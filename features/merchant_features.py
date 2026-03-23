"""Merchant-level features for banking transaction analysis.

Computes per-merchant behavioral features from raw transaction data.
All functions are standalone callables that accept a list of transaction
dicts and return simple dicts/lists. No LLM calls — purely deterministic.

Reuses existing merchant extraction logic from utils/narration_utils.py
and fuzzy matching pattern from tools/transaction_fetcher.py.
"""

import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

from utils.narration_utils import (
    extract_recipient_name,
    clean_narration,
    normalize_narration,
)

try:
    from fuzzywuzzy import fuzz
    _FUZZYWUZZY_AVAILABLE = True
except ImportError:
    _FUZZYWUZZY_AVAILABLE = False

# Same threshold as tools/transaction_fetcher.py
_SIMILARITY_THRESHOLD = 70


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _are_similar(s1: str, s2: str) -> bool:
    """Check if two merchant names are similar (reuses transaction_fetcher pattern)."""
    if not _FUZZYWUZZY_AVAILABLE:
        return s1.lower() == s2.lower()
    n1 = normalize_narration(s1)
    n2 = normalize_narration(s2)
    if not n1 or not n2:
        return False
    return fuzz.token_set_ratio(n1, n2) >= _SIMILARITY_THRESHOLD


def _filter_transactions(
    transactions: List[Dict[str, Any]],
    direction: Optional[str] = None,
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Filter transactions by direction and self-transfer flag."""
    result = []
    for txn in transactions:
        if exclude_self_transfers and txn.get("self_transfer") in (1, "1", True):
            continue
        if direction and txn.get("dr_cr_indctor") != direction:
            continue
        result.append(txn)
    return result


def _group_by_merchant(
    transactions: List[Dict[str, Any]],
    direction: Optional[str] = None,
    exclude_self_transfers: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """Group transactions by extracted merchant name using fuzzy matching.

    REUSES EXISTING LOGIC:
    - extract_recipient_name() from utils/narration_utils.py
    - clean_narration() from utils/narration_utils.py as fallback
    - normalize_narration() + fuzzywuzzy for similarity (same as transaction_fetcher.py)

    Returns:
        Dict mapping merchant_name -> list of txn dicts (each enriched
        with 'direction' from the original dr_cr_indctor).
    """
    filtered = _filter_transactions(transactions, direction, exclude_self_transfers)

    groups: Dict[str, List[Dict[str, Any]]] = {}
    group_keys: List[str] = []  # ordered list of canonical names

    for txn in filtered:
        narration = str(txn.get("tran_partclr", ""))
        merchant = extract_recipient_name(narration)
        if not merchant:
            merchant = clean_narration(narration)
        if not merchant:
            continue

        # Find matching group via fuzzy match
        matched_key = None
        for key in group_keys:
            if _are_similar(merchant, key):
                matched_key = key
                break

        enriched = {**txn, "_merchant": merchant}

        if matched_key:
            groups[matched_key].append(enriched)
        else:
            groups[merchant] = [enriched]
            group_keys.append(merchant)

    return groups


def _get_month(txn: Dict[str, Any]) -> str:
    """Extract YYYY-MM from tran_date."""
    return str(txn.get("tran_date", ""))[:7]


# ---------------------------------------------------------------------------
# Public feature functions
# ---------------------------------------------------------------------------

def get_merchant_distinct_months(
    transactions: List[Dict[str, Any]],
    direction: Optional[str] = None,
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Number of distinct months each merchant appeared in.

    Returns:
        List of dicts with merchant, direction, distinct_months, months.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    result = []
    for merchant, txns in groups.items():
        months = sorted(set(_get_month(t) for t in txns if _get_month(t)))
        dirs = set(t.get("dr_cr_indctor", "") for t in txns)
        result.append({
            "merchant": merchant,
            "direction": "/".join(sorted(dirs)),
            "distinct_months": len(months),
            "months": months,
        })
    return result


def get_merchant_monthly_counts(
    transactions: List[Dict[str, Any]],
    direction: Optional[str] = None,
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Monthly transaction count per merchant.

    Returns:
        List of dicts with merchant, direction, monthly_counts, total_count.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    result = []
    for merchant, txns in groups.items():
        monthly: Dict[str, int] = defaultdict(int)
        for t in txns:
            m = _get_month(t)
            if m:
                monthly[m] += 1
        dirs = set(t.get("dr_cr_indctor", "") for t in txns)
        result.append({
            "merchant": merchant,
            "direction": "/".join(sorted(dirs)),
            "monthly_counts": dict(sorted(monthly.items())),
            "total_count": len(txns),
        })
    return result


def get_merchant_monthly_amount_stats(
    transactions: List[Dict[str, Any]],
    direction: Optional[str] = None,
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Monthly avg, median, max amount per merchant.

    Returns:
        List of dicts with merchant, direction, avg/median/max/total_amount.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    result = []
    for merchant, txns in groups.items():
        amounts = [float(t.get("tran_amt_in_ac", 0)) for t in txns]
        if not amounts:
            continue
        dirs = set(t.get("dr_cr_indctor", "") for t in txns)
        result.append({
            "merchant": merchant,
            "direction": "/".join(sorted(dirs)),
            "avg_amount": sum(amounts) / len(amounts),
            "median_amount": statistics.median(amounts),
            "max_amount": max(amounts),
            "total_amount": sum(amounts),
        })
    return result


def get_regular_merchants(
    transactions: List[Dict[str, Any]],
    min_months: int = 2,
    total_months: int = 6,
    direction: Optional[str] = None,
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Merchants appearing in at least min_months distinct months.

    Returns:
        List of dicts with merchant, direction, distinct_months, is_regular, avg_amount.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    result = []
    for merchant, txns in groups.items():
        months = set(_get_month(t) for t in txns if _get_month(t))
        if len(months) < min_months:
            continue
        amounts = [float(t.get("tran_amt_in_ac", 0)) for t in txns]
        dirs = set(t.get("dr_cr_indctor", "") for t in txns)
        result.append({
            "merchant": merchant,
            "direction": "/".join(sorted(dirs)),
            "distinct_months": len(months),
            "is_regular": True,
            "avg_amount": sum(amounts) / len(amounts) if amounts else 0,
        })
    return result


def get_anomaly_merchants(
    transactions: List[Dict[str, Any]],
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Merchants flagged as anomalous — one-time large transactions.

    Criterion: appeared exactly once, amount > 3x customer's median debit amount.

    Returns:
        List of dicts with merchant, direction, anomaly_reason, amount, count.
    """
    # Compute median debit amount across all transactions
    debit_amounts = [
        float(t.get("tran_amt_in_ac", 0))
        for t in transactions
        if t.get("dr_cr_indctor") == "D"
        and not (exclude_self_transfers and t.get("self_transfer") in (1, "1", True))
    ]
    if not debit_amounts:
        return []
    median_debit = statistics.median(debit_amounts)
    threshold = median_debit * 3

    groups = _group_by_merchant(transactions, exclude_self_transfers=exclude_self_transfers)
    result = []
    for merchant, txns in groups.items():
        if len(txns) != 1:
            continue
        amt = float(txns[0].get("tran_amt_in_ac", 0))
        if amt > threshold:
            result.append({
                "merchant": merchant,
                "direction": txns[0].get("dr_cr_indctor", ""),
                "anomaly_reason": "one_time_large",
                "amount": amt,
                "count": 1,
            })
    return result


def get_merchant_concentration(
    transactions: List[Dict[str, Any]],
    direction: str = "D",
    exclude_self_transfers: bool = True,
) -> Dict[str, Any]:
    """Spending concentration across merchants.

    Returns:
        Dict with top_1_pct, top_3_pct, hhi, total_merchants.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    if not groups:
        return {"top_1_pct": 0, "top_3_pct": 0, "hhi": 0, "total_merchants": 0}

    totals = {m: sum(float(t.get("tran_amt_in_ac", 0)) for t in txns)
              for m, txns in groups.items()}
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return {"top_1_pct": 0, "top_3_pct": 0, "hhi": 0, "total_merchants": len(groups)}

    sorted_totals = sorted(totals.values(), reverse=True)
    top_1_pct = (sorted_totals[0] / grand_total) * 100
    top_3_pct = (sum(sorted_totals[:3]) / grand_total) * 100

    # HHI: sum of squared market shares (each as percentage)
    hhi = sum((v / grand_total * 100) ** 2 for v in sorted_totals)

    return {
        "top_1_pct": round(top_1_pct, 1),
        "top_3_pct": round(top_3_pct, 1),
        "hhi": round(hhi, 1),
        "total_merchants": len(groups),
    }


def get_merchant_amount_trend(
    transactions: List[Dict[str, Any]],
    direction: Optional[str] = None,
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Amount trend per merchant (first-half vs second-half average).

    Only for merchants with transactions in 2+ distinct months.

    Returns:
        List of dicts with merchant, direction, trend, first_half_avg, second_half_avg.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    result = []
    for merchant, txns in groups.items():
        months = sorted(set(_get_month(t) for t in txns if _get_month(t)))
        if len(months) < 2:
            continue

        mid = len(months) // 2
        first_months = set(months[:mid])
        second_months = set(months[mid:])

        first_amounts = [float(t.get("tran_amt_in_ac", 0)) for t in txns
                         if _get_month(t) in first_months]
        second_amounts = [float(t.get("tran_amt_in_ac", 0)) for t in txns
                          if _get_month(t) in second_months]

        first_avg = sum(first_amounts) / len(first_amounts) if first_amounts else 0
        second_avg = sum(second_amounts) / len(second_amounts) if second_amounts else 0

        if first_avg == 0:
            trend = "stable"
        elif second_avg / first_avg > 1.2:
            trend = "increasing"
        elif second_avg / first_avg < 0.8:
            trend = "decreasing"
        else:
            trend = "stable"

        dirs = set(t.get("dr_cr_indctor", "") for t in txns)
        result.append({
            "merchant": merchant,
            "direction": "/".join(sorted(dirs)),
            "trend": trend,
            "first_half_avg": round(first_avg, 2),
            "second_half_avg": round(second_avg, 2),
        })
    return result


def get_round_amount_merchants(
    transactions: List[Dict[str, Any]],
    direction: str = "D",
    exclude_self_transfers: bool = True,
) -> List[Dict[str, Any]]:
    """Merchants where >80% of transactions are round amounts (divisible by 100).

    Returns:
        List of dicts with merchant, round_pct, count.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    result = []
    for merchant, txns in groups.items():
        amounts = [float(t.get("tran_amt_in_ac", 0)) for t in txns]
        if not amounts:
            continue
        round_count = sum(1 for a in amounts if a > 0 and a % 100 == 0)
        round_pct = (round_count / len(amounts)) * 100
        if round_pct > 80:
            result.append({
                "merchant": merchant,
                "round_pct": round(round_pct, 1),
                "count": len(amounts),
            })
    return result


def get_new_merchant_ratio(
    transactions: List[Dict[str, Any]],
    direction: str = "D",
    exclude_self_transfers: bool = True,
) -> Dict[str, Any]:
    """Ratio of merchants that first appeared in the last month of data.

    Returns:
        Dict with new_merchant_count, total_merchant_count, ratio, new_merchants.
    """
    groups = _group_by_merchant(transactions, direction, exclude_self_transfers)
    if not groups:
        return {"new_merchant_count": 0, "total_merchant_count": 0, "ratio": 0, "new_merchants": []}

    # Find last month across all transactions
    all_months = set()
    for txns in groups.values():
        for t in txns:
            m = _get_month(t)
            if m:
                all_months.add(m)
    if not all_months:
        return {"new_merchant_count": 0, "total_merchant_count": len(groups), "ratio": 0, "new_merchants": []}

    last_month = max(all_months)

    new_merchants = []
    for merchant, txns in groups.items():
        merchant_months = set(_get_month(t) for t in txns if _get_month(t))
        if merchant_months == {last_month}:
            total = sum(float(t.get("tran_amt_in_ac", 0)) for t in txns)
            new_merchants.append({"name": merchant, "amount": total})

    return {
        "new_merchant_count": len(new_merchants),
        "total_merchant_count": len(groups),
        "ratio": round(len(new_merchants) / len(groups), 2) if groups else 0,
        "new_merchants": new_merchants,
    }


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def compute_all_merchant_features(
    customer_id: int,
    exclude_self_transfers: bool = True,
) -> Dict[str, Any]:
    """Compute all merchant features for a customer.

    Loads transactions via get_transactions_df(), groups once, then
    calls each feature function.

    Args:
        customer_id: Customer identifier.
        exclude_self_transfers: Exclude self-transfer transactions (default True).

    Returns:
        Dict with keys for each feature category.
    """
    from data.loader import get_transactions_df

    df = get_transactions_df()
    cust_df = df[df["cust_id"] == customer_id]
    if len(cust_df) == 0:
        return {}

    transactions = cust_df.to_dict("records")

    return {
        "distinct_months": get_merchant_distinct_months(transactions, exclude_self_transfers=exclude_self_transfers),
        "monthly_counts": get_merchant_monthly_counts(transactions, exclude_self_transfers=exclude_self_transfers),
        "amount_stats": get_merchant_monthly_amount_stats(transactions, exclude_self_transfers=exclude_self_transfers),
        "regular_merchants": get_regular_merchants(transactions, exclude_self_transfers=exclude_self_transfers),
        "anomaly_merchants": get_anomaly_merchants(transactions, exclude_self_transfers=exclude_self_transfers),
        "concentration": get_merchant_concentration(transactions, exclude_self_transfers=exclude_self_transfers),
        "amount_trends": get_merchant_amount_trend(transactions, exclude_self_transfers=exclude_self_transfers),
        "round_amount_merchants": get_round_amount_merchants(transactions, exclude_self_transfers=exclude_self_transfers),
        "new_merchant_ratio": get_new_merchant_ratio(transactions, exclude_self_transfers=exclude_self_transfers),
    }
