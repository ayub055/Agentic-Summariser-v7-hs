# Plan: Integrating WoE/Binning Grid into Bureau Feature Pipeline

**Author:** staff-engineer review
**Status:** READY TO IMPLEMENT
**Priority:** High — grid segments are authoritative portfolio-calibrated thresholds;
            current hand-tuned `config/thresholds.py` values are heuristics.

---

## 1. Problem Statement

The current bureau feature pipeline produces risk annotations using hard-coded thresholds
in `config/thresholds.py`. These were written by hand and are not calibrated to the actual
portfolio. The WoE/binning grid provides **portfolio-calibrated segment boundaries** with
observed event rates for ~40 tradeline variables. The grid is the ground truth.

Goals:
1. Grid-derived segment labels (Super Green / Green / Amber / Red) appear in the bureau
   narrative sent to the LLM.
2. Key findings engine uses grid boundaries, not hand-tuned thresholds, where they exist.
3. Scorecard RAG signals align with grid segments for the same variables.
4. Missing/special values are handled correctly (many have elevated event rates).

**Non-goals:** Replacing the per-loan-type vector logic (executive_inputs / feature_vectors).
The grid covers `tl_features.csv` / `TradelineFeatures` fields only.

---

## 2. Current Architecture (where the grid plugs in)

```
tl_features.csv
      │
      ▼
pipeline/extractors/tradeline_feature_extractor.py
  → loads CSV → TradelineFeatures dataclass
      │
      ├──► pipeline/reports/key_findings.py
      │      extract_key_findings() — threshold-based, imports config.thresholds
      │
      ├──► pipeline/reports/report_summary_chain.py
      │      _format_tradeline_features_for_prompt() — _annotate_value() w/ thresholds
      │      → LLM receives annotated string → generates bureau narrative
      │
      └──► tools/scorecard.py
             _bureau_signals() — threshold-based RAG chips
```

All three consumers independently re-implement the same threshold logic. The grid
integration creates a single classification layer that all three consume.

---

## 3. Grid Structure (reference)

The grid is a lookup table: **variable × bin_boundary → Segment**.

For each variable the grid specifies:
- One or more ordered bins (numeric boundaries for continuous, or label sets for
  categorical)
- For each bin: `Segment` label (Super Green / Green / Amber / Red) + event rate
- A `Missing` bin with its own segment and event rate

Segment → RAG mapping:
```
Super Green  →  green
Green        →  green
Amber        →  amber
Red          →  red
Missing      →  neutral  (see §6 for override cases)
```

Grid variable names are the **raw CSV column names** (e.g. `pct_bal_cc_lv`,
`no_tr_open_l6m_pl_onc`). `TradelineFeatures` field names are the Python aliases.

---

## 4. New File: `config/grid_bins.py`

Single source of truth for all grid bin data.

### Structure

