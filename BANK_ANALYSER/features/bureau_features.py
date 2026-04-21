"""Bureau feature vector definition.

Each BureauLoanFeatureVector represents the computed features for one
canonical loan type across all tradelines of that type for a customer.
These are primitive data points — internal, not UI-facing.
"""

from dataclasses import dataclass, field
from typing import Optional, List

from schemas.loan_type import LoanType


@dataclass
class BureauLoanFeatureVector:
    loan_type: LoanType
    secured: bool

    loan_count: int
    total_sanctioned_amount: float
    total_outstanding_amount: float

    avg_vintage_months: float
    months_since_last_payment: Optional[int]

    live_count: int
    closed_count: int

    delinquency_flag: bool
    max_dpd: Optional[int]
    max_dpd_months_ago: Optional[int] = None
    overdue_amount: float = 0.0

    utilization_ratio: Optional[float] = None  # CC only

    earliest_opened: Optional[str] = None   # e.g. "Dec 2019"
    latest_opened: Optional[str] = None     # e.g. "Nov 2025"
    latest_closed: Optional[str] = None     # e.g. "Apr 2025", None if all live

    forced_event_flags: List[str] = field(default_factory=list)
    on_us_count: int = 0
    off_us_count: int = 0

    # Kotak (on-us) amount breakdowns
    on_us_sanctioned: float = 0.0
    on_us_outstanding: float = 0.0
    on_us_live_count: int = 0

    # Largest individual tradeline sanction in this loan type
    max_single_sanction: float = 0.0

    # Tradelines with joint ownership
    joint_count: int = 0
