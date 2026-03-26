# Checklist Algorithm Reference

Exact algorithms behind each checklist item in the Quick Assessment Checklist.
Generated via `/document-algorithm <item-name>`.

All checklist logic lives in `pipeline/renderers/combined_report_renderer.py:compute_checklist()`.

---

# Bureau Checklist

---

## B1. DPD > 0 in bureau

**Source:** `combined_report_renderer.py:497-515`

**Data source:** `bureau_report.executive_inputs.max_dpd`, `.max_dpd_loan_type`, `.max_dpd_months_ago`

### Algorithm

1. Read `executive_inputs.max_dpd` from the bureau report
2. If `max_dpd` is not None and > 0 → checked = True
3. Build detail string: `"{max_dpd} days — {loan_type} — {months_ago}M ago"`

### Thresholds

| Condition | Severity |
|-----------|----------|
| `max_dpd > 0` | high |
| `max_dpd == 0` or None | positive |

### Edge Cases
- If `bureau_report` is None, defaults to unchecked/positive

---

## B2. Adverse events (write-off / settlement)

**Source:** `combined_report_renderer.py:517-530`

**Data source:** `bureau_report.feature_vectors[*].forced_event_flags`

### Algorithm

1. Iterate all loan-type feature vectors in bureau report
2. For each vector, scan `forced_event_flags` list
3. Collect any flag that matches `_ADVERSE_FLAGS = {"WRF", "SET", "SMA", "SUB", "DBT", "LSS", "WOF"}`
4. If any adverse flags found → checked = True
5. Detail: comma-separated sorted unique flags

### Thresholds

| Condition | Severity |
|-----------|----------|
| Any adverse flag present | high |
| No adverse flags | positive |

### Edge Cases
- Flags are extracted per-tradeline from `dpd_string` by `_extract_forced_event_flags()` in `bureau_feature_extractor.py` using regex `[A-Z]{3}`, excluding `STD` and `XXX`

---

## B3. High FOIR (> 50%)

**Source:** `combined_report_renderer.py:532-542`

**Data source:** `bureau_report.tradeline_features.foir` (pre-computed in `tl_features.csv` column `foir`)

### Algorithm

1. Read `foir` from `tradeline_features`
2. If `foir > 50` → checked = True

### Thresholds

| Condition | Severity |
|-----------|----------|
| `foir > 65%` | high |
| `50% < foir <= 65%` | medium |
| `foir <= 50%` or None | neutral |

### Edge Cases
- `foir` is a pre-computed value from upstream scoring; None means data unavailable

---

## B4. CC utilization elevated (>=30%)

**Source:** `combined_report_renderer.py:544-558`

**Data source:** `bureau_report.feature_vectors[LoanType.CC].utilization_ratio`

### Algorithm

1. Look up `feature_vectors[LoanType.CC]`
2. Read `utilization_ratio` — computed as `total_outstanding / total_credit_limit` across **live CC tradelines only** (see `bureau_feature_extractor.py:147-170`)
3. The ratio is stored as a percentage (0–100 scale, already multiplied)
4. If `utilization_ratio >= 30` → checked = True

### Thresholds

| Condition | Severity |
|-----------|----------|
| `util >= 75%` | high |
| `30% <= util < 75%` | medium |
| `util < 30%` or None | positive |

### Edge Cases
- Only live CC tradelines are included (closed are skipped at `bureau_feature_extractor.py:159`)
- If no CC tradelines exist, `cc_vec` is None → unchecked/positive
- If total credit limit is 0, utilization is None

---

## B5. Customer has Kotak loan

**Source:** `combined_report_renderer.py:560-577`

**Data source:** `bureau_report.feature_vectors[*].on_us_count`

### Algorithm

1. Iterate all loan-type feature vectors
2. Sum `on_us_count` across all types (Kotak = sectors `{"KOTAK BANK", "KOTAK PRIME"}`)
3. Build per-type distribution string: e.g., `"PL(2), HL(1)"`
4. If `kotak_total > 0` → checked = True
5. Detail: `"{count} Kotak loan(s): {type_distribution}"`

### Thresholds

| Condition | Severity |
|-----------|----------|
| Any Kotak loan exists | neutral |
| No Kotak loans | neutral |

---

## B6. Kotak loan default (live)

**Source:** `combined_report_renderer.py:579-625`

**Data source:** Raw `dpd_data.csv` via `_load_bureau_data()` (cached)

### Algorithm

