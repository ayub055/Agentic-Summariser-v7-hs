# Code Features Reference

## 1. Delinquency Detection

The system has comprehensive, multi-layer delinquency detection covering both live and closed loans within configurable time windows (6M, 9M, 18M, 24M).

### Detection is Present: YES

---

### 1.1 Raw Data Fields (`dpd_data.csv`)

| CSV Column | Meaning |
|---|---|
| `max_dpd` | Lifetime worst DPD for the tradeline |
| `months_since_max_dpd` | How many months ago that worst DPD occurred |
| `dpf1` – `dpf36` | Month-by-month DPD flag (0/1) for the last 36 months |
| `loan_status` | `"Live"` or `"Closed"` |
| `dpd_string` | Encoded payment history string — source of forced event codes |

---

### 1.2 Feature Extraction (`pipeline/extractors/bureau_feature_extractor.py`)

**`_compute_max_dpd(tradelines)`**
- Reads `max_dpd` and `months_since_max_dpd` for each tradeline
- Sets `delinquency_flag = True` if `max_dpd > 0`
- Tracks both Live and Closed loans independently

**`_extract_forced_event_flags(tradelines)`**
- Parses `dpd_string` for 7 adverse status codes:

| Code | Meaning |
|---|---|
| `WRF` | Written-off (outstanding loss) |
| `SET` | Settled (below full amount) |
| `SMA` | Special Mention Account |
| `SUB` | Substandard asset |
| `DBT` | Doubtful asset |
| `LSS` | Loss asset |
| `WOF` | Written-off (full) |

Any of these present → automatic **HIGH RISK** override in the scorecard regardless of DPD value.

**`_build_feature_vector(tradelines, loan_type)`**
- Produces `BureauLoanFeatureVector` per loan type with:
  - `delinquency_flag`, `max_dpd`, `max_dpd_months_ago`
  - `live_count`, `closed_count`
  - `forced_event_flags` (list of matched codes above)

---

### 1.3 Portfolio Aggregation (`pipeline/extractors/bureau_feature_aggregator.py`)

`aggregate_bureau_features()` rolls up all per-loan-type vectors into `BureauExecutiveSummaryInputs`:

| Field | Source |
|---|---|
| `has_delinquency` | True if any loan type has `delinquency_flag` |
| `max_dpd` | Worst DPD across all loan types |
| `max_dpd_months_ago` | When that worst DPD occurred |
| `max_dpd_loan_type` | Which loan type held the worst DPD |

---

### 1.4 Pre-Computed Tradeline Features (`tl_features.csv` → `features/tradeline_features.py`)

These are computed externally and loaded per customer:

| Field | Raw Column | Window | Description |
|---|---|---|---|
| `max_dpd_6m_cc` | `max_dpd_l6m_cc_onc` | 6 months | Max DPD on credit card |
| `max_dpd_6m_pl` | `max_dpd_l6m_pl_onc` | 6 months | Max DPD on personal loan |
| `max_dpd_9m_cc` | `max_dpd_l9m_cc_onc` | 9 months | Max DPD on credit card |
| `months_since_last_0p_uns` | `mon_sin_last_0p_uns_op` | — | Months since last unsecured 0+ DPD event |
| `months_since_last_0p_pl` | `monsinlast_0p_pl_onc` | — | Months since last PL 0+ DPD event |
| `pct_0plus_24m_all` | `pct_0p_l24m_all_onc` | 24 months | % of active trades with 0+ DPD in 24M |
| `pct_0plus_24m_pl` | `pct_0p_l24m_pl_onc` | 24 months | % of PL trades with 0+ DPD in 24M |
| `pct_missed_payments_18m` | `pct_missed_pymt_last18m_all` | **18 months** | % of all payments missed |

---

### 1.5 Thresholds (`config/thresholds.py`)

