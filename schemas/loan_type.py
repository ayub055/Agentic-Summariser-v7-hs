"""Canonical loan type taxonomy for bureau tradeline classification.

Single source of truth for loan types used across all bureau logic.
Derived from dpd_data.csv loan_type values.
"""

from enum import Enum
from typing import Dict, Set


class LoanType(str, Enum):
    PL = "personal_loan"
    CC = "credit_card"
    HL = "home_loan"
    AL = "auto_loan"
    BL = "business_loan"
    LAP = "lap"
    LAS = "las"
    LAD = "lad"
    GL = "gold_loan"
    TWL = "two_wheeler_loan"
    CD = "consumer_durable"
    CMVL = "commercial_vehichle_loan"
    OTHER = "other"


# Maps raw dpd_data.csv `loan_type` values to canonical LoanType
LOAN_TYPE_NORMALIZATION_MAP: Dict[str, LoanType] = {
    # Personal loans
    "Personal Loan": LoanType.PL,
    "Short Term Personal Loan": LoanType.PL,
    "Microfinance - Personal Loan": LoanType.PL,
    "P2P Personal Loan": LoanType.PL,

    ### AS IT IS
    "Loan to Professional": LoanType.PL, # -- CHANGE TO AS IT IS
    "Loan on Credit Card": LoanType.CC,
    "Microfinance - Housing Loan": LoanType.HL,

    # Credit cards
    "Credit Card": LoanType.CC,
    "Secured Credit Card": LoanType.CC,
    "Corporate Credit Card": LoanType.CC,
    "Fleet Card": LoanType.CC,
    "Kisan Credit Card": LoanType.CC,

    # Home / housing loans
    "Housing Loan": LoanType.HL,
    "Home Loan": LoanType.HL,
    "Pradhan Mantri Awas Yojana - Credit Link Subsidy Scheme MAY CLSS": LoanType.HL,

    # Auto / vehicle loans
    "Auto Loan (Personal)": LoanType.AL,
    "Auto Loan": LoanType.AL,
    "Used Car Loan": LoanType.AL,

    ## COMMERCIAL VEHICLE LOAN CATEGORY
    "Commercial Vehicle Loan": LoanType.CMVL,
    "Construction Equipment Loan": LoanType.CMVL,
    "Tractor Loan": LoanType.CMVL,
    "P2P Auto Loan": LoanType.CMVL,

    # Business loans
    "Business Loan - General": LoanType.BL,
    "Business Loan - Secured": LoanType.BL,
    "Business Loan - Unsecured": LoanType.BL,
    "Business Loan - Priority Sector - Agriculture": LoanType.BL,
    "Business Loan - Priority Sector - Others": LoanType.BL,
    "Business Loan - Priority Sector - Small Business": LoanType.BL,
    "Business Loan Against Bank Deposits": LoanType.BL,
    "Business Non-Funded Credit Facility - General": LoanType.BL,
    "Business Non-Funded Credit Facility - Priority Sector-Others": LoanType.BL,
    "Business Non-Funded Credit Facility - Priority Sector - Agriculture": LoanType.BL,
    "Business Non-Funded Credit Facility - Priority Sector - Small Business": LoanType.BL,
    "Business Loan - General": LoanType.BL,
    "Business Loan - Unsecured": LoanType.BL,


    # Loan against property / securities / deposits
    "Loan_against_securities": LoanType.LAS,
    "Loan Against Shares/Securities": LoanType.LAS,
    "Loan Against Bank Deposits": LoanType.LAD,
    "Property Loan": LoanType.LAP,

    # Gold loans
    "Gold Loan": LoanType.GL,
    "Priority Sector - Gold Loan": LoanType.GL,

    # Two-wheeler
    "Two-wheeler Loan": LoanType.TWL,

    # Consumer durables
    "Consumer Loan": LoanType.CD,

    # Education & others
    "Education Loan": LoanType.OTHER,
    "P2P Education Loan": LoanType.OTHER,
    "Seller Financing": LoanType.OTHER,
    "Temporary Overdraft": LoanType.OTHER,
    "Overdraft": LoanType.OTHER,
    "Prime Minister Jaan Dhan Yojana - Overdraft": LoanType.OTHER,
    "Leasing": LoanType.OTHER,
    "Microfinance - Other": LoanType.OTHER,
    "Non-Funded Credit Facility": LoanType.OTHER,
    "Microfinance - Business Loan": LoanType.OTHER,
    "Mudra Loans - Shishu / Kishor / Tarun": LoanType.OTHER,
    "GECL Loan Secured": LoanType.OTHER,
    "GECL Loan Unsecured": LoanType.OTHER,
    "Other": LoanType.OTHER,
}

# Raw loan type names that are secured (sec_flag=1).
# Checked at raw level because some canonical types (BL, CC)
# have both secured and unsecured variants.
SECURED_LOAN_TYPES: Set[str] = {
    "Gold Loan",
    "Priority Sector - Gold Loan",
    "Two-wheeler Loan",
    "Tractor Loan",
    "Loan Against Bank Deposits",
    "Loan_against_securities",
    "Loan Against Shares/Securities",
    "Secured Credit Card",
    "Pradhan Mantri Awas Yojana - Credit Link Subsidy Scheme MAY CLSS",
    "GECL Loan Secured",
    "Microfinance - Housing Loan",
    "Leasing",
    "P2P Auto Loan",
    "Housing Loan",
    "Home Loan",
    "Property Loan",
    "Auto Loan (Personal)",
    "Auto Loan",
    "Used Car Loan",
    "Commercial Vehicle Loan",
    "Construction Equipment Loan",
    "Business Loan - Secured",
    "Business Loan Against Bank Deposits",
}


# Human-readable display names for report rendering
LOAN_TYPE_DISPLAY_NAMES: Dict[str, str] = {
    "personal_loan": "Personal Loan",
    "credit_card": "Credit Card",
    "home_loan": "Home Loan",
    "auto_loan": "Auto Loan",
    "business_loan": "Business Loan",
    "lap": "LAP",
    "las": "LAS",
    "lad": "LAD",
    "gold_loan": "Gold Loan",
    "two_wheeler_loan": "Two Wheeler Loan",
    "consumer_durable": "Consumer Durable",
    "commercial_vehichle_loan": "Commercial Vehicle Loan",
    "other": "Other",
}


def get_loan_type_display_name(loan_type) -> str:
    """Get human-readable display name for a LoanType.

    Args:
        loan_type: LoanType enum or its string value.

    Returns:
        Human-readable name like 'Personal Loan'.
    """
    value = loan_type.value if isinstance(loan_type, LoanType) else str(loan_type)
    return LOAN_TYPE_DISPLAY_NAMES.get(value, value.replace("_", " ").title())


# Kotak sectors that count as "on-us" tradelines
ON_US_SECTORS: Set[str] = {"KOTAK BANK", "KOTAK PRIME"}


def normalize_loan_type(raw_loan_type: str) -> LoanType:
    """Normalize a raw loan_type string from dpd_data.csv to canonical LoanType."""
    return LOAN_TYPE_NORMALIZATION_MAP.get(raw_loan_type, LoanType.OTHER)


def is_secured(raw_loan_type: str) -> bool:
    """Check if a raw loan type is secured (collateral-backed)."""
    return raw_loan_type in SECURED_LOAN_TYPES
