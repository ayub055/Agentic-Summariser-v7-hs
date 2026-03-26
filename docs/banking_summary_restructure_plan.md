# Plan: Restructure Banking `_build_data_summary()` for Structured LLM Input

> Improve the banking customer review data summary to use the same structured,
> section-headed, risk-annotated format that the bureau review already uses.

---

## 1. Problem Statement

The banking `_build_data_summary()` in `pipeline/reports/report_summary_chain.py` (lines 100-326)
produces a **flat list of strings** joined by `\n`. The LLM receives something like:

```
Top spending categories: Transfers: 1,45,000, Loan EMI: 72,500, Food & Dining: 23,400
Monthly cashflow: Avg net -12,340 INR (Total in: 4,85,000, out: 5,22,000)
Salary income: 85,000 INR average from KOTAK MAHINDRA (3 months)
EMI commitments: 36,250 INR average per payment (6 debit transactions)
Rent payments: 15,000 INR (3 transactions)
Banking FOIR (EMI+Rent/Salary): 60.3% [STRETCHED]
Utility bills: 8,500 INR total
Most frequent merchant: SWIGGY (12 transactions, 18,600 INR)
MERCHANT PROFILE: Regular merchants: 5 (SWIGGY, AMAZON, HDFC BANK). Anomaly: PREMIUM MOTORS INR 3,45,000. Concentration: top-1 = 28%, 14 merchants total. Favourite debit merchants: SWIGGY (12 txns, INR 18,600, avg 8 days apart); AMAZON (7 txns, INR 42,300, avg 12 days apart). ...
Account shows moderate ATM dependency with 15% of debits routed through cash withdrawals
Primary account with regular salary credits and EMI outflows — stable usage pattern
DETECTED TRANSACTION EVENTS [include in summary with specific dates/amounts]:
  [HIGH    ] Jan 2025: Self-transfer of INR 72,000 ...
DATA NOT AVAILABLE (do NOT invent or assume these): utility bills
```

### Issues (from `docs/SAMPLE_LLM_PROMPTS.md` observations)

| # | Issue | Impact |
|---|-------|--------|
| 1 | **Flat list, no section headers** | LLM must infer which data maps to which paragraph (Financial Overview vs Merchant vs Events) by keyword matching |
| 2 | **Merchant profile is one massive line** | ~500 chars of period-separated facts. Hard for LLM to parse distinct merchant sub-features (regulars, anomalies, concentration, favourites, counterparties, two-way, emerging) |
| 3 | **Account quality observations are bare strings** | No label or section header. They blend into financial data and may be misinterpreted |
| 4 | **No risk annotations on banking values** | Bureau annotates every value with `[HIGH RISK]`, `[CONCERN]`, `[POSITIVE]` etc. Banking only tags FOIR — cashflow direction, salary consistency, EMI burden are untagged |
| 5 | **No composite signals** | Bureau has `_compute_interaction_signals()` for multi-feature combinations. Banking leaves cross-feature analysis to the LLM (e.g., "salary + same-day self-transfer" is only in events, not flagged as a composite signal) |

### What Bureau Does Right

The bureau `_build_bureau_data_summary()` (lines 766-925) organises data into **10 clearly labelled blocks**:

```
Portfolio Summary:          ← 8 lines, core numbers
CC Utilization:             ← per-product util %
Obligation & FOIR:          ← income, EMI, FOIR with [STRETCHED]/[COMFORTABLE] tags
Product-wise Breakdown:     ← indented per-type detail
Kotak (On-Us) Exposure:     ← own-bank context
Joint Loans:                ← joint account flag
Defaulted Loans:            ← per-type with [ON-US] tag
Behavioral & Risk Features: ← 6 sub-sections, every value annotated
Composite Risk Signals:     ← multi-feature deterministic interpretations
Exposure Trend:             ← 12M/6M trend + commentary
```

Each value carries an inline risk tag. The LLM knows what to highlight without doing its own analysis.

---

## 2. Target State — New Banking Data Summary Format

After restructuring, the LLM will receive:

```
Financial Overview:
  Top Spending: Transfers: 1,45,000, Loan EMI: 72,500, Food & Dining: 23,400
  Monthly Cashflow: Avg net -12,340 INR (Total in: 4,85,000, out: 5,22,000) [DEFICIT]
  Salary: 85,000 INR average from KOTAK MAHINDRA (3 months) [REGULAR]
  EMI Obligation: 36,250 INR average per payment (6 debit transactions)
  Rent: 15,000 INR (3 transactions)
  Banking FOIR (EMI+Rent/Salary): 60.3% [STRETCHED]
  Utility Bills: 8,500 INR total

Merchant Profile:
  Regular Merchants: 5 (SWIGGY, AMAZON, HDFC BANK)
  Anomaly Merchants: PREMIUM MOTORS INR 3,45,000
  Concentration: top-1 = 28%, 14 merchants total
  Favourite Debit Merchants:
    - SWIGGY (12 txns, INR 18,600, avg 8 days apart)
    - AMAZON (7 txns, INR 42,300, avg 12 days apart)
  Favourite Credit Merchants:
    - KOTAK MAHINDRA (3 txns, INR 2,55,000, avg 30 days apart)
  Significant Counterparties: KOTAK MAHINDRA accounts for 53% of credits
  Two-way Merchants: HDFC BANK (credit INR 50,000, debit INR 36,250, net inflow INR 13,750, received first then paid)
  Emerging Merchants (new in recent 3 months): 2 — ZOMATO, UBER

Account Quality:
  Moderate ATM dependency with 15% of debits routed through cash withdrawals
  Primary account with regular salary credits and EMI outflows — stable usage pattern

Transaction Events:
  [HIGH    ] Jan 2025: Self-transfer of INR 72,000 within 2 days of salary credit of INR 85,000 to account ending XX4521
  [HIGH    ] Feb 2025: Loan disbursement credit of INR 3,50,000 followed by INR 3,45,000 debit to PREMIUM MOTORS within 3 days
  [MEDIUM  ] Mar 2025: ECS/NACH bounce — HDFC BANK EMI return of INR 36,250
  [POSITIVE] Jan-Mar 2025: Regular SIP investment of INR 5,000/month to HDFC MUTUAL FUND (3 months)
  [POSITIVE] Jan-Mar 2025: Insurance premium of INR 12,000 to LIC OF INDIA (quarterly)

DATA NOT AVAILABLE (do NOT invent or assume these): utility bills
```

### Key Differences from Current

1. **Section headers** — `Financial Overview:`, `Merchant Profile:`, `Account Quality:`, `Transaction Events:`
2. **Multi-line merchant profile** — each sub-feature on its own indented line, favourite merchants as bullet lists
3. **Labelled account quality** — under its own header instead of bare strings
4. **Risk annotations** — `[DEFICIT]`, `[SURPLUS]`, `[REGULAR]`, `[IRREGULAR]` on cashflow and salary
5. (Optional) **Composite signals** — cross-feature flags similar to bureau

---

## 3. Implementation Steps

### Step 1: Add Section Headers (HIGH PRIORITY)

**What:** Wrap existing data lines under labelled section headers.

**File:** `pipeline/reports/report_summary_chain.py` — `_build_data_summary()`

**Changes:**
- Add `\nFinancial Overview:` header before categories/cashflow/salary/EMI/rent/FOIR/bills
- Indent each line under the header with 2 spaces
- The existing code already builds lines sequentially — just insert headers at the right points

**Complexity:** Low — string formatting only, no logic changes.

---

### Step 2: Break Merchant Profile into Multi-line Block (HIGH PRIORITY)

**What:** Replace the single `MERCHANT PROFILE: ...` line with a multi-line indented block.

**File:** `pipeline/reports/report_summary_chain.py` — lines 201-287 (merchant_features section)

**Current code builds:**
```python
m_parts = []
m_parts.append("Regular merchants: ...")
m_parts.append("Anomaly: ...")
# ... more m_parts ...
sections.append("MERCHANT PROFILE: " + ". ".join(m_parts))  # ONE LINE
```

**New approach:**
```python
merchant_lines = ["\nMerchant Profile:"]
merchant_lines.append(f"  Regular Merchants: ...")
merchant_lines.append(f"  Anomaly Merchants: ...")
# Favourite merchants as sub-bullets
merchant_lines.append(f"  Favourite Debit Merchants:")
for f in fav_list:
    merchant_lines.append(f"    - {f['merchant']} ({f['count']} txns, ...)")
# ... etc ...
sections.extend(merchant_lines)
```