```python
DPD_HIGH_RISK          = 90     # max_dpd > 90  → Severe / NPA risk
DPD_MODERATE_RISK      = 30     # max_dpd > 30  → Significant past-due
MISSED_PAYMENTS_HIGH_RISK = 10.0  # >10% missed (18M window) → high_risk
RECENT_DELINQUENCY_MONTHS = 6   # months_since_max_dpd < 6 → CONCERN label
CLEAN_HISTORY_STRONG_MONTHS = 24 # ≥24M clean → [POSITIVE]
CLEAN_HISTORY_GOOD_MONTHS   = 12 # ≥12M clean → [POSITIVE]
PCT_0PLUS_HIGH_RISK    = 10.0   # >10% trades with 0+ DPD (24M) → HIGH RISK
```

---

### 1.6 Key Findings Engine (`pipeline/reports/key_findings.py`)

All delinquency findings are deterministic (no LLM). Generated in three passes:

**Portfolio findings** (`_portfolio_findings`):
- `has_delinquency=True` + `max_dpd > 90` → severity `high_risk`
- `has_delinquency=True` + `max_dpd > 30` → severity `moderate_risk`
- `has_delinquency=True` + `max_dpd > 0` → severity `concern`
- `has_delinquency=False` → severity `positive` ("No delinquency detected across the portfolio")

**Per-loan-type findings** (`_loan_type_findings`):
- Each `BureauLoanFeatureVector` with `delinquency_flag=True` generates a finding labelled by loan type (PL, CC, HL, etc.)
- `forced_event_flags` present → finding listed separately with the event codes

**Tradeline behavioral findings** (`_tradeline_findings`):
- Scans `max_dpd_6m_cc`, `max_dpd_6m_pl`, `max_dpd_9m_cc` for recent-window DPD
- `pct_missed_payments_18m > 10%` → `high_risk`; `> 0%` → `concern`
- `pct_0plus_24m_all > 10%` → `high_risk` ("X% of active trades show delinquency in 24M")

**Composite findings** (`_composite_findings`):
- Cross-checks 6M/9M DPD windows against portfolio max DPD to detect re-occurring delinquency
- Checks `months_since_last_0p_uns` / `months_since_last_0p_pl` for recency of last clean payment

---

### 1.7 Scorecard (`tools/scorecard.py`)

The `compute_scorecard()` function translates findings into the traffic-light dashboard:

| Signal | Green | Amber | Red |
|---|---|---|---|
| Max DPD | 0 days | 1–30 days | >30 days |
| Missed Payments (18M) | 0% | >0% | >10% |
| Forced Events (WRF/SET/SMA/…) | none | SUB/DBT | WRF/SET/SMA |

**Override rule**: Any WRF, SET, or SMA forced event → verdict forced to **HIGH RISK** regardless of other signals.

---

### 1.8 Excel Export (`tools/excel_exporter.py`)

Two delinquency-derived columns written to the batch Excel report:

| Column | Source | Logic |
|---|---|---|
| `Max DPD & Product` | `bureau_report.executive_inputs` | `"{max_dpd}d DPD / {loan_type} / {months_ago}M ago"` |
| `Payments Missed in l 18M` | `bureau_report.tradeline_features` | `pct_missed_payments_18m` (rounded to 2 dp) |

---

### 1.9 Detection Flow (Summary)

```
dpd_data.csv
    │
    ├─ bureau_feature_extractor.py
    │     _compute_max_dpd()            → delinquency_flag, max_dpd, max_dpd_months_ago
    │     _extract_forced_event_flags() → WRF/SET/SMA/SUB/DBT/LSS/WOF
    │     _build_feature_vector()       → BureauLoanFeatureVector (per loan type)
    │
    ├─ bureau_feature_aggregator.py
    │     aggregate_bureau_features()   → BureauExecutiveSummaryInputs
    │                                      (portfolio max DPD, has_delinquency)
    │
    ├─ tl_features.csv (pre-computed)
    │     TradelineFeatures             → max_dpd_6m_cc/pl, max_dpd_9m_cc
    │                                      pct_missed_payments_18m
    │                                      months_since_last_0p_uns/pl
    │                                      pct_0plus_24m_all/pl
    │
    ├─ key_findings.py
    │     extract_key_findings()        → KeyFinding list (severity-tagged, deterministic)
    │
    ├─ scorecard.py
    │     compute_scorecard()           → RAG signal + verdict (forced HIGH RISK on WRF/SET/SMA)
    │
    └─ excel_exporter.py
          build_excel_row()             → "Max DPD & Product", "Payments Missed in l 18M"
```

