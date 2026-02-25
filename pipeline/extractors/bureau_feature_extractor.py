"""Bureau feature extraction from raw tradeline data.

Loads dpd_data.csv, normalizes loan types, groups by canonical LoanType,
and computes one BureauLoanFeatureVector per loan type.

All logic is deterministic — no LLM, no formatting.
"""

import csv
import re
from collections import defaultdict
from datetime import datetime, date
from typing import Dict, List, Optional

from schemas.loan_type import (
    LoanType,
    normalize_loan_type,
    is_secured,
    ON_US_SECTORS,
)
from features.bureau_features import BureauLoanFeatureVector
from config.settings import BUREAU_DPD_FILE, BUREAU_DPD_DELIMITER

# Module-level cache for bureau CSV
_bureau_df: Optional[List[dict]] = None

# DPD flag columns in dpd_data.csv
_DPD_COLUMNS = [f"dpdf{i}" for i in range(1, 37)]

# Forced event codes in dpd_string (3-char patterns indicating non-standard events)
_KNOWN_FORCED_EVENTS = {"WRF", "SET", "SMA", "SUB", "DBT", "LSS", "WOF"}

# Pattern: 3 consecutive alpha chars in dpd_string
_ALPHA_PATTERN = re.compile(r"[A-Z]{3}")


def _load_bureau_data(force_reload: bool = False) -> List[dict]:
    """Load and cache bureau DPD data."""
    global _bureau_df
    if _bureau_df is None or force_reload:
        with open(BUREAU_DPD_FILE, "r") as f:
            reader = csv.DictReader(f, delimiter=BUREAU_DPD_DELIMITER)
            _bureau_df = list(reader)
    return _bureau_df


def _safe_float(value: str, default: float = 0.0) -> float:
    """Parse a string to float, returning default for NULL/empty/invalid."""
    if not value or value.strip().upper() in ("NULL", ""):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: str, default: int = 0) -> int:
    """Parse a string to int, returning default for NULL/empty/invalid."""
    if not value or value.strip().upper() in ("NULL", ""):
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _parse_date(value: str) -> Optional[date]:
    """Parse a date string safely. Tries DD-MM-YYYY first, then YYYY-MM-DD."""
    if not value or value.strip().upper() in ("NULL", ""):
        return None
    cleaned = value.strip().split(" ")[0]  # strip time part like "30-04-2024 00:00"
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _compute_months_since_last_payment(tradelines: List[dict]) -> Optional[int]:
    """Compute months since the most recent last_payment_date across tradelines."""
    today = date.today()
    latest_payment: Optional[date] = None

    for tl in tradelines:
        payment_date = _parse_date(tl.get("last_payment_date", ""))
        if payment_date is not None:
            if latest_payment is None or payment_date > latest_payment:
                latest_payment = payment_date

    if latest_payment is None:
        return None

    delta = (today.year - latest_payment.year) * 12 + (today.month - latest_payment.month)
    return max(0, delta)


def _compute_max_dpd(tradelines: List[dict]) -> tuple:
    """Find maximum DPD across all tradelines using pre-computed CSV columns.

    Reads `max_dpd` and `months_since_max_dpd` columns from dpd_data.csv
    (pre-computed per tradeline) and returns the portfolio max.

    Returns:
        (max_dpd, months_ago) — max_dpd is None if no DPD found,
        months_ago is months since that max DPD occurred.
    """
    best_val = 0
    best_months_ago = None
    found_any = False

    for tl in tradelines:
        val = _safe_int(tl.get("max_dpd", ""), default=0)
        if val > 0:
            found_any = True
            if val > best_val:
                best_val = val
                raw_months = tl.get("months_since_max_dpd", "")
                best_months_ago = _safe_int(raw_months) if raw_months and raw_months.strip().upper() not in ("NULL", "") else None

    if not found_any:
        return None, None
    return best_val, best_months_ago