**Complexity:** Medium — restructuring string assembly, same data sources.

---

### Step 3: Label Account Quality Observations (HIGH PRIORITY)

**What:** Add `\nAccount Quality:` header before bare observation strings.

**File:** `pipeline/reports/report_summary_chain.py` — lines 289-293

**Current:**
```python
if report.account_quality:
    obs = report.account_quality.get("observations", [])
    for ob in obs:
        sections.append(ob)  # bare string, no label
```

**New:**
```python
if report.account_quality:
    obs = report.account_quality.get("observations", [])
    if obs:
        sections.append("\nAccount Quality:")
        for ob in obs:
            sections.append(f"  {ob}")
```

**Complexity:** Low — 3-line change.

---

### Step 4: Add Risk Annotations to Banking Values (MEDIUM PRIORITY)

**What:** Tag cashflow direction, salary consistency, and EMI burden using the existing `_annotate_value()` helper.

**Files:**
- `config/thresholds.py` — add banking-specific thresholds
- `pipeline/reports/report_summary_chain.py` — add tags inline

**New thresholds to add in `config/thresholds.py`:**
```python
# Banking cashflow tags
CASHFLOW_DEFICIT_THRESHOLD = 0       # avg net < 0 → [DEFICIT]
CASHFLOW_TIGHT_PCT = 0.10            # avg net < 10% of inflow → [TIGHT CASHFLOW]

# Salary consistency
SALARY_REGULAR_MIN_MONTHS = 3        # >= 3 months → [REGULAR]

# EMI burden (EMI / Salary)
EMI_BURDEN_HIGH = 0.50               # > 50% → [HIGH OBLIGATION]
EMI_BURDEN_MODERATE = 0.30           # > 30% → [MODERATE OBLIGATION]
```

**Tag logic in `_build_data_summary()`:**
```python
# Cashflow
avg_net = (total_inflow - total_outflow) / max(1, len(report.monthly_cashflow))
if avg_net < 0:
    tag = " [DEFICIT]"
elif avg_net < total_inflow * CASHFLOW_TIGHT_PCT:
    tag = " [TIGHT CASHFLOW]"
else:
    tag = " [SURPLUS]"

# Salary
if count >= SALARY_REGULAR_MIN_MONTHS:
    tag = " [REGULAR]"
else:
    tag = " [IRREGULAR]"
```

**Complexity:** Medium — new thresholds + tag logic, but follows existing `_annotate_value()` pattern.

---

### Step 5: Add Banking Composite Signals (LOW PRIORITY / OPTIONAL)

**What:** Add a `_compute_banking_interaction_signals()` function similar to bureau's `_compute_interaction_signals()`.

**File:** `pipeline/reports/report_summary_chain.py`

**Candidate composite signals:**

| Signal | Condition | Output |
|--------|-----------|--------|
| TIGHT CASHFLOW + HIGH OBLIGATION | deficit cashflow + FOIR > 50% | "CASH PRESSURE: Negative monthly cashflow (-12,340 INR) with FOIR at 60.3% — obligations exceed net income" |
| LOW DIVERSIFICATION | top-1 merchant > 40% + < 5 merchants | "CONCENTRATED SPENDING: Top merchant accounts for 45% of debits across only 4 merchants" |
| SALARY ROUTING | salary detected + self-transfer HIGH event | "SALARY ROUTING PATTERN: Salary of 85,000 followed by self-transfer of 72,000 (85% of salary)" |

**Note:** Some of these overlap with events (e.g., salary routing). The composite signal makes the interpretation explicit rather than leaving it to the LLM. However, this step is optional — events already flag individual occurrences. Only add composites for cross-feature patterns that events don't cover.

**Complexity:** Medium — new function, but mirrors existing bureau pattern.

---

### Step 6: Update Prompt to Reference Section Names (LOW PRIORITY)

**What:** Minor adjustments to `CUSTOMER_REVIEW_PROMPT` in `config/prompts.py` to reference the new section headers.