1. Load raw bureau rows from `dpd_data.csv`
2. Filter to customer's rows (`crn == customer_id`)
3. For each row:
   a. Check `sector` is in `ON_US_SECTORS` (`{"KOTAK BANK", "KOTAK PRIME"}`) — skip if not Kotak
   b. Check `loan_status` is NOT in closed statuses (`{"closed", "written off", "settled", "npa", "loss", "doubtful", "write-off"}`) — skip if closed
   c. Parse `max_dpd` from the row
   d. Scan `dpd_string` for adverse flags (`_ADVERSE_FLAGS`)
   e. If `max_dpd > 0` OR any adverse flag found → record as default
4. Build detail: loan type + DPD + flags for each defaulted tradeline (up to 5)

### Thresholds

| Condition | Severity |
|-----------|----------|
| Any live Kotak tradeline has default | high |
| Kotak loans exist but no defaults | positive |
| No Kotak loans at all | neutral |

### Edge Cases
- Queries raw data (not aggregated feature vectors) to accurately identify Kotak-specific defaults
- Wrapped in `try/except` for fail-soft behavior

---

## B7. Live Home Loan detected

**Source:** `combined_report_renderer.py:627-644`

**Data source:** `bureau_report.feature_vectors[LoanType.HL]`

### Algorithm

1. Look up `feature_vectors[LoanType.HL]`
2. If `hl_vec.live_count > 0` → checked = True
3. Detail: `"Sanctioned: ₹{amount} | On-Us: {count}, Off-Us: {count}"`

### Thresholds

| Condition | Severity |
|-----------|----------|
| Live HL exists | neutral |
| No live HL | neutral |

---

## B8. Bureau thick

**Source:** `combined_report_renderer.py:646-656`

**Data source:** `bureau_report.tradeline_features.bu_grp` (from `tl_features.csv` column `bu_grp`)

### Algorithm

1. Read `bu_grp` string from tradeline features
2. Check if the string contains "thick" (case-insensitive)
3. If thick → checked = True, no detail shown
4. If not thick → unchecked, detail shows actual value (e.g., "BU thin")

### Thresholds

| Condition | Severity |
|-----------|----------|
| Contains "thick" | positive |
| Does not contain "thick" | medium |

---

## B9. Banking thick

**Source:** `combined_report_renderer.py:658-668`

**Data source:** `bureau_report.tradeline_features.bank_grp` (from `tl_features.csv` column `bank_grp`)

### Algorithm

1. Read `bank_grp` string from tradeline features
2. Check if the string contains "thick" (case-insensitive)
3. Same logic as B8

### Thresholds

| Condition | Severity |
|-----------|----------|
| Contains "thick" | positive |
| Does not contain "thick" | medium |

---

## B10. Exposure elevated

**Source:** `combined_report_renderer.py:670-689`, `tools/scorecard.py:54-117`

**Data source:** `bureau_report.monthly_exposure` (24-month sanctioned exposure time series)

### Algorithm

1. Call `_exposure_signals(monthly_exposure)` from `tools/scorecard.py`
2. The function computes a 12M point-in-time comparison:
   a. Requires >= 13 months of data
   b. `current` = total sanctioned exposure in most recent month
   c. `ago_12m` = total sanctioned exposure 12 months ago
   d. `pct_change = (current - ago_12m) / ago_12m * 100`
   e. If `ago_12m == 0` and `current > 0`, change = 100%
3. RAG assignment via `_rag_exposure()`:
   - `<= -5%` → green ("declining")
   - `-5% to +5%` → neutral ("Stable")
   - `+5% to +30%` → amber ("growing")
   - `> +30%` → red ("rapid growth")
4. If RAG is amber or red → checked = True (elevated)

### Thresholds

| Condition | Severity |
|-----------|----------|
| RAG = red (> +30%) | high |
| RAG = amber (+5% to +30%) | medium |
| RAG = green (<= -5%) | positive |
| RAG = neutral or no data | neutral |

### Edge Cases
- If fewer than 13 months of exposure data, no signal is produced → neutral
- If all monthly totals are 0, no signal → neutral

---

# Banking Checklist

---

## K1. ECS / NACH bounces

**Source:** `combined_report_renderer.py:693-700`, `tools/event_detector.py:169-226`

**Data source:** Banking transactions (`rgs.csv`) via keyword event detection

### Algorithm

1. Event detector scans debit transactions for `ECS_BOUNCE_KEYWORDS`:
   `["ECS%RETURN", "ECS%BOUNCE", "NACH%RETURN", "NACH%BOUNCE", "ECS%DISHON", "NACH%DISHON", "MANDATE%REJECT"]`
   (`%` = SQL-style wildcard, matches any characters)