def _extract_forced_event_flags(tradelines: List[dict]) -> List[str]:
    """Extract forced event flags from dpd_string across tradelines.

    Forced events are 3-character alpha codes in the dpd_string that are
    not standard markers (STD, XXX).
    """
    flags: set = set()

    for tl in tradelines:
        dpd_str = tl.get("dpd_string", "")
        matches = _ALPHA_PATTERN.findall(dpd_str)
        for m in matches:
            if m not in ("STD", "XXX"):
                flags.add(m)

    return sorted(flags)


def _compute_utilization_ratio(tradelines: List[dict], loan_type: LoanType) -> Optional[float]:
    """Compute utilization ratio for credit cards only.

    Utilization = total outstanding / total credit limit (for live tradelines).
    """
    if loan_type != LoanType.CC:
        return None

    total_outstanding = 0.0
    total_limit = 0.0

    for tl in tradelines:
        if tl.get("loan_status", "").strip() != "Live":
            continue
        limit = _safe_float(tl.get("creditlimit", ""))
        outstanding = _safe_float(tl.get("out_standing_balance", ""))
        if limit > 0:
            total_limit += limit
            total_outstanding += outstanding

    if total_limit <= 0:
        return None

    return round(total_outstanding / total_limit, 4)


def _build_feature_vector(
    loan_type: LoanType, tradelines: List[dict]
) -> BureauLoanFeatureVector:
    """Build a single feature vector for a group of tradelines of the same loan type."""
    loan_count = len(tradelines)
    # Secured if any tradeline in this group has a secured raw loan type
    secured = any(is_secured(tl.get("loan_type_new", "")) for tl in tradelines)

    total_sanctioned = sum(_safe_float(tl.get("sanction_amount", "")) for tl in tradelines)
    total_outstanding = sum(_safe_float(tl.get("out_standing_balance", "")) for tl in tradelines)

    # Vintage from tl_vin_1 (months)
    vintages = [_safe_float(tl.get("tl_vin_1", "")) for tl in tradelines]
    valid_vintages = [v for v in vintages if v > 0]
    avg_vintage = round(sum(valid_vintages) / len(valid_vintages), 1) if valid_vintages else 0.0

    # Live / Closed counts — ensure live + closed = total for consistency
    # Anything not explicitly "Closed" is treated as live (includes Live, Written-Off, etc.)
    closed_count = sum(1 for tl in tradelines if tl.get("loan_status", "").strip() == "Closed")
    live_count = loan_count - closed_count

    # DPD and delinquency
    max_dpd, max_dpd_months_ago = _compute_max_dpd(tradelines)
    delinquency_flag = max_dpd is not None and max_dpd > 0

    # Overdue
    overdue_amount = sum(_safe_float(tl.get("over_due_amount", "")) for tl in tradelines)

    # Utilization (CC only)
    utilization_ratio = _compute_utilization_ratio(tradelines, loan_type)

    # Forced events
    forced_event_flags = _extract_forced_event_flags(tradelines)

    # On-us / Off-us
    on_us_count = sum(1 for tl in tradelines if tl.get("sector", "").strip() in ON_US_SECTORS)
    off_us_count = loan_count - on_us_count

    # Months since last payment
    months_since_last_payment = _compute_months_since_last_payment(tradelines)

    # Timeline: earliest/latest opened and latest closed
    opened_dates = [_parse_date(tl.get("date_opened", "")) for tl in tradelines]
    closed_dates = [_parse_date(tl.get("date_closed", "")) for tl in tradelines]
    valid_opened = [d for d in opened_dates if d is not None]
    valid_closed = [d for d in closed_dates if d is not None]

    _month_fmt = lambda d: d.strftime("%b %Y")  # e.g. "Dec 2019"
    earliest_opened = _month_fmt(min(valid_opened)) if valid_opened else None
    latest_opened = _month_fmt(max(valid_opened)) if valid_opened else None
    latest_closed = _month_fmt(max(valid_closed)) if valid_closed else None

    return BureauLoanFeatureVector(
        loan_type=loan_type,
        secured=secured,
        loan_count=loan_count,
        total_sanctioned_amount=total_sanctioned,
        total_outstanding_amount=total_outstanding,
        avg_vintage_months=avg_vintage,
        months_since_last_payment=months_since_last_payment,
        live_count=live_count,
        closed_count=closed_count,
        delinquency_flag=delinquency_flag,
        max_dpd=max_dpd,
        max_dpd_months_ago=max_dpd_months_ago,
        overdue_amount=overdue_amount,
        utilization_ratio=utilization_ratio,
        earliest_opened=earliest_opened,
        latest_opened=latest_opened,
        latest_closed=latest_closed,
        forced_event_flags=forced_event_flags,
        on_us_count=on_us_count,
        off_us_count=off_us_count,
    )


