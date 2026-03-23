"""Combined report tool - merges banking + bureau into one report.

Generates both individual reports (reusing caches), then renders
a unified combined PDF + HTML document.  If one data source is
unavailable the report is still generated with the available source.
"""

import logging
import os
from typing import Optional, Tuple

from schemas.customer_report import CustomerReport
from schemas.bureau_report import BureauReport
from pipeline.reports.report_orchestrator import generate_customer_report_pdf
from tools.bureau import generate_bureau_report_pdf

logger = logging.getLogger(__name__)

# Directory where per-customer Excel files are written
_EXCEL_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "excel"
)


def generate_combined_report_pdf(
    customer_id: int,
    theme: str = "original", # blue
) -> Tuple[Optional[CustomerReport], Optional[BureauReport], str]:
    """Generate a combined banking + bureau report as one PDF.

    Steps:
        1. Generate customer report (reuses cache if available)
        2. Generate bureau report (reuses cache if available)
        3. Render combined PDF + HTML

    If one data source is missing the report is still produced with a
    note about the absent source.

    Args:
        customer_id: The customer identifier (CRN).

    Returns:
        Tuple of (CustomerReport | None, BureauReport | None, combined_pdf_path).
    """
    # 1. Customer report (cached by report_orchestrator)
    customer_report = None
    try:
        customer_report, _ = generate_customer_report_pdf(customer_id)
    except Exception as e:
        logger.warning(f"Banking report unavailable for {customer_id}: {e}")

    # 2. Bureau report
    bureau_report = None
    try:
        bureau_report, _ = generate_bureau_report_pdf(customer_id)
    except Exception as e:
        logger.warning(f"Bureau report unavailable for {customer_id}: {e}")

    # 2.5 Generate combined executive summary (fail-soft)
    combined_summary = None
    exposure_text = None
    banking_text = (customer_report.customer_review or "") if customer_report else ""
    bureau_text = (bureau_report.narrative or "") if bureau_report else ""
    try:
        from pipeline.reports.report_summary_chain import (
            generate_combined_executive_summary,
            summarize_exposure_timeline,
        )
        from utils.helpers import mask_customer_id

        # Build FOIR context from tradeline features
        _tl = bureau_report.tradeline_features if bureau_report else None
        _foir_parts = []
        if _tl and _tl.foir is not None:
            _foir_parts.append(f"FOIR (total): {_tl.foir:.1f}%")
        if _tl and _tl.foir_unsec is not None:
            _foir_parts.append(f"FOIR (unsecured): {_tl.foir_unsec:.1f}%")
        # Kotak (on-us) context for combined summary
        if bureau_report and bureau_report.executive_inputs:
            _ei = bureau_report.executive_inputs
            if getattr(_ei, 'on_us_total_tradelines', 0) > 0:
                _foir_parts.append(
                    f"Kotak (On-Us): {_ei.on_us_total_tradelines} tradelines "
                    f"({', '.join(getattr(_ei, 'on_us_product_types', []))}), "
                    f"Sanctioned INR {_ei.on_us_total_sanctioned:,.0f}, "
                    f"Outstanding INR {_ei.on_us_total_outstanding:,.0f}"
                )
            if getattr(_ei, 'total_joint_count', 0) > 0:
                _foir_parts.append(
                    f"Joint Loans: {_ei.total_joint_count} tradeline(s) — "
                    f"{', '.join(getattr(_ei, 'joint_product_types', []))}"
                )
            if getattr(_ei, 'max_single_sanction_amount', 0) > 0:
                _max_loan = f"Largest Single Loan: INR {_ei.max_single_sanction_amount:,.0f}"
                if getattr(_ei, 'max_single_sanction_loan_type', None):
                    _max_loan += f" ({_ei.max_single_sanction_loan_type})"
                _foir_parts.append(_max_loan)

        foir_ctx = ", ".join(_foir_parts)

        exposure_text = summarize_exposure_timeline(
            bureau_report.monthly_exposure if bureau_report else None
        )

        combined_summary = generate_combined_executive_summary(
            banking_summary=banking_text,
            bureau_summary=bureau_text,
            customer_id=mask_customer_id(customer_id),
            exposure_summary=exposure_text,
            foir_context=foir_ctx,
        )
    except Exception as e:
        logger.warning(f"Combined executive summary generation failed: {e}")

    # 2.7 Load internal salary data (fail-soft)
    rg_salary_data = None
    try:
        from data.loader import load_rg_salary_data
        rg_salary_data = load_rg_salary_data(customer_id) or None
    except Exception as e:
        logger.warning(f"RG salary data unavailable for combined report [{customer_id}]: {e}")

    # 3. Combined rendering
    from pipeline.renderers.combined_report_renderer import render_combined_report
    pdf_path = render_combined_report(
        customer_report, bureau_report, combined_summary=combined_summary,
        rg_salary_data=rg_salary_data, theme=theme,
    )

    # 4. Export one-row Excel file for this customer (batch-merge later)
    try:
        from tools.excel_exporter import build_excel_row, export_row_to_excel
        row = build_excel_row(
            customer_id=customer_id,
            customer_report=customer_report,
            bureau_report=bureau_report,
            combined_summary=combined_summary,
            pdf_path=pdf_path,
            rg_salary_data=rg_salary_data,
            exposure_summary=exposure_text,
        )
        excel_path = os.path.join(_EXCEL_OUTPUT_DIR, f"{customer_id}.xlsx")
        export_row_to_excel(row, excel_path)
    except Exception as exc:
        logger.warning("Excel export failed for %s: %s", customer_id, exc)

    return customer_report, bureau_report, pdf_path
