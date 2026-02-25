"""Transaction fetching and summarization with fuzzy matching.

This module provides deterministic transaction analysis:
- Salary/income detection
- Similar transaction grouping using fuzzywuzzy
- Structured output via Pydantic schemas

NO LLM calls - purely deterministic logic.
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict

from data.loader import get_transactions_df
from schemas.transaction_summary import (
    SalarySummary,
    HighFrequencyTransaction,
    TransactionSummary
)
from utils.narration_utils import (
    normalize_narration,
    extract_recipient_name,
    is_salary_narration
)

try:
    from fuzzywuzzy import fuzz
    FUZZYWUZZY_AVAILABLE = True
except ImportError:
    FUZZYWUZZY_AVAILABLE = False
    print("Warning: fuzzywuzzy not installed. Install with: pip install fuzzywuzzy python-Levenshtein")


# Configuration
SIMILARITY_THRESHOLD = 70  # Minimum similarity for grouping
MIN_GROUP_SIZE = 3  # Minimum transactions to form a group
MIN_SALARY_COUNT = 2  # Minimum salary transactions to detect


def fetch_transaction_summary(customer_id: int) -> TransactionSummary:
    """
    Fetch and summarize transactions for a customer.
    This is the main entry point for the transaction summarization subsystem.
    Args: customer_id: Customer identifier
    Returns: TransactionSummary with salary info and high-frequency transaction groups
    """
    df = get_transactions_df()
    cust_df = df[df['cust_id'] == customer_id]

    if len(cust_df) == 0:
        return TransactionSummary(customer_id=customer_id, total_transactions_analyzed=0)

    # Convert to list of dicts for processing
    transactions = cust_df.to_dict('records')

    # Detect salary
    salary_summary = _detect_salary(transactions)

    # Group similar transactions
    high_freq_txns = _group_similar_transactions(transactions)

    return TransactionSummary(
        customer_id=customer_id,
        salary_summary=salary_summary,
        high_frequency_transactions=high_freq_txns,
        total_transactions_analyzed=len(transactions)
    )


def _detect_salary(transactions: List[Dict[str, Any]]) -> Optional[SalarySummary]:
    """
    Detect salary/income transactions deterministically.

    Rules:
    - Filter credit transactions (dr_cr_indctor == 'C')
    - Match by category == 'SALARY' OR salary keywords in narration
    - Require at least MIN_SALARY_COUNT occurrences

    Args:
        transactions: List of transaction dicts

    Returns:
        SalarySummary if salary detected, None otherwise
    """
    salary_txns = []

    for txn in transactions:
        # Only credits
        if txn.get('dr_cr_indctor') != 'C':
            continue

        # Check category
        category = str(txn.get('category_of_txn', '')).upper()
        narration = str(txn.get('tran_partclr', ''))

        if category == 'SALARY' or is_salary_narration(narration):
            salary_txns.append({
                'amount': float(txn.get('tran_amt_in_ac', 0)),
                'narration': narration,
                'date': txn.get('tran_date', '')
            })

    if len(salary_txns) < MIN_SALARY_COUNT:
        return None

    amounts = [t['amount'] for t in salary_txns]
    narrations = [t['narration'] for t in salary_txns]

    return SalarySummary(
        average_amount=sum(amounts) / len(amounts),
        frequency="monthly",
        narrations=narrations,
        transaction_count=len(salary_txns),
        total_amount=sum(amounts)
    )


def _group_similar_transactions(
    transactions: List[Dict[str, Any]]
) -> List[HighFrequencyTransaction]:
    """
    Group similar transactions using fuzzy matching.

    Algorithm:
    1. Extract recipient names from narrations
    2. Group by normalized recipient name using fuzzy matching
    3. Filter groups with count >= MIN_GROUP_SIZE

    Args:
        transactions: List of transaction dicts

    Returns:
        List of HighFrequencyTransaction groups
    """
    if not FUZZYWUZZY_AVAILABLE:
        return _group_by_exact_match(transactions)

    # Separate debits and credits
    debits = [t for t in transactions if t.get('dr_cr_indctor') == 'D']
    credits = [t for t in transactions if t.get('dr_cr_indctor') == 'C']

    # Process debits (spending patterns)
    debit_groups = _fuzzy_group_transactions(debits, 'D')

    # Process credits (income patterns) - excluding salary
    non_salary_credits = [
        t for t in credits
        if str(t.get('category_of_txn', '')).upper() != 'SALARY'
        and not is_salary_narration(str(t.get('tran_partclr', '')))
    ]
    credit_groups = _fuzzy_group_transactions(non_salary_credits, 'C')

    # Combine and sort by count
    all_groups = debit_groups + credit_groups
    all_groups.sort(key=lambda x: x.count, reverse=True)

    return all_groups


def _fuzzy_group_transactions(
    transactions: List[Dict[str, Any]],
    txn_type: str
) -> List[HighFrequencyTransaction]:
    """
    Group transactions by fuzzy matching on recipient names.

    Args:
        transactions: List of transactions to group
        txn_type: "D" or "C"

    Returns:
        List of transaction groups
    """
    groups: List[Dict] = []

    for txn in transactions:
        narration = str(txn.get('tran_partclr', ''))
        amount = float(txn.get('tran_amt_in_ac', 0))
        recipient = extract_recipient_name(narration)

        if not recipient:
            # Use normalized narration as fallback
            recipient = normalize_narration(narration)[:50]

        if not recipient:
            continue

        # Find matching group
        matched_group = None
        for group in groups:
            rep_name = group['representative']
            if _are_similar(recipient, rep_name):
                matched_group = group
                break

        if matched_group:
            matched_group['narrations'].append(narration)
            matched_group['amounts'].append(amount)
            matched_group['recipients'].add(recipient)
        else:
            # Create new group
            groups.append({
                'representative': recipient,
                'narrations': [narration],
                'amounts': [amount],
                'recipients': {recipient}
            })

    # Convert to HighFrequencyTransaction, filtering by MIN_GROUP_SIZE
    result = []
    for group in groups:
        if len(group['narrations']) >= MIN_GROUP_SIZE:
            total = sum(group['amounts'])
            count = len(group['narrations'])
            result.append(HighFrequencyTransaction(
                representative_narration=group['representative'],
                similar_narrations=list(set(group['narrations'])),
                count=count,
                total_amount=total,
                average_amount=total / count if count > 0 else 0,
                transaction_type=txn_type
            ))

    return result


def _are_similar(s1: str, s2: str, threshold: int = SIMILARITY_THRESHOLD) -> bool:
    """
    Check if two strings are similar using fuzzywuzzy.

    Args:
        s1: First string
        s2: Second string
        threshold: Minimum similarity score (0-100)

    Returns:
        True if similarity >= threshold
    """
    if not FUZZYWUZZY_AVAILABLE:
        return s1.lower() == s2.lower()

    # Normalize for comparison
    n1 = normalize_narration(s1)
    n2 = normalize_narration(s2)

    if not n1 or not n2:
        return False

    score = fuzz.token_set_ratio(n1, n2)
    return score >= threshold


def _group_by_exact_match(
    transactions: List[Dict[str, Any]]
) -> List[HighFrequencyTransaction]:
    """
    Fallback grouping by exact recipient match (when fuzzywuzzy unavailable).

    Args:
        transactions: List of transactions

    Returns:
        List of transaction groups
    """
    groups = defaultdict(lambda: {'narrations': [], 'amounts': [], 'type': 'D'})

    for txn in transactions:
        narration = str(txn.get('tran_partclr', ''))
        amount = float(txn.get('tran_amt_in_ac', 0))
        txn_type = txn.get('dr_cr_indctor', 'D')
        recipient = extract_recipient_name(narration)

        if not recipient:
            continue

        key = recipient.upper()
        groups[key]['narrations'].append(narration)
        groups[key]['amounts'].append(amount)
        groups[key]['type'] = txn_type

    result = []
    for name, data in groups.items():
        if len(data['narrations']) >= MIN_GROUP_SIZE:
            total = sum(data['amounts'])
            count = len(data['narrations'])
            result.append(HighFrequencyTransaction(
                representative_narration=name,
                similar_narrations=list(set(data['narrations'])),
                count=count,
                total_amount=total,
                average_amount=total / count if count > 0 else 0,
                transaction_type=data['type']
            ))

    result.sort(key=lambda x: x.count, reverse=True)
    return result


# Convenience function for direct testing
def get_transaction_summary(customer_id: int) -> Dict[str, Any]:
    """
    Get transaction summary as a dictionary (for tool integration).

    Args:
        customer_id: Customer identifier

    Returns:
        Dictionary representation of TransactionSummary
    """
    summary = fetch_transaction_summary(customer_id)
    return summary.model_dump()