2. Matches `tran_partclr` (uppercased) against regex pattern
3. No `min_months` requirement — single occurrence triggers
4. Each match produces one event; checklist reads first event's description

### Thresholds

| Condition | Severity |
|-----------|----------|
| Any bounce detected | high |
| No bounces | neutral |

---

## K2. Loan disbursement detected

**Source:** `combined_report_renderer.py:702-713`, `tools/event_detector.py:169-226`

**Data source:** Banking transactions (`rgs.csv`) — credit transactions

### Algorithm

1. Check for events of type `loan_disbursal` (keyword match on credits using `LOAN_DISBURSEMENT_KEYWORDS`: `["LOAN DIS", "LOAN DISB", "LOAN DISBURS", "LOAN CREDIT", "LOAN A/C CR", "SANCTIONED"]`)
2. If none, check for `loan_redistribution_suspect` events
3. If none, check `large_single_credit` events where description contains "lender" or "loan"
4. First match wins

### Thresholds

| Condition | Severity |
|-----------|----------|
| Any loan event detected | high |
| None | neutral |

---

## K3. Post-disbursement fund diversion

**Source:** `combined_report_renderer.py:715-734`, `tools/event_detector.py:383-512`

**Data source:** Banking transactions (`rgs.csv`) — credit + debit analysis

### Algorithm

1. For each credit that looks like a loan disbursement (keyword or lender match):
   a. `min_amount` = max(`POST_DISB_MIN_AMOUNT` (₹50,000), salary × 2)
   b. Gather all debits within `POST_DISB_WINDOW_DAYS` (7 days) where amount >= `POST_DISB_MIN_DEBIT` (₹5,000)
   c. Group debits by recipient name
   d. Check **concentration**: do top recipients account for >= `POST_DISB_CONCENTRATION_PCT` (50%) of disbursement?
   e. Check **amount match**: total debits within ±`POST_DISB_MATCH_TOLERANCE` (15%) of disbursement?
   f. Must have concentration >= 50% OR amount match to trigger
2. Checklist reads `_amounts_match` and `_concentration_pct` from the event

### Thresholds

| Condition | Severity |
|-----------|----------|
| `_amounts_match == True` | high |
| `concentration_pct >= 50%` | high |
| Other triggered cases | medium |
| Not triggered | neutral |

### Edge Cases
- Each disbursement credit is analyzed independently
- Recipients named "Unknown" are excluded from concentration calculation
- Up to 5 top recipients shown in detail

---

## K4. Salary detected in banking

**Source:** `combined_report_renderer.py:736-747`

**Data source:** `customer_report.salary` (built by `customer_report_builder._get_salary_block()`)

### Algorithm

1. Check if `customer_report.salary` is not None
2. If present → checked = True
3. Detail: `"₹{avg_amount} avg ({frequency} transactions)"`

### Thresholds

| Condition | Severity |
|-----------|----------|
| Salary detected | positive |
| No salary | neutral |

---

## K5. EMI obligations present

**Source:** `combined_report_renderer.py:749-760`

**Data source:** `customer_report.emis` (built by `customer_report_builder._get_emi_block()` via `resolve_category_presence(customer_id, "emi")`)

### Algorithm

1. Check if `customer_report.emis` is not None and has items
2. Sum all EMI amounts: `total_emi = sum(e.amount for e in emis)`
3. Detail: `"₹{total} total across {count} lender(s)"`

### Thresholds

| Condition | Severity |
|-----------|----------|
| EMIs present | medium |
| No EMIs | neutral |

### Edge Cases
- EMI detection uses the 4-strategy category resolver (column → YAML → keyword → fuzzy match)
- Grouped by merchant name — each lender is a separate `EMIBlock`

---

## K6. Rent payments present

**Source:** `combined_report_renderer.py:762-769`

**Data source:** `customer_report.rent` (built by `customer_report_builder._get_rent_block()` via `resolve_category_presence(customer_id, "rent")`)

### Algorithm

1. Check if `customer_report.rent` is not None
2. Detail: `"₹{amount} ({frequency} transactions)"`

### Thresholds

| Condition | Severity |
|-----------|----------|
| Rent detected | neutral |
| No rent | neutral |

---

## K7. Post-salary self-transfer

**Source:** `combined_report_renderer.py:771-778`, `tools/event_detector.py:515-579`

**Data source:** Banking transactions (`rgs.csv`) — salary credits + subsequent debits

### Algorithm