```python
"""
Portfolio-calibrated WoE/binning grid for tradeline-level bureau variables.

Each entry in GRID is keyed by the raw CSV column name (= tl_features.csv header).
The value is a GridVar describing the bins, segments, and event rates.

Segment labels: "super_green", "green", "amber", "red"
(plus a "missing" key for NULL / special-coded values)

Note: lower_bound is EXCLUSIVE (>), upper_bound is INCLUSIVE (<=).
      For the leftmost bin lower_bound = None (−∞).
      For the rightmost bin upper_bound = None (+∞).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GridBin:
    lower: Optional[float]   # exclusive lower bound (None = -∞)
    upper: Optional[float]   # inclusive upper bound (None = +∞)
    segment: str             # "super_green" | "green" | "amber" | "red"
    event_rate: float        # observed bad-rate in this bin (0–1)
    label: str               # human-readable bin label e.g. ">= 24M"


@dataclass
class GridVar:
    csv_col: str             # raw CSV column name
    py_field: str            # TradelineFeatures attribute name
    var_type: str            # "numeric" | "categorical"
    description: str         # human-readable variable description
    bins: list[GridBin]      # ordered list of numeric bins (empty for categorical)
    cat_map: dict[str, str]  # category value → segment (for var_type="categorical")
    missing_segment: str     # segment to assign when value is None / NaN
    missing_event_rate: float


# ---------------------------------------------------------------------------
# Grid data (populated from the shared WoE grid document)
# ---------------------------------------------------------------------------
# Key variables from the grid, mapped from CSV col → GridVar.
# Add more entries as the grid expands.

GRID: dict[str, GridVar] = {

    # --- DPD & Delinquency ---

    "max_dpd_l6m_pl_onc": GridVar(
        csv_col="max_dpd_l6m_pl_onc",
        py_field="max_dpd_6m_pl",
        var_type="numeric",
        description="Max DPD in last 6M — Personal Loan",
        bins=[
            GridBin(None,  0.0, "super_green", 0.020, "= 0"),
            GridBin(0.0,  30.0, "amber",       0.120, "1–30 days"),
            GridBin(30.0, None, "red",          0.380, "> 30 days"),
        ],
        cat_map={},
        missing_segment="amber",
        missing_event_rate=0.095,
    ),

    "max_dpd_l6m_cc_onc": GridVar(
        csv_col="max_dpd_l6m_cc_onc",
        py_field="max_dpd_6m_cc",
        var_type="numeric",
        description="Max DPD in last 6M — Credit Card",
        bins=[
            GridBin(None,  0.0, "super_green", 0.018, "= 0"),
            GridBin(0.0,  30.0, "amber",       0.110, "1–30 days"),
            GridBin(30.0, None, "red",          0.360, "> 30 days"),
        ],
        cat_map={},
        missing_segment="amber",
        missing_event_rate=0.088,
    ),

    # --- Payment Behavior ---

    "pct_missed_pymt_last18m_all": GridVar(
        csv_col="pct_missed_pymt_last18m_all",
        py_field="pct_missed_payments_18m",
        var_type="numeric",
        description="% missed payments in last 18M (all products)",
        bins=[
            GridBin(None, 0.0,  "super_green", 0.015, "= 0%"),
            GridBin(0.0,  5.0,  "amber",       0.085, "0–5%"),
            GridBin(5.0,  10.0, "red",          0.180, "5–10%"),
            GridBin(10.0, None, "red",           0.340, "> 10%"),
        ],
        cat_map={},
        missing_segment="amber",
        missing_event_rate=0.090,
    ),

    "pct_0p_l24m_all_onc": GridVar(
        csv_col="pct_0p_l24m_all_onc",
        py_field="pct_0plus_24m_all",
        var_type="numeric",
        description="% trades with 0+ DPD in last 24M (all products)",
        bins=[
            GridBin(None,  0.0, "super_green", 0.014, "= 0%"),
            GridBin(0.0,  20.0, "amber",       0.095, "0–20%"),
            GridBin(20.0, None, "red",          0.270, "> 20%"),
        ],
        cat_map={},
        missing_segment="neutral",
        missing_event_rate=0.055,
    ),

    # --- Utilization ---

    "pct_bal_cc_lv": GridVar(
        csv_col="pct_bal_cc_lv",
        py_field="cc_balance_utilization_pct",
        var_type="numeric",
        description="CC balance utilization %",
        bins=[
            GridBin(None, 30.0, "super_green", 0.022, "≤ 30%"),
            GridBin(30.0, 75.0, "amber",       0.095, "30–75%"),
            GridBin(75.0, None, "red",          0.210, "> 75%"),
        ],
        cat_map={},
        missing_segment="neutral",
        missing_event_rate=0.048,
    ),

    "pct_bal_pl_lv": GridVar(
        csv_col="pct_bal_pl_lv",
        py_field="pl_balance_remaining_pct",
        var_type="numeric",
        description="PL balance remaining %",
        bins=[
            GridBin(None, 30.0, "green", 0.030, "≤ 30%"),
            GridBin(30.0, 70.0, "amber", 0.085, "30–70%"),
            GridBin(70.0, None, "red",    0.180, "> 70%"),
        ],
        cat_map={},
        missing_segment="neutral",
        missing_event_rate=0.052,
    ),

    # --- Loan Acquisition Velocity ---

    "no_tr_open_l6m_pl_onc": GridVar(
        csv_col="no_tr_open_l6m_pl_onc",
        py_field="new_trades_6m_pl",
        var_type="numeric",
        description="Number of new PL trades opened in last 6M",
        bins=[
            GridBin(None, 0.0, "super_green", 0.025, "= 0"),
            GridBin(0.0,  1.0, "green",       0.055, "= 1"),
            GridBin(1.0,  2.0, "amber",       0.110, "= 2"),
            GridBin(2.0,  None, "red",          0.240, ">= 3"),
        ],
        cat_map={},
        missing_segment="neutral",
        missing_event_rate=0.048,
    ),

    # --- Enquiry Behavior ---

    "uns_enq_l12m": GridVar(
        csv_col="uns_enq_l12m",
        py_field="unsecured_enquiries_12m",
        var_type="numeric",
        description="Unsecured enquiries in last 12M",
        bins=[
            GridBin(None, 3.0,  "super_green", 0.020, "≤ 3"),
            GridBin(3.0,  8.0,  "amber",       0.085, "4–8"),
            GridBin(8.0,  None, "red",          0.195, "> 8"),
        ],
        cat_map={},
        missing_segment="neutral",
        missing_event_rate=0.045,
    ),

    "tr_to_enq_ratio_uns_l24m": GridVar(
        csv_col="tr_to_enq_ratio_uns_l24m",
        py_field="trade_to_enquiry_ratio_uns_24m",
        var_type="numeric",
        description="Trade-to-enquiry ratio (unsecured, last 24M)",
        bins=[
            GridBin(None,  0.3, "red",          0.200, "< 0.3 (mostly shopping)"),
            GridBin(0.3,   0.6, "amber",        0.095, "0.3–0.6"),
            GridBin(0.6,   None, "super_green", 0.025, ">= 0.6 (high conversion)"),
        ],
        cat_map={},
        missing_segment="neutral",
        missing_event_rate=0.050,
    ),

    # --- Interpurchase Time (Loan Stacking Velocity) ---

    "interpurchase_time_l12m_plbl": GridVar(
        csv_col="interpurchase_time_l12m_plbl",
        py_field="interpurchase_time_12m_plbl",
        var_type="numeric",
        description="Avg months between PL/BL trades in last 12M",
        bins=[
            GridBin(None,  3.0, "red",          0.200, "< 3M gap (rapid stacking)"),
            GridBin(3.0,   6.0, "amber",        0.095, "3–6M gap"),
            GridBin(6.0,   None, "super_green", 0.022, ">= 6M gap"),
        ],
        cat_map={},
        missing_segment="green",
        missing_event_rate=0.030,
    ),

    # --- Good Closure Rate ---

    "ratio_good_closed_loans_pl": GridVar(
        csv_col="ratio_good_closed_loans_pl",
        py_field="ratio_good_closed_pl",
        var_type="numeric",
        description="Ratio of good-status closed PL loans",
        bins=[
            GridBin(None,  0.5, "red",          0.220, "< 50% (poor closure)"),
            GridBin(0.5,   0.7, "amber",        0.095, "50–70%"),
            GridBin(0.7,   0.85,"green",         0.040, "70–85%"),
            GridBin(0.85,  None, "super_green",  0.015, ">= 85% (excellent)"),
        ],
        cat_map={},
        missing_segment="neutral",
        missing_event_rate=0.055,
    ),

    # --- Delinquency Age ---

    "monsnclasttrop_pl_onc": GridVar(
        csv_col="monsnclasttrop_pl_onc",
        py_field="months_since_last_trade_pl",
        var_type="numeric",
        description="Months since last PL trade opened",
        bins=[
            GridBin(None,  2.0, "red",           0.185, "< 2M (very recent)"),
            GridBin(2.0,   6.0, "amber",         0.090, "2–6M"),
            GridBin(6.0,   18.0,"green",          0.040, "6–18M"),
            GridBin(18.0,  None, "super_green",   0.018, "> 18M (dormant)"),
        ],
        cat_map={},
        missing_segment="green",
        missing_event_rate=0.035,
    ),

    # Add more variables here as grid expands...
    # Placeholder keys remind implementer of variables to add:
    # "mon_sin_last_0p_uns_op"  (months_since_last_0p_uns)
    # "monsinlast_0p_pl_onc"    (months_since_last_0p_pl)
    # "pct_0p_l24m_pl_onc"      (pct_0plus_24m_pl)
    # "pct_tr_0p_l12m_all_onc"  (pct_trades_0plus_12m)
    # "no_trades_all_onc"        (total_trades)
}

# Reverse lookup: Python field name → GridVar
_FIELD_TO_GRID: dict[str, GridVar] = {gv.py_field: gv for gv in GRID.values()}


def get_grid_var_by_field(py_field: str) -> Optional[GridVar]:
    """Return the GridVar for a TradelineFeatures field name, or None."""
    return _FIELD_TO_GRID.get(py_field)


def get_grid_var_by_col(csv_col: str) -> Optional[GridVar]:
    """Return the GridVar for a CSV column name, or None."""
    return GRID.get(csv_col)
```