---

## 2. FOIR (Fixed Obligation to Income Ratio)

### Definition
`FOIR = (Total EMI + Rent) / Monthly Salary × 100`

### Salary Source Priority (consistent across scorecard and Excel export)
1. `rg_salary_data["rg_sal"]["salary_amount"]` — internal RG algorithm output (preferred)
2. `customer_report.salary.avg_amount` — banking-detected salary (fallback)

### Where FOIR is Computed

| Location | Function | Purpose |
|---|---|---|
| `tools/scorecard.py` | `compute_scorecard()` | RAG signal for the dashboard (green <40%, amber 40–65%, red >65%) |
| `tools/excel_exporter.py` | `build_excel_row()` | Written to `Foir` column in the batch Excel output (raw ratio, 4 dp) |

### Thresholds (Scorecard)
- **Green**: FOIR < 40% — comfortable repayment capacity
- **Amber**: 40% ≤ FOIR ≤ 65% — moderate obligation load
- **Red**: FOIR > 65% — over-leveraged, limited repayment buffer

### Verify Trigger
If FOIR > 50%, the scorecard adds `"Cross-verify income source"` to the Verify column to prompt analyst review.

---

## 3. Exposure Trend Flag (12-Month)

### Feature
Two independent RAG-tagged chips in the scorecard signal grid:

| Chip | Question answered | Shown when |
|---|---|---|
| **Exposure 12M** | Has total sanctioned exposure grown vs exactly 12M ago? | ≥ 13 months of data |
| **Exposure 6M** | Has the last-6M average grown vs the prior-6M average? | ≥ 7 months of data |

If a window has insufficient history, that chip is silently omitted. Both chips can appear together when 13+ months of data are available.

---

### Implementation Steps

#### Step 1 — Understand the existing data structure
Read `pipeline/reports/report_summary_chain.py` (`summarize_exposure_timeline`) and `pipeline/renderers/bureau_pdf_renderer.py` to confirm the shape of `monthly_exposure`:

```python
monthly_exposure = {
    "months": ["Apr 2024", "May 2024", ..., "Mar 2026"],  # up to 24 labels
    "series": {
        "PL": [amt_apr24, amt_may24, ..., amt_mar26],
        "CC": [...],
        ...
    }
}
```

`BureauReport.monthly_exposure` carries this dict; it is already populated by the bureau pipeline and passed to the chart renderer.

#### Step 2 — Understand the scorecard signal pattern
Read `tools/scorecard.py`. Each signal in the `signals` list is a dict:

```python
{"label": str, "value": str, "rag": "green"|"amber"|"red"|"neutral", "note": str}
```

`_bureau_signals(bureau_report)` builds the bureau side; signals are appended in order and rendered by the Jinja2 scorecard block in all three templates without any template changes.

#### Step 3 — Choose the computation approach
Two options considered:
- **LLM narrative** — rejected (adds latency, no determinism needed)
- **Deterministic math** on `monthly_exposure["series"]` — chosen

Each window is computed independently so both can appear at once:
- **12M**: compare `totals[-1]` (current) vs `totals[-13]` (exactly 12M ago) — requires `n >= 13`
- **6M**: compare last-6M avg vs prior-6M avg — requires `n >= 7`
- If a window lacks data, that chip is omitted (no fallback substitution)

#### Step 4 — Write `_exposure_signals()` in `tools/scorecard.py`

Added above `_bureau_signals()` (with shared `_rag_exposure()` helper to avoid duplicating the threshold logic):

