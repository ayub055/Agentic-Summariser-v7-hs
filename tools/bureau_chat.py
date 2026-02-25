"""Bureau chat tools - lightweight bureau queries for conversational use.

These tools return structured dicts that the LLM explainer narrates.
All logic is deterministic — reuses existing feature extractors.
"""

from typing import Dict, Any, Optional

from schemas.loan_type import LoanType, get_loan_type_display_name, LOAN_TYPE_DISPLAY_NAMES
from pipeline.extractors.bureau_feature_extractor import extract_bureau_features
from pipeline.extractors.bureau_feature_aggregator import aggregate_bureau_features
from pipeline.extractors.tradeline_feature_extractor import extract_tradeline_features
from utils.helpers import format_inr


def _fuzzy_match_loan_type(raw: str) -> Optional[LoanType]:
    """Fuzzy-match a user-provided loan type string to a LoanType enum."""
    raw_lower = raw.lower().strip()

    # Direct enum value match
    for lt in LoanType:
        if lt.value == raw_lower:
            return lt

    # Match against display names
    for value, display in LOAN_TYPE_DISPLAY_NAMES.items():
        if raw_lower in display.lower() or display.lower() in raw_lower:
            return LoanType(value)

    # Common abbreviations
    abbrevs = {
        "pl": LoanType.PERSONAL_LOAN, "personal": LoanType.PERSONAL_LOAN,
        "cc": LoanType.CREDIT_CARD, "credit card": LoanType.CREDIT_CARD,
        "hl": LoanType.HOME_LOAN, "home": LoanType.HOME_LOAN,
        "al": LoanType.AUTO_LOAN, "auto": LoanType.AUTO_LOAN, "car": LoanType.AUTO_LOAN,
        "bl": LoanType.BUSINESS_LOAN, "business": LoanType.BUSINESS_LOAN,
        "gl": LoanType.GOLD_LOAN, "gold": LoanType.GOLD_LOAN,
        "twl": LoanType.TWO_WHEELER_LOAN, "two wheeler": LoanType.TWO_WHEELER_LOAN,
        "lap": LoanType.LAP_LAS_LAD, "las": LoanType.LAP_LAS_LAD, "lad": LoanType.LAP_LAS_LAD,
        "consumer": LoanType.CONSUMER_DURABLE, "durable": LoanType.CONSUMER_DURABLE,
    }
    for key, lt in abbrevs.items():
        if key in raw_lower:
            return lt

    return None


def bureau_credit_card_info(customer_id: int) -> Dict[str, Any]:
    """Check if customer has credit cards and return utilization details."""
    vectors = extract_bureau_features(customer_id)

    cc_vec = vectors.get(LoanType.CREDIT_CARD)

    result = {
        "customer_id": customer_id,
        "has_credit_cards": cc_vec is not None,
    }

    if cc_vec is not None:
        result["count"] = cc_vec.loan_count
        result["live_count"] = cc_vec.live_count
        result["closed_count"] = cc_vec.closed_count
        result["total_sanctioned"] = format_inr(cc_vec.total_sanctioned_amount)
        result["total_outstanding"] = format_inr(cc_vec.total_outstanding_amount)
        result["utilization_pct"] = (
            f"{cc_vec.utilization_ratio * 100:.1f}%"
            if cc_vec.utilization_ratio is not None else "N/A"
        )
        result["max_dpd"] = cc_vec.max_dpd
        result["on_us_count"] = cc_vec.on_us_count
        result["off_us_count"] = cc_vec.off_us_count
    else:
        result["count"] = 0

    # Supplement with tl_features CC utilization if available
    tl = extract_tradeline_features(customer_id)
    if tl and tl.cc_balance_utilization_pct is not None:
        result["cc_balance_utilization_pct"] = f"{tl.cc_balance_utilization_pct:.2f}%"

    return result