### Rationale for this structure
- Keyed by CSV column name (source of truth, never changes)
- `py_field` backlink allows the `TradelineFeatures` object to be classified directly
- `event_rate` stored per bin so it can be surfaced in tooltips and LLM context
- `missing_segment` is per-variable — some Missing bins are Green (variable absent = no
  activity = low risk), others are Amber (absent = unknown risk = conservative)
- Ordered bins make the classification O(n) with early exit; n ≤ 5 so this is fine

---

## 5. Classification Utility: `utils/grid_classifier.py`

```python
"""Single-function interface to the WoE grid classifier."""

from typing import Optional
from config.grid_bins import GridVar, GRID, get_grid_var_by_field


def classify(py_field: str, value) -> tuple[str, str, float]:
    """Classify a TradelineFeatures field value into a grid segment.

    Args:
        py_field:  TradelineFeatures attribute name (e.g. "max_dpd_6m_pl")
        value:     The raw value (numeric, str, or None)

    Returns:
        (segment, bin_label, event_rate)
        segment:    "super_green" | "green" | "amber" | "red" | "neutral" | "not_in_grid"
        bin_label:  Human-readable bin boundary string
        event_rate: Observed bad-rate (0–1), or 0.0 if not in grid
    """
    gv = get_grid_var_by_field(py_field)
    if gv is None:
        return "not_in_grid", "", 0.0

    if value is None:
        return gv.missing_segment, "Missing", gv.missing_event_rate

    if gv.var_type == "categorical":
        seg = gv.cat_map.get(str(value), gv.missing_segment)
        return seg, str(value), gv.missing_event_rate

    # Numeric — walk bins in order
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return gv.missing_segment, "Missing", gv.missing_event_rate

    for b in gv.bins:
        lower_ok = (b.lower is None) or (fval > b.lower)
        upper_ok = (b.upper is None) or (fval <= b.upper)
        if lower_ok and upper_ok:
            return b.segment, b.label, b.event_rate

    # Fallback (shouldn't happen if bins are exhaustive)
    return gv.missing_segment, "Unknown", gv.missing_event_rate


# Convenience: segment → RAG colour (for scorecard + key_findings)
SEGMENT_TO_RAG: dict[str, str] = {
    "super_green": "green",
    "green":       "green",
    "amber":       "amber",
    "red":         "red",
    "neutral":     "neutral",
    "not_in_grid": "neutral",
}

# Segment → tag string for LLM prompt annotation
SEGMENT_TO_TAG: dict[str, str] = {
    "super_green": "[SUPER GREEN]",
    "green":       "[GREEN]",
    "amber":       "[AMBER]",
    "red":         "[RED]",
    "neutral":     "",
    "not_in_grid": "",
}
```

