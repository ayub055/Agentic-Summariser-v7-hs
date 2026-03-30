"""Bureau report schema - single source of truth for bureau report state.

This module defines the canonical bureau report object that flows through
the report generation pipeline. Feature vectors are retained for auditability.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from schemas.loan_type import LoanType
from features.bureau_features import BureauLoanFeatureVector
from features.tradeline_features import TradelineFeatures
from pipeline.extractors.bureau_feature_aggregator import BureauExecutiveSummaryInputs
from schemas.customer_report import ReportMeta


@dataclass
class BureauReport:
    meta: ReportMeta
    feature_vectors: Dict[LoanType, BureauLoanFeatureVector] = field(default_factory=dict)
    executive_inputs: BureauExecutiveSummaryInputs = field(default_factory=lambda: BureauExecutiveSummaryInputs(
        total_tradelines=0, live_tradelines=0, closed_tradelines=0
    ))
    tradeline_features: Optional[TradelineFeatures] = None
    narrative: Optional[str] = None
    key_findings: List = field(default_factory=list)
    monthly_exposure: Optional[Dict[str, Any]] = None  # {"months": [...], "series": {...}}
    raw_loan_profile: Optional[Dict[str, Any]] = None  # raw loan type counts for persona
