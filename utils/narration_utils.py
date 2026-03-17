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
    Extract remitter / recipient name from transaction narrations.

    Patterns handled (in priority order):
    - IFT: "IFT RAJU KUMAR 12345" → "RAJU KUMAR"
    - UPI: "UPI/RAJU KUMAR/9876@ybl/..." → "RAJU KUMAR"
    - IMPS (Recd): "Recd:IMPS/123/RAJU KUMAR/..." → "RAJU KUMAR"
    - IMPS (Sent): "SentIMPS123456RAJU KUMAR IMPS-..." → "RAJU KUMAR"
    - RTGS: "RTGS 12345 RAJU KUMAR HDFC" → "RAJU KUMAR"
    - MB:RECEIVED FROM: "MB:RECEIVED FROM RAJU KUMAR" → "RAJU KUMAR"
    - NEFT: "NEFT 12345 RAJU KUMAR" → "RAJU KUMAR"

    Args:
        narration: Raw transaction narration

    Returns:
        Extracted name or None if no pattern matched
    """
    if not narration:
        return None

    narration = narration.strip()

    # Pattern 1: IFT — "IFT <name words> <last_token>"
    if narration.startswith("IFT"):
        parts = narration.split()
        if len(parts) >= 3:
            return ' '.join(parts[1:-1])
        return None

    # Pattern 2: UPI — "UPI/NAME/ID/..."
    if narration.upper().startswith("UPI/"):
        parts = narration.split('/')
        if len(parts) >= 2:
            name = parts[1].strip()
            if name and len(name) > 1:
                return name
        return None

    # Pattern 3: IMPS received — "Recd:IMPS/.../NAME/..."
    if "Recd:IMPS/" in narration:
        parts = narration.split('/')
        if len(parts) >= 3:
            name = parts[2].strip()
            if name and len(name) > 1:
                return name
        return None

    # Pattern 4: IMPS sent — "SentIMPS{digits}{name} IMPS-..."
    imps_match = re.match(r'^SentIMPS\d+([a-zA-Z\s]+)\s*IMPS-', narration, re.IGNORECASE)
    if imps_match:
        name = imps_match.group(1).strip()
        if name and len(name) > 1:
            return name

    # Pattern 5: RTGS — "RTGS <code> <name words> <bank>"
    if narration.startswith("RTGS"):
        parts = narration.split()
        if len(parts) >= 3:
            return ' '.join(parts[2:-1]) if len(parts) > 3 else parts[2]
        return None

    # Pattern 6: MB:RECEIVED FROM — "MB:RECEIVED FROM <name>"
    if narration.startswith("MB:RECEIVED FROM"):
        parts = narration.split("RECEIVED FROM")
        if len(parts) >= 2:
            name = parts[1].strip()
            if name:
                return name
        return None

    # Pattern 7: NEFT — "NEFT <code> <name words>"
    if narration.startswith("NEFT"):
        parts = narration.split()
        if len(parts) >= 3:
            return ' '.join(parts[2:])
        return None

    return None


def clean_narration(text: str) -> Optional[str]:
    """
    Lightweight cleanup of narration for display as a fallback merchant name.

    Unlike normalize_narration (which strips digits and lowercases for fuzzy
    matching), this preserves readability: keeps digits, title-cases, and
    only removes special characters.

    Args:
        text: Raw narration string

    Returns:
        Cleaned title-cased string, or None if empty after cleaning
    """
    if not text:
        return None

    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)  # Remove special chars, keep letters+digits
    text = re.sub(r'\s+', ' ', text).strip()       # Collapse whitespace

    if not text:
        return None

    return text.title()


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