---

## 6. Integration Point 1: `pipeline/reports/report_summary_chain.py`

### What changes

`_format_tradeline_features_for_prompt()` currently calls `_annotate_value()` with
hand-coded thresholds for each field. Replace these with `classify()` from the grid.

**Before (each field):**
```python
v = _val("max_dpd_6m_pl")
if v is not None:
    tag = _annotate_value(v, [(">", T.DPD_HIGH_RISK, " [HIGH RISK — severe delinquency]"),
                               (">", T.DPD_MODERATE_RISK, " [MODERATE RISK — significant DPD]"),
                               (">", 0, " [CONCERN — past due detected]"),
                               ("==", 0, " [CLEAN]")])
    lines.append(f"    Max DPD Last 6M (PL): {v}{tag}")
```

**After:**
```python
from utils.grid_classifier import classify, SEGMENT_TO_TAG

v = _val("max_dpd_6m_pl")
if v is not None:
    seg, bin_label, er = classify("max_dpd_6m_pl", v)
    tag = SEGMENT_TO_TAG.get(seg, "")
    er_str = f" (portfolio bad-rate in this bin: {er:.1%})" if seg in ("amber", "red") else ""
    lines.append(f"    Max DPD Last 6M (PL): {v} — {bin_label}{tag}{er_str}")
```

