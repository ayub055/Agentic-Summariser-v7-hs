"""Narration normalization and extraction utilities."""

import re
from typing import Optional


def normalize_narration(text: str) -> str:
    """
    Normalize narration for fuzzy matching.

    - Convert to lowercase
    - Remove numbers
    - Remove special characters
    - Strip whitespace

    Args:
        text: Raw narration string

    Returns:
        Normalized string for comparison
    """
    if not text:
        return ""

    text = text.lower()
    text = re.sub(r'\d+', '', text)  # Remove numbers
    text = re.sub(r'[^a-z\s]', ' ', text)  # Remove special chars, keep letters and spaces
    text = re.sub(r'\s+', ' ', text)  # Collapse multiple spaces
    return text.strip()


def extract_recipient_name(narration: str) -> Optional[str]:
    """
    Extract recipient name from UPI/IMPS narrations.

    Patterns handled:
    - "UPI/NAME/ID/..." → NAME
    - "SentIMPS...NAME IMPS-..." → NAME
    - "EMPLOYEE SALARY FOR..." → "SALARY"

    Args:
        narration: Raw transaction narration

    Returns:
        Extracted name or None if not found
    """
    if not narration:
        return None

    narration = narration.strip()

    # Pattern 1: UPI transactions - "UPI/NAME/ID/..."
    upi_match = re.match(r'^UPI/([^/]+)/', narration, re.IGNORECASE)
    if upi_match:
        name = upi_match.group(1).strip()
        if name and len(name) > 1:
            return name

    # Pattern 2: IMPS transactions - "SentIMPS{id}{name} IMPS-..."
    imps_match = re.match(r'^SentIMPS\d+([a-zA-Z\s]+)\s*IMPS-', narration, re.IGNORECASE)
    if imps_match:
        name = imps_match.group(1).strip()
        if name and len(name) > 1:
            return name

    # Pattern 3: Salary - "EMPLOYEE SALARY FOR..."
    if 'SALARY' in narration.upper() or 'EMPLOYEE' in narration.upper():
        return "SALARY"

    # Pattern 4: Cash deposit - "Cash Deposit at/..."
    if narration.upper().startswith('CASH DEPOSIT'):
        return "CASH_DEPOSIT"

    # Pattern 5: Reversal - "REV-..."
    if narration.upper().startswith('REV-'):
        # Try to extract from the reversed transaction
        inner = narration[4:]
        return extract_recipient_name(inner)

    return None


def is_salary_narration(narration: str) -> bool:
    """
    Check if narration indicates a salary/income transaction.

    Args:
        narration: Transaction narration

    Returns:
        True if salary-related keywords found
    """
    if not narration:
        return False

    keywords = ['salary', 'employee', 'payroll', 'stipend', 'bonus', 'wages']
    narration_lower = narration.lower()

    return any(keyword in narration_lower for keyword in keywords)


def get_transaction_category_from_narration(narration: str) -> str:
    """
    Infer transaction category from narration text.

    Args:
        narration: Transaction narration

    Returns:
        Inferred category string
    """
    if not narration:
        return "UNKNOWN"

    narration_lower = narration.lower()

    if is_salary_narration(narration):
        return "SALARY"

    if 'upi' in narration_lower:
        return "UPI"

    if 'imps' in narration_lower:
        return "IMPS"

    if 'cash deposit' in narration_lower:
        return "CASH_DEPOSIT"

    if 'atm' in narration_lower or 'withdrawal' in narration_lower:
        return "ATM"

    return "OTHER"
