"""Bureau PDF renderer - BureauReport to PDF/HTML conversion.

Parallel to pdf_renderer.py for customer reports.
Reuses ReportPDF class and _sanitize_text helper.

NO LLM calls - NO data manipulation - just rendering.
"""

import calendar
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from fpdf import FPDF

from schemas.bureau_report import BureauReport
from schemas.loan_type import get_loan_type_display_name
from .pdf_renderer import ReportPDF, _sanitize_text
from ..reports.key_findings import KeyFinding, findings_to_dicts
from utils.helpers import mask_customer_id, format_inr, format_inr_units


class BureauReportPDF(ReportPDF):
    """Custom PDF class for bureau reports — overrides header only."""

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "Bureau Tradeline Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)


_SEVERITY_LABELS = {
    "high_risk": "HIGH RISK",
    "moderate_risk": "MODERATE",
    "concern": "CONCERN",
    "positive": "POSITIVE",
    "neutral": "NEUTRAL",
}


def _render_key_finding(pdf, finding: KeyFinding):
    """Render a single key finding bullet in the PDF."""
    # Category label
    pdf.set_font("Helvetica", "I", 7)
    pdf.cell(0, 5, finding.category, new_x="LMARGIN", new_y="NEXT")

    # Finding (bold bullet)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 8)
    pdf.multi_cell(0, 5, _sanitize_text(f"  {finding.finding}"))

    # Inference (italic)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(0, 4, _sanitize_text(f"  -> {finding.inference}"))
    pdf.ln(2)


def _render_group_header(pdf, title: str):
    """Render a sub-group header in the PDF."""
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")


def _render_feature_pair(pdf, label: str, value):
    """Render a label-value pair, showing 'N/A' for None."""
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(100, 6, f"{label}:")
    pdf.set_font("Helvetica", "", 9)
    if value is None:
        display = "N/A"
    elif isinstance(value, float):
        display = f"{value:.2f}"
    else:
        display = str(value)
    pdf.cell(0, 6, display, new_x="LMARGIN", new_y="NEXT")


def _compute_html_chart_data(vectors_data: list, ei, monthly_exposure=None) -> str:
    """Compute chart datasets and return as a pre-serialized JSON string.

    Pre-serializing in Python avoids Jinja2 tojson filter issues with
    non-standard types (enums, numpy ints, etc.) that may be present in
    the feature vector dicts after asdict() conversion.
    """
    product_labels = [str(v["loan_type_display"]) for v in vectors_data]
    product_values = [int(v["loan_count"]) for v in vectors_data]

    secured   = int(sum(int(v["loan_count"]) for v in vectors_data if v.get("secured")))
    unsecured = int(sum(int(v["loan_count"]) for v in vectors_data if not v.get("secured")))

    on_us  = int(sum(int(v.get("on_us_count", 0)) for v in vectors_data))
    off_us = int(sum(int(v.get("off_us_count", 0)) for v in vectors_data))

    unsec_out_labels = [
        str(v["loan_type_display"]) for v in vectors_data
        if not v.get("secured") and float(v.get("total_outstanding_amount") or 0) > 0
    ]
    unsec_out_values = [
        float(v["total_outstanding_amount"]) for v in vectors_data
        if not v.get("secured") and float(v.get("total_outstanding_amount") or 0) > 0
    ]

    # Normalise monthly_exposure series values to plain Python floats
    ts: dict = {"months": [], "series": {}}
    if monthly_exposure:
        ts["months"] = [str(m) for m in monthly_exposure.get("months", [])]
        ts["series"] = {
            str(k): [float(x) for x in v]
            for k, v in monthly_exposure.get("series", {}).items()
        }

    # --- DPD Timeline ---
    # Generate 24-month labels (reuse from monthly_exposure if available)
    if ts["months"]:
        months_24 = ts["months"]
    else:
        today = date.today()
        months_24 = []
        for i in range(23, -1, -1):
            month = (today.month - 1 - i) % 12 + 1
            year = today.year + (today.month - 1 - i) // 12
            months_24.append(f"{calendar.month_abbr[month]} {year}")

    dpd_events = []
    dpd_historical = []
    for vec in vectors_data:
        dpd = vec.get("max_dpd") or 0
        months_ago = vec.get("max_dpd_months_ago")
        lt = str(vec.get("loan_type_display", "Unknown"))
        if dpd <= 0 or months_ago is None:
            continue
        idx = 23 - int(months_ago)   # months_24[23]=current month, [0]=23M ago
        if 0 <= idx < 24:
            dpd_events.append({
                "loan_type": lt,
                "dpd": int(dpd),
                "month_idx": idx,
                "month_label": months_24[idx],
            })
        else:
            dpd_historical.append({"loan_type": lt, "dpd": int(dpd), "months_ago": int(months_ago)})

    data = {
        "product_mix":      {"labels": product_labels,              "values": product_values},
        "secured_split":    {"labels": ["Secured", "Unsecured"],    "values": [secured, unsecured]},
        "onus_offus":       {"labels": ["On-Us (Kotak)", "Off-Us"], "values": [on_us, off_us]},
        "unsec_outstanding":{"labels": unsec_out_labels,            "values": unsec_out_values},
        "timeseries":       ts,
        "dpd_timeline":     {"months": months_24, "events": dpd_events, "historical": dpd_historical},
    }
    return json.dumps(data)