1. For each salary credit transaction:
   a. Look for debits within **3 days** where amount >= **40%** of salary amount
   b. Check if the debit is a self-transfer via:
      - Narration keyword matching (self-transfer keywords)
      - OR `self_transfer` column flag == "1"
      - OR customer name prefix match in narration
2. One event per salary month (deduplication by month key)

### Thresholds

| Condition | Severity |
|-----------|----------|
| Self-transfer detected | medium |
| None | neutral |

### Edge Cases
- Uses customer's `prty_name` (first 6 chars, uppercased) for self-name detection
- Only fires once per salary month even if multiple matches exist

---

## K8. NACH mandate EMI detected

**Source:** `combined_report_renderer.py:780-787`, `tools/event_detector.py:169-226`

**Data source:** Banking transactions (`rgs.csv`) — debit transactions

### Algorithm

1. Event detector scans debit transactions for `MANDATE_EMI_KEYWORDS`: `["NACH-10", "SPLN"]`
2. Requires `min_months: 2` — must appear in at least 2 calendar months (recurring pattern)
3. If recurring, produces summary: avg amount/month and sample narration

### Thresholds

| Condition | Severity |
|-----------|----------|
| Recurring NACH EMI detected | medium |
| None or fewer than 2 months | neutral |

---

## K9. Credit card bill payments

**Source:** `combined_report_renderer.py:789-796`, `tools/event_detector.py:169-226`

**Data source:** Banking transactions (`rgs.csv`) — debit transactions

### Algorithm

1. Event detector scans debit transactions for `CC_PAYMENT_KEYWORDS`:
   `["CREDIT CARD PAYMENT", "BILL PAID TO CREDIT CARD", "CREDIT CARD BILL", "CC PAY", "CARD DUES"]`
2. Requires `min_months: 2` — must appear in at least 2 calendar months

### Thresholds

| Condition | Severity |
|-----------|----------|
| CC payments detected | positive |
| None | neutral |

---

## K10. Land purchase payments

**Source:** `combined_report_renderer.py:798-805`, `tools/event_detector.py:169-226`

**Data source:** Banking transactions (`rgs.csv`) — debit transactions

### Algorithm

1. Event detector scans debit transactions for `LAND_PAYMENT_KEYWORDS`: `[":LAND PAYMENT", " LAND PAYMENT "]`
2. No `min_months` requirement — single occurrence triggers

### Thresholds

| Condition | Severity |
|-----------|----------|
| Land payment detected | medium |
| None | neutral |

---

## K11. ATM withdrawals elevated

**Source:** `combined_report_renderer.py:807-828`, `tools/event_detector.py:994-1097`

**Data source:** Banking transactions (`rgs.csv`) — columns: `dr_cr_indctor`, `tran_partclr`, `tran_amt_in_ac`, `tran_date`

### Algorithm

1. **Filter to debits only** — select rows where `dr_cr_indctor == "D"`
2. **Identify ATM transactions** — match `tran_partclr` (uppercased) against `ATM_WITHDRAWAL_KEYWORDS` regex pattern (keywords like `ATL/`, `ATW/`, etc. from `config/keywords.py`)
3. **Parse dates** — convert `tran_date` to datetime, drop rows with invalid dates
4. **Group by calendar month** — assign each transaction to a month period
5. **Split into halves** — divide the sorted months at the midpoint:
   - `first_months = all_months[:mid]` (earlier half)
   - `last_months = all_months[mid:]` (recent half)
   - e.g., 6 months of data → months [0,1,2] = first, [3,4,5] = last
6. **Sum amounts per half** — `first_amt` = total ATM withdrawals in first half, `last_amt` = total in last half
7. **Compute change percentage**:
   ```
   change_pct = ((last_amt - first_amt) / first_amt) * 100
   ```
   If `first_amt == 0` and `last_amt > 0`, change = 100%. If both zero, change = 0%.
8. **Determine elevated flag**:
   ```
   is_elevated = last_amt > first_amt AND change_pct > 20
   ```
9. **Extract ATM addresses** — parse narrations for location info via `_extract_atm_address()`

### Thresholds

| Condition | Severity |
|-----------|----------|
| `last_amt > first_amt` AND `change_pct > 20%` | medium |
| Otherwise | neutral |
| Fewer than 2 months of ATM data | neutral |

### Edge Cases
- If fewer than 2 months of ATM transactions exist, `is_elevated` defaults to `False`
- If no debit transactions exist at all, returns empty (no checklist item event)
- Addresses are extracted and shown as "Likely nearby" locations in the detail

---

## K12. Transactions above 95th percentile

**Source:** `combined_report_renderer.py:845-866`