def compute_monthly_exposure(customer_id: int, n_months: int = 24) -> dict:
    """Compute monthly active sanction exposure by canonical loan type.

    For each of the past n_months calendar months, sums the sanction_amount
    of all tradelines that were open during that month (opened on/before month
    end AND not yet closed / closed on/after month start).

    Returns:
        {
            "months": ["Jan 2023", ...],          # ordered labels oldest→newest
            "series": {"PL": [0, 5e5, ...], ...}  # sanction exposure per month
        }
    """
    from calendar import monthrange

    today = date.today()

    # Build ordered list of (first_day, last_day, label) for the window
    months_window = []
    base = today.year * 12 + today.month - 1
    for i in range(n_months - 1, -1, -1):
        total = base - i
        yr, mo = divmod(total, 12)
        mo += 1
        first_day = date(yr, mo, 1)
        last_day = date(yr, mo, monthrange(yr, mo)[1])
        months_window.append((first_day, last_day, first_day.strftime("%b %Y")))

    all_rows = _load_bureau_data()
    customer_rows = [r for r in all_rows if _safe_int(r.get("crn", "")) == customer_id]

    # Group by canonical loan type
    grouped: Dict[LoanType, List[dict]] = defaultdict(list)
    for row in customer_rows:
        canonical = normalize_loan_type(row.get("loan_type_new", "").strip())
        grouped[canonical].append(row)

    series: Dict[str, list] = {}
    for loan_type, tradelines in grouped.items():
        label = loan_type.name  # short: "PL", "CC", "HL", etc.
        amounts = []
        for first_day, last_day, _ in months_window:
            total = 0.0
            for tl in tradelines:
                opened = _parse_date(tl.get("date_opened", ""))
                closed = _parse_date(tl.get("date_closed", ""))
                if opened is None:
                    continue
                # Tradeline active during this month?
                if opened <= last_day and (closed is None or closed >= first_day):
                    total += _safe_float(tl.get("sanction_amount", ""))
            amounts.append(round(total, 0))
        series[label] = amounts

    # Drop all-zero series
    series = {k: v for k, v in series.items() if any(x > 0 for x in v)}

    return {
        "months": [m[2] for m in months_window],
        "series": series,
    }


def extract_bureau_features(customer_id: int) -> Dict[LoanType, BureauLoanFeatureVector]:
    """Extract bureau feature vectors for a customer.

    Loads raw tradelines from dpd_data.csv, groups by canonical LoanType,
    and computes one BureauLoanFeatureVector per loan type.

    Args:
        customer_id: The CRN (customer reference number) from bureau data.

    Returns:
        Dict mapping each LoanType to its computed feature vector.
        Only loan types present in the customer's data are included.
    """
    all_rows = _load_bureau_data()

    # Filter by customer
    customer_rows = [
        row for row in all_rows if _safe_int(row.get("crn", "")) == customer_id
    ]

    if not customer_rows:
        return {}

    # Group by canonical loan type
    grouped: Dict[LoanType, List[dict]] = defaultdict(list)
    for row in customer_rows:
        raw_type = row.get("loan_type_new", "").strip()
        canonical = normalize_loan_type(raw_type)
        grouped[canonical].append(row)

    # Build one feature vector per loan type
    vectors: Dict[LoanType, BureauLoanFeatureVector] = {}
    for loan_type, tradelines in grouped.items():
        vectors[loan_type] = _build_feature_vector(loan_type, tradelines)

    return vectors