def _build_bureau_pdf(report: BureauReport) -> FPDF:
    """Build PDF document from BureauReport."""
    pdf = BureauReportPDF()
    pdf.add_page()

    # -- Page 1: Executive Summary --

    # Meta information
    pdf.section_title("Report Information")
    pdf.key_value("Customer ID", mask_customer_id(report.meta.customer_id))
    pdf.key_value("Generated", report.meta.generated_at[:10] if report.meta.generated_at else "N/A")
    pdf.key_value("Currency", report.meta.currency)
    pdf.key_value("Total Tradelines", str(report.executive_inputs.total_tradelines))
    pdf.ln(5)

    # Key metrics grid
    pdf.section_title("Portfolio Summary")
    ei = report.executive_inputs
    pdf.key_value("Live Tradelines", str(ei.live_tradelines))
    pdf.key_value("Total Sanction Amount", f"INR {format_inr(ei.total_sanctioned)}")
    pdf.key_value("Total Outstanding", f"INR {format_inr(ei.total_outstanding)}")
    pdf.key_value("Unsecured Sanction Amount", f"INR {format_inr(ei.unsecured_sanctioned)}")
    # Unsecured outstanding as % of total outstanding
    if ei.total_outstanding > 0:
        unsec_os_pct = ei.unsecured_outstanding / ei.total_outstanding * 100
        pdf.key_value("Unsecured Outstanding", f"{unsec_os_pct:.0f}% of total outstanding")
    else:
        pdf.key_value("Unsecured Outstanding", "N/A")
    # Max DPD with timing
    dpd_str = str(ei.max_dpd) if ei.max_dpd is not None else "N/A"
    if ei.max_dpd is not None:
        details = []
        if ei.max_dpd_months_ago is not None:
            details.append(f"{ei.max_dpd_months_ago} months ago")
        if ei.max_dpd_loan_type:
            details.append(ei.max_dpd_loan_type)
        if details:
            dpd_str += f" ({', '.join(details)})"
    pdf.key_value("Max DPD", dpd_str)
    pdf.ln(5)

    # Narrative (LLM-generated executive summary)
    if report.narrative:
        pdf.section_title("Executive Summary")
        pdf.section_text(report.narrative)
        pdf.ln(3)

    # Key Findings & Inferences
    if report.key_findings:
        pdf.add_page()
        pdf.section_title("Key Findings & Inferences")
        pdf.ln(2)
        for finding in report.key_findings:
            _render_key_finding(pdf, finding)

    # -- Product-wise Table --
    pdf.add_page()
    pdf.section_title("Product-wise Breakdown")

    headers = [
        "Type", "Sec", "Count", "Live", "Closed",
        "Sanctioned", "Outstanding", "Max DPD", "Util%",
        "On-Us"
    ]
    widths = [30, 12, 16, 14, 16, 30, 30, 18, 14, 16]

    pdf.set_font("Helvetica", "B", 7)
    pdf.set_fill_color(220, 220, 220)
    for header, width in zip(headers, widths):
        pdf.cell(width, 7, header, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    for loan_type, vec in report.feature_vectors.items():
        secured = "Y" if vec.secured else "N"
        util = f"{vec.utilization_ratio * 100:.0f}" if vec.utilization_ratio is not None else "-"
        max_dpd = str(vec.max_dpd) if vec.max_dpd is not None else "-"

        values = [
            get_loan_type_display_name(loan_type)[:14],
            secured,
            str(vec.loan_count),
            str(vec.live_count),
            str(vec.closed_count),
            format_inr(vec.total_sanctioned_amount),
            format_inr(vec.total_outstanding_amount),
            max_dpd,
            util,
            str(vec.on_us_count),
        ]

        for val, width in zip(values, widths):
            display_val = str(val)[:14]
            pdf.cell(width, 6, display_val, border=1, align="C")
        pdf.ln()

    # Totals row
    pdf.set_font("Helvetica", "B", 7)
    ei = report.executive_inputs
    totals = [
        "TOTAL", "",
        str(ei.total_tradelines),
        str(ei.live_tradelines),
        str(ei.closed_tradelines),
        format_inr(ei.total_sanctioned),
        format_inr(ei.total_outstanding),
        str(ei.max_dpd) if ei.max_dpd is not None else "-",
        "", ""
    ]
    for val, width in zip(totals, widths):
        pdf.cell(width, 6, val, border=1, align="C")
    pdf.ln()

    # -- Page 3: Behavioral & Risk Features --
    if report.tradeline_features is not None:
        pdf.add_page()
        pdf.section_title("Behavioral & Risk Features")
        tf = report.tradeline_features

        # Loan Activity
        _render_group_header(pdf, "Loan Activity")
        _render_feature_pair(pdf, "Months Since Last PL Trade Opened", tf.months_since_last_trade_pl)
        _render_feature_pair(pdf, "Months Since Last Unsecured Trade Opened", tf.months_since_last_trade_uns)
        _render_feature_pair(pdf, "New PL Trades in Last 6 Months", tf.new_trades_6m_pl)
        pdf.ln(3)

        # DPD & Delinquency
        _render_group_header(pdf, "DPD & Delinquency")
        _render_feature_pair(pdf, "Max DPD Last 6M (CC)", tf.max_dpd_6m_cc)
        _render_feature_pair(pdf, "Max DPD Last 6M (PL)", tf.max_dpd_6m_pl)
        _render_feature_pair(pdf, "Max DPD Last 9M (CC)", tf.max_dpd_9m_cc)
        _render_feature_pair(pdf, "Months Since Last 0+ DPD (Unsecured)", tf.months_since_last_0p_uns)
        _render_feature_pair(pdf, "Months Since Last 0+ DPD (PL)", tf.months_since_last_0p_pl)
        pdf.ln(3)

        # Payment Behavior
        _render_group_header(pdf, "Payment Behavior")
        _render_feature_pair(pdf, "% Trades with 0+ DPD in 24M (All)", tf.pct_0plus_24m_all)
        _render_feature_pair(pdf, "% Trades with 0+ DPD in 24M (PL)", tf.pct_0plus_24m_pl)
        _render_feature_pair(pdf, "% Missed Payments Last 18M", tf.pct_missed_payments_18m)
        _render_feature_pair(pdf, "% Trades with 0+ DPD in 12M (All)", tf.pct_trades_0plus_12m)
        _render_feature_pair(pdf, "Ratio Good Closed Loans (PL) %",
                            tf.ratio_good_closed_pl * 100 if tf.ratio_good_closed_pl is not None else None)
        pdf.ln(3)

        # Utilization
        _render_group_header(pdf, "Utilization")
        _render_feature_pair(pdf, "CC Balance Utilization %", tf.cc_balance_utilization_pct)
        _render_feature_pair(pdf, "PL Balance Remaining %", tf.pl_balance_remaining_pct)
        pdf.ln(3)

        # Enquiry Behavior
        _render_group_header(pdf, "Enquiry Behavior")
        _render_feature_pair(pdf, "Unsecured Enquiries Last 12M", tf.unsecured_enquiries_12m)
        _render_feature_pair(pdf, "Trade-to-Enquiry Ratio (Unsec 24M)", tf.trade_to_enquiry_ratio_uns_24m)
        pdf.ln(3)

        # Loan Acquisition Velocity
        _render_group_header(pdf, "Loan Acquisition Velocity")
        _render_feature_pair(pdf, "Avg Interpurchase Time 12M (PL/BL)", tf.interpurchase_time_12m_plbl)
        _render_feature_pair(pdf, "Avg Interpurchase Time 6M (PL/BL)", tf.interpurchase_time_6m_plbl)
        _render_feature_pair(pdf, "Avg Interpurchase Time 24M (All)", tf.interpurchase_time_24m_all)
        _render_feature_pair(pdf, "Avg Interpurchase Time 9M (HL/LAP)", tf.interpurchase_time_9m_hl_lap)
        _render_feature_pair(pdf, "Avg Interpurchase Time 24M (HL/LAP)", tf.interpurchase_time_24m_hl_lap)
        _render_feature_pair(pdf, "Avg Interpurchase Time 24M (TWL)", tf.interpurchase_time_24m_twl)
        _render_feature_pair(pdf, "Avg Interpurchase Time 12M (Consumer Loan)", tf.interpurchase_time_12m_cl)

    return pdf


def render_bureau_report_pdf(
    report: BureauReport,
    output_path: Optional[str] = None,
) -> str:
    """Render a BureauReport to PDF (and HTML).

    Args:
        report: Fully populated BureauReport.
        output_path: Desired output file path (.pdf). Defaults to
                      reports/bureau_{customer_id}_report.pdf.

    Returns:
        Path where PDF was saved.
    """
    if output_path is None:
        output_path = f"reports/bureau_{report.meta.customer_id}_report.pdf"

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Build and save PDF
    pdf = _build_bureau_pdf(report)
    pdf.output(str(output_file))

    # Also save HTML version for browser viewing
    html_path = str(output_file).replace(".pdf", ".html")
    html_content = render_bureau_report_html(report)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return str(output_file)


def render_bureau_report_html(report: BureauReport) -> str:
    """Render a BureauReport to HTML string using Jinja2 template.

    Args:
        report: BureauReport to render.

    Returns:
        HTML string.
    """
    template_dir = Path(__file__).parent.parent.parent / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    env.filters["mask_id"] = mask_customer_id
    env.filters["inr"] = format_inr
    env.filters["inr_units"] = format_inr_units

    # Prepare template data — convert feature vectors to dicts for Jinja
    vectors_data = []
    for loan_type, vec in report.feature_vectors.items():
        vec_dict = asdict(vec)
        vec_dict["loan_type_display"] = get_loan_type_display_name(loan_type)
        vec_dict["secured"] = vec.secured
        vectors_data.append(vec_dict)

    # Prepare tradeline features for template
    tl_features_data = None
    if report.tradeline_features is not None:
        tl_features_data = asdict(report.tradeline_features)

    # Prepare key findings for template
    key_findings_data = findings_to_dicts(report.key_findings) if report.key_findings else []

    chart_data = _compute_html_chart_data(vectors_data, report.executive_inputs, report.monthly_exposure)

    from tools.scorecard import compute_scorecard
    scorecard = compute_scorecard(bureau_report=report)

    template = env.get_template("bureau_report.html")
    return template.render(
        report=report,
        vectors_data=vectors_data,
        tl_features=tl_features_data,
        key_findings=key_findings_data,
        chart_data=chart_data,
        scorecard=scorecard,
    )