```python
def _rag_exposure(pct_change: float) -> tuple[str, str]:
    """Return (rag, direction_label) for an exposure % change."""
    ...

def _exposure_signals(monthly_exposure: dict) -> list:
    chips = []
    # 12M chip
    if n >= 13:
        pct_12m = (totals[-1] - totals[-13]) / totals[-13] * 100
        rag, direction = _rag_exposure(pct_12m)
        chips.append({"label": "Exposure 12M", "value": direction, "rag": rag, "note": "vs 12M ago"})
    # 6M chip
    if n >= 7:
        pct_6m = (recent_6m_avg - prior_6m_avg) / prior_6m_avg * 100
        rag, direction = _rag_exposure(pct_6m)
        chips.append({"label": "Exposure 6M", "value": direction, "rag": rag, "note": "6M avg trend"})
    return chips
```

RAG thresholds (lender perspective — growing debt = risk):

| % Change | RAG | Value displayed |
|---|---|---|
| ≤ −5% | green | `↓ X% declining` |
| −5% to +5% | neutral | `Stable` |
| +5% to +30% | amber | `↑ X% growing` |
| > +30% | red | `↑ X% rapid growth` |

#### Step 5 — Wire into `_bureau_signals()` as signals #7–8

Replaced the single `append` with `extend` at the end of the function (after Adverse Events):

```python
# 7–8. Exposure Trend (12M point-in-time + 6M avg — each shown only if data available)
signals.extend(_exposure_signals(getattr(bureau_report, "monthly_exposure", None)))
```

`getattr` used defensively so it does not raise if `monthly_exposure` is absent.

#### Step 6 — Verify no template changes needed
The scorecard Jinja2 block already iterates `{% for s in scorecard.signals %}` and renders every chip generically. Adding a new signal to the list is sufficient — no HTML edits required.

---

### Files Changed

| File | Change |
|---|---|
| `tools/scorecard.py` | Added `_rag_exposure()` + `_exposure_signals()` functions; wired into `_bureau_signals()` as signals #7–8 |
| `pipeline/reports/report_summary_chain.py` | See Section 3.1 below |
| `tools/bureau.py` | Passes `monthly_exposure` to `generate_bureau_review()` |

### Files NOT Changed (intentionally)
| File | Reason |
|---|---|
| `templates/bureau_report.html` | Scorecard block renders all signals generically — no edit needed |
| `templates/combined_report.html` | Same |
| `templates/customer_report.html` | Same |
| `pipeline/reports/report_summary_chain.py` | Existing `summarize_exposure_timeline()` retained for the 2-line chart caption — serves a different purpose |

---

### Data Flow

```
BureauReport.monthly_exposure
    │
    ├─ tools/scorecard.py
    │     _rag_exposure()          → shared RAG threshold helper
    │     _exposure_signals()      → computes 12M + 6M chips independently
    │     _bureau_signals()        → extends signals list with available chips
    │     compute_scorecard()      → included in signals[] list
    │         │
    │         └─ templates (all 3 reports)
    │               {% for s in scorecard.signals %}  → renders chips generically
    │
    └─ pipeline/reports/report_summary_chain.py
          _build_bureau_data_summary()  → appends trend lines to LLM data block
          generate_bureau_review()      → LLM reads trend lines → bureau narrative
              │
              └─ BureauReport.narrative → combined_summary (via combined report)
```

---

### 3.1 Feeding Exposure Trend into the Bureau Executive Summary

The exposure trend is also injected into the **LLM data summary** so the bureau narrative and combined summary mention it in plain English.

#### Steps followed

**Step 1 — Locate the LLM data assembly function**
`generate_bureau_review()` in `report_summary_chain.py` calls `_build_bureau_data_summary(executive_inputs, tradeline_features)` to build the text block fed to the LLM. The `monthly_exposure` dict was not being passed in at all.

**Step 2 — Extract shared `_inr()` helper to module level**
The INR formatter was a local closure inside `summarize_exposure_timeline()`. Moved it to module scope so `_build_bureau_data_summary()` can use it without duplication.