**Data source:** Banking transactions (`rgs.csv`) — columns: `tran_amt_in_ac`, `dr_cr_indctor`, `tran_partclr`

### Algorithm

1. **Load customer transactions** — filter `get_transactions_df()` by `cust_id`
2. **Process credits and debits separately** — loop over `("C", "credit")` and `("D", "debit")`
3. **Minimum sample guard** — if a direction has **fewer than 5 transactions**, skip it entirely
4. **Compute 95th percentile threshold**:
   ```python
   p95 = np.percentile(dir_amounts, 95)
   ```
5. **Find outliers** — select all transactions where `amount > p95` (strictly greater than)
6. **Extract merchant names** — for each outlier: `extract_recipient_name(narration)` → `clean_narration(narration)` → fallback `"Unknown"`
7. **Build detail** — collect as `"Merchant: ₹Amount (credit/debit)"`, show up to 5

### Thresholds

| Condition | Severity |
|-----------|----------|
| Any outlier exists (credit or debit) | medium |
| No outliers in either direction | neutral |

### Edge Cases
- Credits and debits are evaluated **independently** — a ₹50,000 credit is compared against the 95th percentile of credits only, not all transactions
- Directions with fewer than 5 transactions are skipped (not enough data for meaningful percentile)
- Wrapped in `try/except` — if data loading fails, this item is silently skipped (fail-soft)

---

## K13. Automated (NACH/mandate) transactions

**Source:** `combined_report_renderer.py:868-879`

**Data source:** Banking transactions (`rgs.csv`) — columns: `tran_partclr`, `dr_cr_indctor`

### Algorithm

1. Uppercase all narrations
2. Match rows containing `"NACH"` or `"MANDATE"` (regex)
3. Count matches split by direction: debit count + credit count
4. Detail: `"{total} total ({debits} debits, {credits} credits)"`

### Thresholds

| Condition | Severity |
|-----------|----------|
| Any NACH/mandate found | neutral |
| None | neutral |

### Edge Cases
- Always neutral severity — this is informational, not a risk signal

---

## K14. Payment mode distribution shift

**Source:** `combined_report_renderer.py:881-975`

**Data source:** Banking transactions (`rgs.csv`) — columns: `tran_type`, `tran_partclr`, `tran_date`

### Algorithm

1. **Infer payment mode** for each transaction: `tran_type` if available, else narration-based detection:
   - UPI, NEFT, IMPS, RTGS, NACH, Mobile Banking, IFT, Internet Banking, Funds Transfer, ATM, Payment Gateway, Card Payment, Cheque → fallback "Other"
2. **Group by calendar month** and sort
3. **Require minimum data**: `MODE_SHIFT_MIN_MONTHS` (3) distinct months
4. **Split into periods**:
   - Recent = last `MODE_SHIFT_RECENT_MONTHS` (2) calendar months
   - Earlier = all months before that
5. **Require minimum transactions**: both periods need >= `MODE_SHIFT_MIN_TRANSACTIONS` (5)
6. **Compute distribution** per period (% of total for each mode)
7. **Detect shifts**: for each mode, `delta = recent_pct - earlier_pct`
8. **Flag if any mode shifts >= `MODE_SHIFT_THRESHOLD_PP`** (15 percentage points)

### Thresholds (from `config/thresholds.py`)

| Parameter | Value |
|-----------|-------|
| `MODE_SHIFT_MIN_MONTHS` | 3 |
| `MODE_SHIFT_RECENT_MONTHS` | 2 |
| `MODE_SHIFT_MIN_TRANSACTIONS` | 5 |
| `MODE_SHIFT_THRESHOLD_PP` | 15.0 pp |

| Condition | Severity |
|-----------|----------|
| Any mode shift >= 15pp | medium |
| No significant shifts | neutral |
| Insufficient data | neutral |

### Edge Cases
- Detail shows each shifted mode: `"UPI: 20% → 50% (+30pp)"`
- Sorted by absolute delta (largest shift first)

---

## K15. Emerging merchants detected

**Source:** `combined_report_renderer.py:977-983`

**Data source:** `customer_report.merchant_features["emerging_merchants"]`

### Algorithm

1. Read `emerging_merchants` from `customer_report.merchant_features`
2. If list is non-empty → checked = True
3. Detail: `"{count} new: {name1}, {name2}, {name3}"` (up to 3 names)

### Thresholds

| Condition | Severity |
|-----------|----------|
| Emerging merchants found | medium |
| None | (item not rendered) |

### Edge Cases
- This item is only appended if merchants exist — it does not appear at all if empty