def bureau_loan_type_info(customer_id: int, loan_type: str = None) -> Dict[str, Any]:
    """Get tradeline info for a specific loan type or all types."""
    vectors = extract_bureau_features(customer_id)

    result = {"customer_id": customer_id}

    if loan_type:
        matched_lt = _fuzzy_match_loan_type(loan_type)
        if matched_lt is None:
            result["error"] = f"Unknown loan type: '{loan_type}'"
            result["available_types"] = [
                get_loan_type_display_name(lt) for lt in vectors.keys()
            ]
            return result

        vec = vectors.get(matched_lt)
        if vec is None:
            result["found"] = False
            result["loan_type"] = get_loan_type_display_name(matched_lt)
            result["message"] = f"No {get_loan_type_display_name(matched_lt)} tradelines found"
            return result

        result["found"] = True
        result["loan_type"] = get_loan_type_display_name(matched_lt)
        result["secured"] = vec.secured
        result["count"] = vec.loan_count
        result["live_count"] = vec.live_count
        result["closed_count"] = vec.closed_count
        result["total_sanctioned"] = format_inr(vec.total_sanctioned_amount)
        result["total_outstanding"] = format_inr(vec.total_outstanding_amount)
        result["max_dpd"] = vec.max_dpd
        result["delinquent"] = vec.delinquency_flag
        result["on_us_count"] = vec.on_us_count
        result["off_us_count"] = vec.off_us_count
    else:
        # Return all loan types summary
        loan_types = []
        for lt, vec in vectors.items():
            loan_types.append({
                "loan_type": get_loan_type_display_name(lt),
                "count": vec.loan_count,
                "live": vec.live_count,
                "closed": vec.closed_count,
                "sanctioned": format_inr(vec.total_sanctioned_amount),
                "outstanding": format_inr(vec.total_outstanding_amount),
            })
        result["loan_types"] = loan_types
        result["total_types"] = len(loan_types)

    return result


def bureau_delinquency_check(customer_id: int, loan_type: str = None) -> Dict[str, Any]:
    """Check delinquency status across bureau tradelines."""
    vectors = extract_bureau_features(customer_id)
    tl = extract_tradeline_features(customer_id)

    result = {"customer_id": customer_id}

    # Filter to specific loan type if requested
    if loan_type:
        matched_lt = _fuzzy_match_loan_type(loan_type)
        if matched_lt and matched_lt in vectors:
            vec = vectors[matched_lt]
            result["loan_type"] = get_loan_type_display_name(matched_lt)
            result["is_delinquent"] = vec.delinquency_flag
            result["max_dpd"] = vec.max_dpd
            result["overdue_amount"] = format_inr(vec.overdue_amount)
        else:
            result["loan_type"] = loan_type
            result["is_delinquent"] = False
            result["message"] = f"No {loan_type} tradelines found"
    else:
        # Check across all loan types
        delinquent_types = []
        portfolio_max_dpd = None

        for lt, vec in vectors.items():
            if vec.delinquency_flag:
                delinquent_types.append({
                    "loan_type": get_loan_type_display_name(lt),
                    "max_dpd": vec.max_dpd,
                    "overdue_amount": format_inr(vec.overdue_amount),
                })
            if vec.max_dpd is not None:
                if portfolio_max_dpd is None or vec.max_dpd > portfolio_max_dpd:
                    portfolio_max_dpd = vec.max_dpd

        result["has_delinquency"] = len(delinquent_types) > 0
        result["delinquent_loan_types"] = delinquent_types
        result["portfolio_max_dpd"] = portfolio_max_dpd

    # Add DPD features from tl_features if available
    if tl:
        dpd_features = {}
        if tl.max_dpd_6m_cc is not None:
            dpd_features["max_dpd_6m_cc"] = tl.max_dpd_6m_cc
        if tl.max_dpd_6m_pl is not None:
            dpd_features["max_dpd_6m_pl"] = tl.max_dpd_6m_pl
        if tl.max_dpd_9m_cc is not None:
            dpd_features["max_dpd_9m_cc"] = tl.max_dpd_9m_cc
        if tl.pct_missed_payments_18m is not None:
            dpd_features["pct_missed_payments_18m"] = f"{tl.pct_missed_payments_18m:.2f}%"
        if tl.pct_0plus_24m_all is not None:
            dpd_features["pct_trades_with_dpd_24m"] = f"{tl.pct_0plus_24m_all:.2f}%"
        if dpd_features:
            result["dpd_features"] = dpd_features

    return result


def bureau_overview(customer_id: int) -> Dict[str, Any]:
    """Get a high-level bureau tradeline overview."""
    vectors = extract_bureau_features(customer_id)
    summary = aggregate_bureau_features(vectors)

    loan_types_present = [
        {"type": get_loan_type_display_name(lt), "count": vec.loan_count}
        for lt, vec in vectors.items()
    ]

    result = {
        "customer_id": customer_id,
        "total_tradelines": summary.total_tradelines,
        "live_tradelines": summary.live_tradelines,
        "closed_tradelines": summary.closed_tradelines,
        "total_sanctioned": format_inr(summary.total_sanctioned),
        "total_outstanding": format_inr(summary.total_outstanding),
        "unsecured_sanctioned": format_inr(summary.unsecured_sanctioned),
        "max_dpd": summary.max_dpd,
        "loan_types": loan_types_present,
        "currency": "INR",
    }

    return result