**Step 3 — Add `monthly_exposure` param to `_build_bureau_data_summary()`**
Appended a new `"Sanctioned Exposure Trend:"` block at the end of the data summary lines:

```
Sanctioned Exposure Trend:
  Sanctioned exposure 12M trend: increased by 23% (₹12.3L → ₹15.1L)
  Sanctioned exposure 6M avg trend: decreased by 8% (prior 6M avg ₹15.4L → recent 6M avg ₹14.2L)
```

Each line only appears if its window has enough data (`n >= 13` for 12M, `n >= 7` for 6M) — same data-availability rules as the scorecard chips.

**Step 4 — Thread `monthly_exposure` through `generate_bureau_review()`**
Added `monthly_exposure=None` param and passed it to `_build_bureau_data_summary()`.

**Step 5 — Update the call site in `tools/bureau.py`**
The one call to `generate_bureau_review()` now passes `monthly_exposure=report.monthly_exposure`.

Because `BureauReport.narrative` flows into `generate_combined_executive_summary()` as `bureau_summary`, the trend commentary automatically propagates into the combined report's executive summary with no further changes.

#### Files changed

| File | Change |
|---|---|
| `pipeline/reports/report_summary_chain.py` | Extracted `_inr()` to module scope; added `monthly_exposure` param to `_build_bureau_data_summary()` and `generate_bureau_review()`; appended trend lines to data summary |
| `tools/bureau.py` | Passes `monthly_exposure=report.monthly_exposure` to `generate_bureau_review()` |

---

## 4. Batch Report Generation + Master Excel

### Overview

Run `batch_reports.py` once to generate combined reports (HTML + PDF) for any number of customers and produce a single merged Excel file with one row per customer.

---

### How to Run

**Option A — All customers in `data/rgs.csv` (default)**
```bash
python batch_reports.py
```
Output Excel: `reports/batch_output.xlsx`

**Option B — Specific CRNs on the command line**
```bash
python batch_reports.py --crns 100070028 200001234 300005678
```

**Option C — CRN list from a text file (one per line)**
```bash
python batch_reports.py --crn-file path/to/crns.txt
```

**Custom output path**
```bash
python batch_reports.py --output reports/march_batch.xlsx
```

---

### What Happens Per Customer

For each CRN `batch_reports.py` calls `generate_combined_report_pdf(crn)` in `tools/combined_report.py`, which runs these steps in order:

| Step | Action | Output |
|---|---|---|
| 1 | Generate banking report (uses cache if already built) | `CustomerReport` object |
| 2 | Generate bureau report (uses cache if already built) | `BureauReport` object |
| 3 | Generate combined executive summary via LLM (fail-soft) | `combined_summary` string |
| 4 | Load internal RG salary data (fail-soft) | `rg_salary_data` dict |
| 5 | Render combined HTML + PDF | `reports/html/{crn}.html` |
| 6 | Build and write per-customer Excel row | `reports/excel/{crn}.xlsx` |

If any step fails for a customer, that customer is logged as failed and processing continues with the next CRN.

---

### Per-Customer Excel Row (`tools/excel_exporter.py`)

`build_excel_row()` maps report data onto 18 fixed columns (defined in `TEMPLATE_COLUMNS`):