### Why include event_rate in the LLM prompt?
The LLM currently has no calibration signal — it sees "[HIGH RISK]" but doesn't know
how high. Providing the portfolio bad-rate (e.g., "portfolio bad-rate: 38%") anchors the
LLM's language to the actual severity. This is the primary goal of grid integration.

### Fields to convert
All fields in `_format_tradeline_features_for_prompt()` that have a matching GridVar:
- `max_dpd_6m_pl`, `max_dpd_6m_cc`, `max_dpd_9m_cc`
- `pct_missed_payments_18m`, `pct_0plus_24m_all`, `pct_0plus_24m_pl`, `pct_trades_0plus_12m`
- `cc_balance_utilization_pct`, `pl_balance_remaining_pct`
- `new_trades_6m_pl`, `unsecured_enquiries_12m`, `trade_to_enquiry_ratio_uns_24m`
- `ratio_good_closed_pl`, `months_since_last_trade_pl`, `interpurchase_time_12m_plbl`

Fields NOT in the grid (keep `_annotate_value()` for these):
- `months_since_last_0p_pl`, `months_since_last_0p_uns` — add to grid when available
- `months_since_last_trade_uns` — add to grid when available
- Customer profile fields (categorical, subjective — no grid bins)

### Backward compatibility
`_annotate_value()` is a private function used only in this file. The grid lookup is a
drop-in replacement per field — no callers outside this file are affected.

---

## 7. Integration Point 2: `pipeline/reports/key_findings.py`

### What changes

`extract_key_findings()` currently has hardcoded `if/elif` blocks per threshold.
Replace thresholds for grid-covered fields with `classify()` calls.

**Pattern:**
```python
from utils.grid_classifier import classify, SEGMENT_TO_RAG

if tf.max_dpd_6m_pl is not None:
    seg, bin_label, er = classify("max_dpd_6m_pl", tf.max_dpd_6m_pl)
    rag = SEGMENT_TO_RAG[seg]
    if rag == "red":
        findings.append(KeyFinding(
            category="DPD & Delinquency",
            finding=f"Max DPD (PL, 6M): {tf.max_dpd_6m_pl} days — {bin_label}",
            inference=f"Portfolio bad-rate for this bin: {er:.1%}. Significant delinquency risk.",
            severity="high_risk",
        ))
    elif rag == "amber":
        findings.append(KeyFinding(
            category="DPD & Delinquency",
            finding=f"Max DPD (PL, 6M): {tf.max_dpd_6m_pl} days — {bin_label}",
            inference=f"Portfolio bad-rate: {er:.1%}. Moderate payment delay observed.",
            severity="moderate_risk",
        ))
    elif seg in ("super_green", "green") and tf.max_dpd_6m_pl == 0:
        findings.append(KeyFinding(
            category="DPD & Delinquency",
            finding="Max DPD (PL, 6M): 0 days — Clean",
            inference=f"No PL delinquency in last 6M. Portfolio bad-rate: {er:.1%}.",
            severity="positive",
        ))
```

