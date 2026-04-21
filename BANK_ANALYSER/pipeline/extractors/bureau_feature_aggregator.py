"""Bureau feature aggregation layer.

Computes executive summary inputs from per-loan-type feature vectors.
All logic is deterministic — this produces the structured inputs that
the LLM narration layer will see.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

    tu_score: Optional[int] = None

    # Kotak (on-us) aggregates
    on_us_total_tradelines: int = 0
    on_us_live_tradelines: int = 0
    on_us_total_sanctioned: float = 0.0
    on_us_total_outstanding: float = 0.0
    on_us_product_types: List[str] = field(default_factory=list)
    on_us_max_dpd: Optional[int] = None
    on_us_delinquency_flag: bool = False

    # Max single loan across portfolio
    max_single_sanction_amount: float = 0.0
    max_single_sanction_loan_type: Optional[str] = None

    # Joint loans
    total_joint_count: int = 0
    joint_product_types: List[str] = field(default_factory=list)

    # Defaulted loan type summaries
    defaulted_loan_summaries: List[dict] = field(default_factory=list)


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

    # Kotak (on-us) accumulators
    on_us_total_tradelines = 0
    on_us_live_tradelines = 0
    on_us_total_sanctioned = 0.0
    on_us_total_outstanding = 0.0
    on_us_product_types: list = []
    on_us_max_dpd: Optional[int] = None
    on_us_delinquency_flag = False

    # Max single loan across portfolio
    max_single_sanction_amount = 0.0
    max_single_sanction_loan_type: Optional[str] = None

    # Joint loans
    total_joint_count = 0
    joint_product_types: list = []

    # Defaulted loan summaries
    defaulted_loan_summaries: list = []

    for loan_type, vec in vectors.items():
        display_name = get_loan_type_display_name(loan_type)

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
            defaulted_loan_summaries.append({
                "type": display_name,
                "sanction": vec.total_sanctioned_amount,
                "outstanding": vec.total_outstanding_amount,
                "dpd": vec.max_dpd,
                "on_us": vec.on_us_count > 0,
            })

        # Max DPD across portfolio — track which loan type and when
        if vec.max_dpd is not None:
            if portfolio_max_dpd is None or vec.max_dpd > portfolio_max_dpd:
                portfolio_max_dpd = vec.max_dpd
                portfolio_max_dpd_months_ago = vec.max_dpd_months_ago
                portfolio_max_dpd_loan_type = display_name

        # Kotak (on-us) aggregation
        if vec.on_us_count > 0:
            on_us_total_tradelines += vec.on_us_count
            on_us_live_tradelines += vec.on_us_live_count
            on_us_total_sanctioned += vec.on_us_sanctioned
            on_us_total_outstanding += vec.on_us_outstanding
            on_us_product_types.append(display_name)
            if vec.max_dpd is not None and vec.on_us_count > 0:
                if on_us_max_dpd is None or vec.max_dpd > on_us_max_dpd:
                    on_us_max_dpd = vec.max_dpd
            if vec.delinquency_flag and vec.on_us_count > 0:
                on_us_delinquency_flag = True

        # Max single loan across portfolio
        if vec.max_single_sanction > max_single_sanction_amount:
            max_single_sanction_amount = vec.max_single_sanction
            max_single_sanction_loan_type = display_name

        # Joint loans
        if vec.joint_count > 0:
            total_joint_count += vec.joint_count
            joint_product_types.append(display_name)

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
        on_us_total_tradelines=on_us_total_tradelines,
        on_us_live_tradelines=on_us_live_tradelines,
        on_us_total_sanctioned=on_us_total_sanctioned,
        on_us_total_outstanding=on_us_total_outstanding,
        on_us_product_types=on_us_product_types,
        on_us_max_dpd=on_us_max_dpd,
        on_us_delinquency_flag=on_us_delinquency_flag,
        max_single_sanction_amount=max_single_sanction_amount,
        max_single_sanction_loan_type=max_single_sanction_loan_type,
        total_joint_count=total_joint_count,
        joint_product_types=joint_product_types,
        defaulted_loan_summaries=defaulted_loan_summaries,
    )