**Current prompt says:**
```
1. FINANCIAL OVERVIEW (4-6 lines): ... Cover salary amount, frequency, source, monthly cashflow ...
2. MERCHANT BEHAVIOR (2-4 lines): If a "MERCHANT PROFILE" line is present below ...
3. TRANSACTION EVENTS: If a "DETECTED TRANSACTION EVENTS" block is present below ...
```

**New prompt says:**
```
1. FINANCIAL OVERVIEW (4-6 lines): Use the data under "Financial Overview:" below. Cover ...
2. MERCHANT BEHAVIOR (2-4 lines): If a "Merchant Profile:" section is present below ...
3. TRANSACTION EVENTS: If a "Transaction Events:" section is present below ...
```

**Also add:**
```
- Values tagged [DEFICIT], [SURPLUS], [REGULAR], [IRREGULAR], [STRETCHED], etc. are pre-computed observations — quote them as factual context, do not override with your own assessment
```

**Complexity:** Low — prompt text changes only.

---

### Step 7: Update SAMPLE_LLM_PROMPTS.md (LOW PRIORITY)

**What:** Regenerate the banking sample prompt to show the new structured format.

**File:** `docs/SAMPLE_LLM_PROMPTS.md`

**Complexity:** Low — documentation only. Update the rendered prompt example and the "What the `{data_summary}` is built from" block map.

---

## 4. Priority & Ordering

| Step | Priority | Impact | Risk | Depends On |
|------|----------|--------|------|------------|
| 1. Section headers | HIGH | Structure | None | — |
| 2. Multi-line merchants | HIGH | Readability | None | — |
| 3. Label account quality | HIGH | Clarity | None | — |
| 4. Risk annotations | MEDIUM | LLM guidance | New thresholds | Step 1 |
| 5. Composite signals | LOW | Prevents LLM cross-analysis | Optional | Step 4 |
| 6. Update prompt | LOW | Prompt-data alignment | None | Steps 1-3 |
| 7. Update sample docs | LOW | Documentation | None | Steps 1-6 |

**Recommended implementation order:** Steps 1 + 2 + 3 together (one commit), then Step 4, then Step 6, then Step 7. Step 5 is optional.

---

## 5. What NOT to Change

- **`_build_comprehensive_data()`** — used by persona chain, different purpose, different prompt
- **The 3-paragraph prompt structure** — already works well (`FINANCIAL OVERVIEW`, `MERCHANT BEHAVIOR`, `TRANSACTION EVENTS`)
- **Event formatting** — `format_events_for_prompt()` in `tools/event_detector.py` already produces structured output with severity tags
- **`DATA NOT AVAILABLE` block** — useful anti-hallucination guard, keep it
- **Bureau data summary** — already well-structured, no changes needed

---

## 6. Files Changed (Summary)

| File | Changes |
|------|---------|
| `pipeline/reports/report_summary_chain.py` | Restructure `_build_data_summary()`: add headers, multi-line merchants, label account quality, add tags, optional composite signals |
| `config/thresholds.py` | Add banking thresholds: `CASHFLOW_DEFICIT_THRESHOLD`, `CASHFLOW_TIGHT_PCT`, `SALARY_REGULAR_MIN_MONTHS`, `EMI_BURDEN_HIGH`, `EMI_BURDEN_MODERATE` |
| `config/prompts.py` | Minor `CUSTOMER_REVIEW_PROMPT` updates to reference section names and tag interpretation rules |
| `docs/SAMPLE_LLM_PROMPTS.md` | Update banking sample prompt example and block map |

---

## 7. Validation

After implementation:

1. **Generate a banking report** for test customer `698167220`:
   ```python
   from tools.combined_report import generate_combined_report_pdf
   generate_combined_report_pdf(698167220)
   ```

2. **Inspect the actual data_summary** by adding a temporary `logger.info("DATA_SUMMARY:\n%s", data_summary)` in `generate_customer_review()` before the chain invocation.

3. **Compare LLM output** — does the review follow the 3-paragraph structure more reliably? Does it quote tagged values? Does it avoid mixing merchant details into the financial overview?

4. **Check the generated HTML** in `reports/combined_report_html_version/` to confirm the narrative reads well in the final report.