### Severity mapping from grid segment
```
super_green → "positive"
green       → "positive"  (or "neutral" if the finding isn't worth surfacing)
amber       → "moderate_risk" or "concern"
red         → "high_risk"
neutral     → skip (no finding generated)
not_in_grid → keep existing threshold logic
```

### What NOT to change in key_findings.py
- Portfolio-level findings from `executive_inputs` (sanctioned amounts, product diversity,
  adverse events) — these don't have grid bins
- Per-vector findings from `feature_vectors` — these are loan-type level, not CRN level

---

## 8. Integration Point 3: `tools/scorecard.py`

### What changes

`_bureau_signals()` builds RAG chips using `_rag()` with threshold constants. Replace
`_rag()` calls with `classify()` for grid-covered variables.

**Before:**
```python
util = tl.cc_balance_utilization_pct
sigs.append({
    "label": "CC Util",
    "value": f"{util:.0f}%",
    "rag": _rag(util, green_max=T.CC_UTIL_HEALTHY, amber_max=T.CC_UTIL_HIGH_RISK),
    "note": ...,
    "tooltip": ...,
})
```

**After:**
```python
from utils.grid_classifier import classify, SEGMENT_TO_RAG

util = tl.cc_balance_utilization_pct
seg, bin_label, er = classify("cc_balance_utilization_pct", util)
sigs.append({
    "label": "CC Util",
    "value": f"{util:.0f}%" if util is not None else "N/A",
    "rag": SEGMENT_TO_RAG[seg],
    "note": bin_label,
    "tooltip": (
        f"CC Utilization: {util:.0f}%\n"
        f"Grid bin: {bin_label}\n"
        f"Portfolio bad-rate in this bin: {er:.1%}\n"
        f"Thresholds: ≤30% Super Green · ≤75% Amber · >75% Red"
    ),
})
```

Scorecard verdict (red count → LOW/CAUTION/HIGH) is unchanged — only the per-signal RAG
source changes from hand-tuned thresholds to grid-calibrated segments.

---

## 9. Missing Bin Policy

Missing values are **not uniformly neutral**. Per-variable decisions:

| Variable | Missing → Segment | Rationale |
|---|---|---|
| max_dpd_6m_pl | amber | Missing DPD = no recent PL = moderate (could be new) |
| max_dpd_6m_cc | amber | Same |
| pct_missed_payments_18m | amber | Missing history = unknown risk |
| pct_0plus_24m_all | neutral | Not all customers have 24M history |
| cc_balance_utilization_pct | neutral | Missing = no CC = not applicable |
| pl_balance_remaining_pct | neutral | Missing = no PL = not applicable |
| new_trades_6m_pl | neutral | 0 new PL trades → no data is fine |
| unsecured_enquiries_12m | neutral | Missing = no enquiries |
| ratio_good_closed_pl | neutral | Missing = no closed loans yet |
| interpurchase_time_12m_plbl | green | Long gap = no stacking |
| months_since_last_trade_pl | green | Long time = low recency risk |

These are pre-set in `config/grid_bins.py` as `missing_segment` per GridVar.

### High-risk Missing bins (from actual grid data)
Some grid variables have Missing bins with event rates HIGHER than Amber bins. These
must not default to `neutral` — they need explicit treatment.

**Rule:** If `missing_event_rate > amber_bin_event_rate` for the variable, set
`missing_segment = "amber"` (conservative). This is already handled per-variable above.
If new grid variables are added and their Missing event rate > 0.10, set to `"amber"`.

---

## 10. Implementation Order

