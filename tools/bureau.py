"""Bureau report tool - orchestrates bureau report generation.

Wires together the builder, LLM narration, and PDF rendering
for the bureau report vertical. Parallel to report_orchestrator
for the customer report.
"""

import logging
from typing import Tuple

from schemas.bureau_report import BureauReport
from pipeline.reports.bureau_report_builder import build_bureau_report

logger = logging.getLogger(__name__)


def generate_bureau_report_pdf(customer_id: int) -> Tuple[BureauReport, str]:
    """Generate a bureau report with PDF output.

    Steps:
        1. Build bureau report (deterministic — feature extraction + aggregation)
        2. Generate LLM narrative from executive inputs (fail-soft)
        3. Render PDF (fail-soft)

    Args:
        customer_id: The CRN (customer reference number) from bureau data.

    Returns:
        Tuple of (BureauReport, pdf_path).
    """
    # 1. Build report (deterministic)
    report = build_bureau_report(customer_id)

    # 2. LLM narrative (fail-soft)
    try:
        from pipeline.reports.report_summary_chain import generate_bureau_review
        report.narrative = generate_bureau_review(
            report.executive_inputs,
            tradeline_features=report.tradeline_features,
            monthly_exposure=report.monthly_exposure,
        )
    except Exception as e:
        logger.warning(f"Bureau narrative generation failed: {e}")

    # 3. PDF rendering (fail-soft)
    pdf_path = ""
    try:
        from pipeline.renderers.bureau_pdf_renderer import render_bureau_report_pdf
        pdf_path = render_bureau_report_pdf(report)
    except Exception as e:
        logger.warning(f"Bureau PDF rendering failed: {e}")

    return report, pdf_path
