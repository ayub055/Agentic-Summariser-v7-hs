# Account Quality Analysis — Implementation Reference

## Purpose

Determines whether the bank account submitted for analysis is the customer's **primary operating account** or a **salary conduit / secondary account**. A conduit account receives salary but immediately routes it elsewhere, leaving the lender blind to real spending, obligations, and lifestyle.

---

## Files Changed

| File | Change |
|---|---|
| `tools/account_quality.py` | **NEW** — all detection logic |
| `schemas/customer_report.py` | Added `account_quality: Optional[Dict[str, Any]]` field |
| `pipeline/reports/customer_report_builder.py` | Calls `compute_account_quality()` after building base report |
| `pipeline/reports/report_summary_chain.py` | Adds `account_quality.observations` to `_build_data_summary()` → LLM prompt |
| `tools/scorecard.py` | Adds "Account Type" RAG chip (signal 10) to `_banking_signals()` |

---

## Patterns Detected

### Pattern 1 — Salary Conduit (Self-Transfer)

**What it detects:** A large outflow within 3 days of a salary credit, indicating the account is not where the customer's financial life happens.

**Data sources:**
- `rg_sal_strings.csv` via `load_rg_salary_data(customer_id)` → provides the exact `tran_date` and `tran_amt_in_ac` of each salary credit
- Raw transactions (`data/rgs.csv`) via `get_transactions_df()` → all debits

**Algorithm (`_detect_conduit_events`):**
1. For each salary transaction from `rg_sal.transactions`:
   - Define a window: `[salary_date, salary_date + 3 days]`
   - Fetch all debit rows in that window from the raw DataFrame
   - For each debit: compute `pct = debit_amount / salary_amount × 100`
   - **Threshold: skip if `pct < 40%`** — only large outflows are flagged
2. For each flagged debit, check if it is a **self-transfer**:
   - Narration contains any of: `SELF`, `OWN A/C`, `OWN ACCOUNT`, `OWNACCOUNT`, `SELF TRF`, `SELF TRANSFER`
   - OR: first 6 characters of `meta.prty_name` (customer name) appear in the narration (catches UPI transfers to own account where the beneficiary name matches the account holder)
3. Each flagged event is recorded as: `{salary_date, outflow_date, outflow_amount, pct_of_salary, days_after_salary, is_self_transfer, narration, tran_type}`

**Conduit summary metrics:**
- `conduit_months`: count of unique calendar months (YYYY-MM) that have ≥1 flagged event
- `salary_outflow_pct_3d`: per conduit month, take the single largest outflow %; average across conduit months
  - Example: Month 1 → 85%, Month 2 → 72%, Month 3 → 91% → `salary_outflow_pct_3d = 82.7%`

**Score impact:**
- `conduit_months == 0` → +15 (no conduit evidence)
- `conduit_months 1–2` → −15
- `conduit_months ≥ 3` → −35 (strong conduit pattern)

---

### Pattern 2 — ATM Cash Dependency

**What it detects:** A high proportion of debit transactions are ATM withdrawals, meaning the customer operates primarily in cash. Spending behavior, merchant usage, and obligations are invisible.

**Data source:** Raw transactions — `tran_partclr` (narration), `tran_type`, `category_of_txn`

**Algorithm (`_compute_atm_pct`):**
1. From all debit rows for the customer, flag a row as ATM if **any** of:
   - `tran_partclr.upper()` contains `"ATM"`
   - `tran_type.upper()` contains `"ATM"`
   - `category_of_txn.upper()` contains `"ATM"`
2. `atm_debit_pct = (ATM debit count / total debit count) × 100`

**Score impact:**
- `atm_pct > 50%` → −20 (heavy cash user)
- No penalty below 50%

**Observation thresholds for LLM:**
- `> 50%` → "X% of debit transactions are ATM cash withdrawals — spending behavior is largely cash-based"
- `> 30%` → "X% of debit transactions are ATM withdrawals — moderate cash dependency"

---

### Pattern 3 — Low Account Activity

**What it detects:** Very few debit transactions per month despite receiving salary. Primary accounts of salaried individuals typically show 15–30+ debits/month (grocery, food, fuel, utilities, UPI payments). Very low activity suggests the account is not where daily life happens.

**Data source:** Raw transactions — count of debit rows grouped by calendar month

**Algorithm:**
1. `months_count = number of distinct calendar months (YYYY-MM) in all transactions`
2. `avg_monthly_debits = total debit rows / months_count`

**Score impact:**
- `avg_monthly_debits > 20` → +10 (active account, positive signal)
- `avg_monthly_debits < 10` → −15 (low activity, negative signal)

**Observation:** Generated only if `salary_amount > 0` (not meaningful for accounts with no detected salary).

---

### Pattern 4 — No Obligation Visibility

**What it detects:** The bureau may show N live loan tradelines, but if no EMI debits appear in the banking statement, the customer is servicing loans from a different account. Similarly, absence of utility bills and rent while earning a salary is unusual.

**Data source:** The already-built `CustomerReport` (reuses what was already computed):
- `customer_report.emis` → EMI payments detected
- `customer_report.bills` → Utility/bill payments detected
- `customer_report.rent` → Rent payments detected