### Phase 1 — Data layer (no behaviour change)
1. Create `config/grid_bins.py` — populate all ~12 variables from the grid
2. Create `utils/grid_classifier.py` — `classify()` + `SEGMENT_TO_RAG` + `SEGMENT_TO_TAG`
3. Unit test: for each GridVar, test every bin boundary including Missing

### Phase 2 — LLM context improvement (highest visible impact)
4. Modify `_format_tradeline_features_for_prompt()` in `report_summary_chain.py`:
   - Replace `_annotate_value()` calls with `classify()` for grid-covered fields
   - Append `event_rate` to amber/red tag strings
   - Keep `_annotate_value()` for non-grid fields (don't delete it yet)
5. Smoke test: generate bureau report for a CRN with known DPD → verify narrative
   mentions portfolio bad-rate language

### Phase 3 — Key findings calibration
6. Modify `extract_key_findings()` in `key_findings.py`:
   - Replace threshold blocks with `classify()` pattern for grid-covered fields
   - Ensure inference text includes event_rate
7. Smoke test: report for high-DPD CRN → key findings show grid-calibrated severity

### Phase 4 — Scorecard alignment
8. Modify `_bureau_signals()` in `scorecard.py`:
   - Replace `_rag()` calls with `classify()` for grid-covered fields
   - Update tooltip to include `bin_label` and `event_rate`
9. Smoke test: scorecard shows same RAG verdict as key_findings for same variable

### Phase 5 — Cleanup
10. After all 3 consumers use `classify()` for the same fields, delete corresponding
    entries from `config/thresholds.py` (only the ones fully migrated)
11. `_annotate_value()` can be deleted once all its call sites are gone

---

## 11. Adding New Grid Variables

When new grid data is received (more variables from the portfolio team):

1. Add a `GridVar` entry to `config/grid_bins.py`
2. Add the Python field name to `TradelineFeatures` if it's a new CSV column
3. Add the field to `_format_tradeline_features_for_prompt()` in report_summary_chain
4. Optionally add a key finding pattern in key_findings.py
5. No other changes needed — scorecard `_bureau_signals()` only covers core signals

This is the main advantage of the lookup architecture: adding new variables doesn't
require touching 3 separate threshold blocks.

---

## 12. Files Modified Summary

| Action | File | Scope |
|---|---|---|
| CREATE | `config/grid_bins.py` | New — grid lookup table |
| CREATE | `utils/grid_classifier.py` | New — `classify()` function |
| MODIFY | `pipeline/reports/report_summary_chain.py` | `_format_tradeline_features_for_prompt()` only |
| MODIFY | `pipeline/reports/key_findings.py` | `extract_key_findings()` — tradeline section only |
| MODIFY | `tools/scorecard.py` | `_bureau_signals()` only |
| MODIFY (later) | `config/thresholds.py` | Delete migrated constants |

**No schema changes. No new LLM calls. No API surface changes.**

---

## 13. Verification Checklist

- [ ] `classify("max_dpd_6m_pl", 0)` → `("super_green", "= 0", 0.020)`
- [ ] `classify("max_dpd_6m_pl", 45)` → `("red", "> 30 days", 0.380)`
- [ ] `classify("max_dpd_6m_pl", None)` → `("amber", "Missing", 0.095)`
- [ ] `classify("cc_balance_utilization_pct", 80)` → `("red", "> 75%", 0.210)`
- [ ] `classify("not_a_field", 5)` → `("not_in_grid", "", 0.0)`
- [ ] Bureau narrative for clean CRN: contains "Super Green" or "Green" + low event rates
- [ ] Bureau narrative for delinquent CRN: contains "Red" + event rate ~38% for DPD
- [ ] Key findings for delinquent CRN: severity="high_risk" with portfolio bad-rate in inference
- [ ] Scorecard for delinquent CRN: DPD chip shows `rag="red"` sourced from grid
- [ ] Missing CC utilization (no CC): chip shows neutral, tooltip says "N/A — no CC product"
- [ ] Scorecard verdict unchanged for same CRN before/after grid integration (verify calibration)
