"""Bureau feature aggregation layer.

Computes executive summary inputs from per-loan-type feature vectors.
All logic is deterministic — this produces the structured inputs that
the LLM narration layer will see.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

from schemas.loan_type import LoanType, get_loan_type_display_name
from features.bureau_features import BureauLoanFeatureVector


@dataclass
class BureauExecutiveSummaryInputs:
    total_tradelines: int
    live_tradelines: int
    closed_tradelines: int

    product_breakdown: Dict[LoanType, BureauLoanFeatureVector] = field(default_factory=dict)

    total_sanctioned: float = 0.0
    total_outstanding: float = 0.0
    unsecured_sanctioned: float = 0.0
    unsecured_outstanding: float = 0.0

    has_delinquency: bool = False
    max_dpd: Optional[int] = None
    max_dpd_months_ago: Optional[int] = None
    max_dpd_loan_type: Optional[str] = None


def aggregate_bureau_features(
    vectors: Dict[LoanType, BureauLoanFeatureVector],
) -> BureauExecutiveSummaryInputs:
    """Aggregate per-loan-type feature vectors into executive summary inputs.

    Args:
        vectors: Dict mapping LoanType to its computed feature vector.

    Returns:
        BureauExecutiveSummaryInputs with portfolio-level aggregations.
    """
    total_tradelines = 0
    live_tradelines = 0
    closed_tradelines = 0
    total_sanctioned = 0.0
    total_outstanding = 0.0
    unsecured_sanctioned = 0.0
    unsecured_outstanding = 0.0
    has_delinquency = False
    portfolio_max_dpd: Optional[int] = None
    portfolio_max_dpd_months_ago: Optional[int] = None
    portfolio_max_dpd_loan_type: Optional[str] = None

    for loan_type, vec in vectors.items():
        total_tradelines += vec.loan_count
        live_tradelines += vec.live_count
        closed_tradelines += vec.closed_count

        total_sanctioned += vec.total_sanctioned_amount
        total_outstanding += vec.total_outstanding_amount

        # Unsecured = non-secured loan types
        if not vec.secured:
            unsecured_sanctioned += vec.total_sanctioned_amount
            unsecured_outstanding += vec.total_outstanding_amount

        # Delinquency across portfolio
        if vec.delinquency_flag:
            has_delinquency = True

        # Max DPD across portfolio — track which loan type and when
        if vec.max_dpd is not None:
            if portfolio_max_dpd is None or vec.max_dpd > portfolio_max_dpd:
                portfolio_max_dpd = vec.max_dpd
                portfolio_max_dpd_months_ago = vec.max_dpd_months_ago
                portfolio_max_dpd_loan_type = get_loan_type_display_name(loan_type)

    return BureauExecutiveSummaryInputs(
        total_tradelines=total_tradelines,
        live_tradelines=live_tradelines,
        closed_tradelines=closed_tradelines,
        product_breakdown=dict(vectors),
        total_sanctioned=total_sanctioned,
        total_outstanding=total_outstanding,
        unsecured_sanctioned=unsecured_sanctioned,
        unsecured_outstanding=unsecured_outstanding,
        has_delinquency=has_delinquency,
        max_dpd=portfolio_max_dpd,
        max_dpd_months_ago=portfolio_max_dpd_months_ago,
        max_dpd_loan_type=portfolio_max_dpd_loan_type,
    )