**Algorithm:** Simple boolean checks — no additional data loading needed.
- `has_emi_debits = bool(customer_report.emis)`
- `has_utility_debits = bool(customer_report.bills)`
- `has_rent_visible = bool(customer_report.rent)`

**Score impact:**
- `has_emi` → +15
- `has_utility` → +10
- `has_rent` → +10
- None of the above → −15

**Observations:**
- If none of EMI/utility/rent → "No recurring obligations (EMI, utility bills, rent) detected — loan servicing and fixed expenses may be flowing through a different account"
- If only EMI missing → "No EMI debits detected — loan obligations may be serviced from another account"

---

## Primary Score Formula

Starting from a baseline of 50:

| Condition | Delta |
|---|---|
| EMI debits visible in banking | +15 |
| Utility/bill payments present | +10 |
| Rent payments present | +10 |
| Avg monthly debits > 20 | +10 |
| No conduit events detected | +15 |
| Conduit in 1–2 months | −15 |
| Conduit in ≥3 months | −35 |
| ATM withdrawal % > 50% | −20 |
| Avg monthly debits < 10 | −15 |
| No EMI + no utility + no rent | −15 |

Score is clamped to [0, 100].

**Classification (threshold = 60):**

| Score | `account_type` | Confidence |
|---|---|---|
| ≥ 75 | `primary` | high |
| 60–74 | `primary` | medium |
| 40–59 | `secondary` | medium |
| < 40, conduit_months ≥ 3 | `conduit` | high |
| < 40, conduit_months < 3 | `conduit` | medium |
| No salary data at all | `unknown` | low |

---

## Integration: Where Results Surface

### 1. Banking LLM Summary (`customer_review`)

`report_summary_chain.py` → `_build_data_summary()` appends:
```
Account quality (Conduit account, primary score 35/100):
  Salary conduit detected: avg 85% of salary transferred out within 3 days of credit in 4 month(s) — this appears to be a self-transfer account, not the primary operating account.
  62% of debit transactions are ATM cash withdrawals — spending behavior is largely cash-based and invisible to banking analysis.
  No EMI debits detected in banking — loan obligations may be serviced from another account.
```
The LLM receives this block along with cashflow, salary, EMI, and category data — and naturally incorporates account quality findings into the generated `customer_review`.

### 2. Scorecard RAG Chip

`tools/scorecard.py` → `_banking_signals()` adds signal 10 "Account Type":

| `account_type` | RAG | Example chip |
|---|---|---|
| `primary` | 🟢 green | Primary — Score 78/100 |
| `secondary` | 🟡 amber | Secondary — Score 52/100 |
| `conduit` | 🔴 red | Conduit — Score 25/100 |
| `unknown` | neutral | Unknown — Score 50/100 |

This chip appears in all 3 reports (customer, bureau-only skips it, combined shows it).

### 3. `CustomerReport.account_quality` field

The full dict is attached to the `CustomerReport` object, making it available to any future renderer or template if needed.

---

## Data Flow Summary

```
build_customer_report(customer_id)
  │
  ├── 1. Build base CustomerReport (salary, emis, bills, rent from existing tools)
  │
  └── 2. compute_account_quality(customer_id, customer_report=base_report)
           │
           ├── load_rg_salary_data(customer_id)     → salary dates + amounts
           ├── get_transactions_df()[cust_id]        → raw transaction rows
           │
           ├── _detect_conduit_events()              → Pattern 1
           ├── _compute_atm_pct()                    → Pattern 2
           ├── avg_monthly_debits                    → Pattern 3
           ├── has_emi / has_utility / has_rent      → Pattern 4 (from base_report)
           │
           ├── primary_score (0–100)
           ├── account_type (primary/secondary/conduit/unknown)
           └── observations (list of strings)
                │
                ├── → report_summary_chain._build_data_summary()  → LLM prompt
                └── → scorecard._banking_signals()                → RAG chip
```

---

## Example Output (Conduit Customer)

```
account_type:          "conduit"
confidence:            "high"
primary_score:         25
conduit_months:        4
salary_outflow_pct_3d: 87.2%
atm_debit_pct:         14.3%
avg_monthly_debits:    7.0
has_emi_debits:        False
has_utility_debits:    False
has_rent_visible:      False

conduit_events: [
  { salary_date: "2025-07-01", outflow_date: "2025-07-02",
    outflow_amount: 69600, pct_of_salary: 87.0, days_after_salary: 1,
    is_self_transfer: True, narration: "UPI/SELF/HDFC9872", tran_type: "UPI" },
  ...
]

observations: [
  "Salary conduit detected: avg 87% of salary transferred out within 3 days of credit
   in 4 month(s) — this appears to be a self-transfer account, not the primary operating account.",
  "No recurring obligations (EMI, utility bills, rent) detected in banking — loan
   servicing and fixed expenses may be flowing through a different account."
]
```

---

## Example Output (Primary Customer)

```
account_type:          "primary"
confidence:            "high"
primary_score:         80
conduit_months:        0
salary_outflow_pct_3d: 0.0%
atm_debit_pct:         8.1%
avg_monthly_debits:    28.4
has_emi_debits:        True
has_utility_debits:    True
has_rent_visible:      True

observations: [
  "Account appears primary: EMI payments visible, utility bills paid, rent payments present
   with avg 28 debit transactions/month."
]
```
