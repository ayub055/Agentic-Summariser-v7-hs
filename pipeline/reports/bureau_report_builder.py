"""Bureau report builder - deterministic data assembly without LLM.

Orchestrates feature extraction and aggregation to produce a BureauReport.
Parallel to customer_report_builder — NO LLM calls happen here.
"""

import logging
from datetime import datetime

from schemas.customer_report import ReportMeta
from schemas.bureau_report import BureauReport
from ..extractors.bureau_feature_extractor import extract_bureau_features, compute_monthly_exposure, extract_tu_score
from ..extractors.bureau_feature_aggregator import aggregate_bureau_features
from ..extractors.tradeline_feature_extractor import extract_tradeline_features
from .key_findings import extract_key_findings

logger = logging.getLogger(__name__)


def _validate_report(report: BureauReport) -> list[str]:
    """Run validation checks on the assembled report. Returns list of warnings."""
    warnings = []
    inputs = report.executive_inputs

    # Check: live + closed == total
    if inputs.live_tradelines + inputs.closed_tradelines != inputs.total_tradelines:
        warnings.append(
            f"Tradeline count mismatch: live({inputs.live_tradelines}) + "
            f"closed({inputs.closed_tradelines}) != total({inputs.total_tradelines})"
        )

    for loan_type, vec in report.feature_vectors.items():
        # Check: utilization only for CC
        if vec.utilization_ratio is not None and loan_type.name != "CC":
            warnings.append(f"Utilization ratio present for non-CC type: {loan_type.name}")

        # Check: no negative balances
        if vec.total_sanctioned_amount < 0:
            warnings.append(f"Negative sanctioned amount for {loan_type.name}")
        if vec.total_outstanding_amount < 0:
            warnings.append(f"Negative outstanding amount for {loan_type.name}")
        if vec.overdue_amount < 0:
            warnings.append(f"Negative overdue amount for {loan_type.name}")

    return warnings


def build_bureau_report(customer_id: int) -> BureauReport:
    """Build a bureau report by extracting and aggregating tradeline features.

    Steps:
        1. Extract per-loan-type feature vectors from raw bureau data
        2. Aggregate vectors into executive summary inputs
        3. Assemble and validate the BureauReport

    Args:
        customer_id: The CRN (customer reference number) from bureau data.

    Returns:
        BureauReport with feature vectors and executive inputs populated.
        Narrative field is left as None — populated downstream by LLM narration.
    """
    # 1. Feature extraction
    feature_vectors = extract_bureau_features(customer_id)

    if not feature_vectors:
        logger.warning(f"No bureau tradelines found for customer {customer_id}")

    # 2. Feature aggregation
    executive_inputs = aggregate_bureau_features(feature_vectors)
    executive_inputs.tu_score = extract_tu_score(customer_id)

    # 2b. Tradeline feature extraction (pre-computed, fail-soft)
    tradeline_features = None
    try:
        tradeline_features = extract_tradeline_features(customer_id)
    except Exception as e:
        logger.warning(f"Tradeline feature extraction failed for {customer_id}: {e}")

    # 3. Build meta
    meta = ReportMeta(
        customer_id=customer_id,
        generated_at=datetime.now().isoformat(),
        analysis_period="Bureau tradeline history",
        currency="INR",
        transaction_count=executive_inputs.total_tradelines,
    )

    # 4. Key findings (deterministic, fail-soft)
    key_findings = []
    try:
        key_findings = extract_key_findings(
            executive_inputs, feature_vectors, tradeline_features
        )
    except Exception as e:
        logger.warning(f"Key findings extraction failed for {customer_id}: {e}")

    # 4b. Monthly exposure timeseries (fail-soft)
    monthly_exposure = None
    try:
        monthly_exposure = compute_monthly_exposure(customer_id)
    except Exception as e:
        logger.warning(f"Monthly exposure computation failed for {customer_id}: {e}")

    # 5. Assemble report
    report = BureauReport(
        meta=meta,
        feature_vectors=feature_vectors,
        executive_inputs=executive_inputs,
        tradeline_features=tradeline_features,
        key_findings=key_findings,
        monthly_exposure=monthly_exposure,
    )

    # 6. Validate (fail-soft: log warnings, return partial report)
    warnings = _validate_report(report)
    for w in warnings:
        logger.warning(f"Bureau report validation [{customer_id}]: {w}")

    return report