| Column | Source | Notes |
|---|---|---|
| `CRN` | `customer_id` | |
| `offer Amt` | — | Left blank for manual fill |
| `Salary Value & Company` | `rg_sal` → `customer_report.salary` | Prefers RG algorithm output |
| `Assesement Strength & Quality` | — | Left blank for analyst override |
| `Relationship` | `rg_sal.method` / `pension_flag` | "Corp SAL" / "Pension SAL" / "Salary" |
| `Event Detector` | `customer_report.events` | Pipe-separated event list |
| `Summary` | `combined_summary` | LLM executive summary |
| `Bureau Brief` | `bureau_report.narrative` | Bureau LLM narrative |
| `Banking Breif` | `customer_report.customer_review` | Banking LLM narrative |
| `Bu & Banking Segment` | `tradeline_features.customer_segment` + `account_quality.account_type` | |
| `Max DPD & Product` | `executive_inputs.max_dpd` | Format: `"30d DPD / PL / 6M ago"` |
| `CC Util` | `tradeline_features.cc_balance_utilization_pct` | Rounded to 2 dp |
| `Enquiries` | `tradeline_features.unsecured_enquiries_12m` | |
| `Payments Missed in l 18M` | `tradeline_features.pct_missed_payments_18m` | Rounded to 2 dp |
| `Foir` | `(EMI + Rent) / salary` | Salary: rg_sal first, then banking; raw ratio 4 dp |
| `Transaction Red flag` | `category_overview["Digital_Betting_Gaming"]` | Total INR amount |
| `Concerns` | `bureau_report.key_findings` (high/moderate severity) | Pipe-separated |
| `Intelligent Report` | HTML file path | `.pdf` extension replaced with `.html` |

`export_row_to_excel(row, path)` writes the single-row `.xlsx` to `reports/excel/{crn}.xlsx`.

---

### Merge Step (`tools/excel_exporter.py` → `merge_excel_reports()`)

After all CRNs are processed, `run_batch()` calls:

```python
merge_excel_reports(excel_dir="reports/excel/", output_path="reports/batch_output.xlsx")
```

This:
1. Globs all `*.xlsx` files in `reports/excel/`
2. Reads each with `pd.read_excel()`
3. Concatenates with `pd.concat(frames, ignore_index=True)`
4. Enforces column order (`TEMPLATE_COLUMNS`) — adds missing cols as empty, drops extras
5. Writes the merged DataFrame to the output path

The merge is additive — if you run a second batch later and re-merge, rows accumulate. To get a clean master file, clear `reports/excel/` first.

---

### Output Files

```
reports/
├── excel/
│   ├── 100070028.xlsx    ← per-customer (one row each)
│   ├── 200001234.xlsx
│   └── ...
├── html/
│   ├── 100070028.html    ← combined report (Intelligent Report link)
│   └── ...
└── batch_output.xlsx     ← master merged file (all customers, 18 columns)
```

---

### Fault Tolerance

- A failing customer (any exception in `generate_combined_report_pdf`) is **logged and skipped** — it does not abort the batch.
- If the per-customer Excel write fails (step 6), it is also fail-soft — the HTML/PDF are still written.
- The merge step only runs if at least one `.xlsx` file exists in `reports/excel/`.
- Partial batches are safe: already-generated per-customer files are re-used on retry (report cache hit), and the new merge replaces the previous master file.

---

### Key Files

| File | Role |
|---|---|
| `batch_reports.py` | CLI entry point — parses args, calls `run_batch()` |
| `tools/combined_report.py` | Per-customer orchestration — generates report + writes Excel row |
| `tools/excel_exporter.py` | `build_excel_row()`, `export_row_to_excel()`, `merge_excel_reports()` |
| `data/loader.py` | `get_transactions_df()` — used to auto-discover CRNs from `data/rgs.csv` |

---

### End-to-End Flow

```
batch_reports.py (CLI)
    │
    ├─ _load_crns_from_csv()          ← if no --crns / --crn-file given
    │     data/rgs.csv → unique cust_id list
    │
    └─ run_batch(crns, output_excel)
          │
          ├─ for each CRN:
          │     generate_combined_report_pdf(crn)   [tools/combined_report.py]
          │         ├─ generate_customer_report_pdf()  → CustomerReport
          │         ├─ generate_bureau_report_pdf()    → BureauReport
          │         ├─ generate_combined_executive_summary()  → combined_summary
          │         ├─ load_rg_salary_data()           → rg_salary_data
          │         ├─ render_combined_report()        → reports/html/{crn}.html
          │         └─ build_excel_row() + export_row_to_excel()
          │                                           → reports/excel/{crn}.xlsx
          │
          └─ merge_excel_reports()   [tools/excel_exporter.py]
                reports/excel/*.xlsx → reports/batch_output.xlsx
```
