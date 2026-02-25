"""Tradeline feature extraction from pre-computed tl_features.csv.

Loads tl_features.csv (tab-separated), looks up a customer by crn,
and returns a TradelineFeatures dataclass.

All logic is deterministic — no LLM, no formatting.
"""

import csv
from typing import List, Optional

from features.tradeline_features import TradelineFeatures
from config.settings import TL_FEATURES_FILE, TL_FEATURES_DELIMITER

# Module-level cache for tl_features CSV
_tl_features_df: Optional[List[dict]] = None

# CSV column name → dataclass field name mapping
_COLUMN_MAP = {
    "monsnclasttrop_pl_onc": "months_since_last_trade_pl",
    "monsnclasttrop_uns_onc": "months_since_last_trade_uns",
    "no_tr_open_l6m_pl_onc": "new_trades_6m_pl",
    "no_trades_all_onc": "total_trades",
    "max_dpd_l6m_cc_onc": "max_dpd_6m_cc",
    "max_dpd_l6m_pl_onc": "max_dpd_6m_pl",
    "max_dpd_l9m_cc_onc": "max_dpd_9m_cc",
    "mon_sin_last_0p_uns_op": "months_since_last_0p_uns",
    "monsinlast_0p_pl_onc": "months_since_last_0p_pl",
    "pct_0p_l24m_all_onc": "pct_0plus_24m_all",
    "pct_0p_l24m_pl_onc": "pct_0plus_24m_pl",
    "pct_missed_pymt_last18m_all": "pct_missed_payments_18m",
    "pct_tr_0p_l12m_all_onc": "pct_trades_0plus_12m",
    "ratio_good_closed_loans_pl": "ratio_good_closed_pl",
    "pct_bal_cc_lv": "cc_balance_utilization_pct",
    "pct_bal_pl_lv": "pl_balance_remaining_pct",
    "uns_enq_l12m": "unsecured_enquiries_12m",
    "tr_to_enq_ratio_uns_l24m": "trade_to_enquiry_ratio_uns_24m",
    "interpurchase_time_l12m_plbl": "interpurchase_time_12m_plbl",
    "interpurchase_time_l6m_plbl": "interpurchase_time_6m_plbl",
    "interpurchase_time_l24m_all": "interpurchase_time_24m_all",
    "interpurchase_time_l9m_hl_lap": "interpurchase_time_9m_hl_lap",
    "interpurchase_time_l24m_hl_lap": "interpurchase_time_24m_hl_lap",
    "interpurchase_time_l24m_twl": "interpurchase_time_24m_twl",
    "interpurchase_time_l12m_cl": "interpurchase_time_12m_cl",
    # Customer profile
    "ktk_rel": "ktk_rel",
    "customer_segment_1_ordered": "customer_segment",
    "bank_grp": "bank_grp",
    "bu_grp": "bu_grp",
    "affluence_amt_6": "affluence_amt",
    "income_source_new": "income_source",
    "node": "node",
}

# Fields that should be parsed as int (rest are float)
_INT_FIELDS = {
    "new_trades_6m_pl", "total_trades", "max_dpd_6m_cc",
    "max_dpd_6m_pl", "max_dpd_9m_cc", "unsecured_enquiries_12m",
}

# Fields that should be kept as plain strings
_STR_FIELDS = {
    "ktk_rel", "customer_segment", "bank_grp", "bu_grp", "income_source", "node",
}


def _load_tl_features(force_reload: bool = False) -> List[dict]:
    """Load and cache tradeline features data."""
    global _tl_features_df
    if _tl_features_df is None or force_reload:
        with open(TL_FEATURES_FILE, "r") as f:
            reader = csv.DictReader(f, delimiter=TL_FEATURES_DELIMITER)
            _tl_features_df = list(reader)
    return _tl_features_df


def _safe_optional_str(value: str) -> Optional[str]:
    """Return stripped string, or None for NULL/empty values."""
    if not value or value.strip().upper() in ("NULL", ""):
        return None
    return value.strip()


def _safe_optional_float(value: str) -> Optional[float]:
    """Parse a string to float, returning None for NULL/empty/invalid."""
    if not value or value.strip().upper() in ("NULL", ""):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_optional_int(value: str) -> Optional[int]:
    """Parse a string to int, returning None for NULL/empty/invalid."""
    if not value or value.strip().upper() in ("NULL", ""):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def extract_tradeline_features(customer_id: int) -> Optional[TradelineFeatures]:
    """Extract pre-computed tradeline features for a customer.

    Args:
        customer_id: The CRN from bureau data.

    Returns:
        TradelineFeatures dataclass, or None if customer not found.
    """
    all_rows = _load_tl_features()

    # Find matching row (one row per customer)
    matching_row = None
    for row in all_rows:
        crn_val = row.get("crn", "").strip()
        if not crn_val or crn_val.upper() == "NULL":
            continue
        try:
            if int(float(crn_val)) == customer_id:
                matching_row = row
                break
        except (ValueError, TypeError):
            continue

    if matching_row is None:
        return None

    # Build kwargs from column map
    kwargs = {}
    for csv_col, field_name in _COLUMN_MAP.items():
        raw_value = matching_row.get(csv_col, "")
        if field_name in _INT_FIELDS:
            kwargs[field_name] = _safe_optional_int(raw_value)
        elif field_name in _STR_FIELDS:
            kwargs[field_name] = _safe_optional_str(raw_value)
        else:
            kwargs[field_name] = _safe_optional_float(raw_value)

    # --- Cross-field consistency fixes ---
    # PL is unsecured: if unsecured 0+ DPD is N/A but PL has a value, use PL
    if kwargs.get("months_since_last_0p_uns") is None and kwargs.get("months_since_last_0p_pl") is not None:
        kwargs["months_since_last_0p_uns"] = kwargs["months_since_last_0p_pl"]

    # 9M CC window includes 6M: if 6M has DPD but 9M is None, use 6M value
    dpd_6m_cc = kwargs.get("max_dpd_6m_cc")
    dpd_9m_cc = kwargs.get("max_dpd_9m_cc")
    if dpd_6m_cc is not None and dpd_9m_cc is not None:
        if dpd_9m_cc < dpd_6m_cc:
            kwargs["max_dpd_9m_cc"] = dpd_6m_cc
    elif dpd_6m_cc is not None and dpd_9m_cc is None:
        kwargs["max_dpd_9m_cc"] = dpd_6m_cc

    # Subset validation: PL is subset of All — pct_0plus_24m_pl cannot exceed pct_0plus_24m_all
    pct_all = kwargs.get("pct_0plus_24m_all")
    pct_pl = kwargs.get("pct_0plus_24m_pl")
    if pct_all is not None and pct_pl is not None and pct_pl > pct_all:
        kwargs["pct_0plus_24m_all"] = pct_pl

    return TradelineFeatures(**kwargs)
