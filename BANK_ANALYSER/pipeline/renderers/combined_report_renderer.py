"""Combined report renderer - merges CustomerReport + BureauReport into one PDF/HTML.

Reuses ReportPDF base class and rendering helpers from both existing renderers.
NO LLM calls - NO data manipulation - just rendering.

Either report may be None when the corresponding data source is unavailable.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from fpdf import FPDF

import numpy as np
import config.thresholds as T

from schemas.customer_report import CustomerReport
from schemas.bureau_report import BureauReport
from schemas.loan_type import get_loan_type_display_name
from .pdf_renderer import ReportPDF, _sanitize_text
from .bureau_pdf_renderer import (
    _render_key_finding, _render_group_header, _render_feature_pair,
    _compute_html_chart_data,
)
from ..reports.key_findings import findings_to_dicts
from utils.helpers import mask_customer_id, format_inr, format_inr_units, strip_segment_prefix


class CombinedReportPDF(ReportPDF):
    """Custom PDF class for combined reports — overrides header only."""

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "Combined Financial & Bureau Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)


def _render_absence_note(pdf: FPDF, source_name: str) -> None:
    """Render a styled note indicating a data source is unavailable."""
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(180, 60, 60)
    pdf.cell(
        0, 8,
        f"  {source_name} data is not available for this customer.",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)


def _build_combined_pdf(
    customer_report: Optional[CustomerReport],
    bureau_report: Optional[BureauReport],
    combined_summary: Optional[str] = None,
) -> FPDF:
    """Build a single PDF document from both reports."""
    pdf = CombinedReportPDF()
    pdf.add_page()

    # =====================================================================
    # META / REPORT INFORMATION
    # =====================================================================
    pdf.section_title("Report Information")
    if customer_report:
        pdf.key_value("Customer ID", mask_customer_id(customer_report.meta.customer_id))
        if customer_report.meta.prty_name:
            pdf.key_value("Customer Name", customer_report.meta.prty_name)
        pdf.key_value("Generated", customer_report.meta.generated_at[:10] if customer_report.meta.generated_at else "N/A")
        pdf.key_value("Period", customer_report.meta.analysis_period)
        pdf.key_value("Currency", customer_report.meta.currency)
        pdf.key_value("Transactions", str(customer_report.meta.transaction_count))
    if bureau_report:
        pdf.key_value("Tradelines", str(bureau_report.executive_inputs.total_tradelines))
    pdf.ln(5)

    # =====================================================================
    # PART 1: BUREAU REPORT
    # =====================================================================

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_fill_color(44, 62, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, "  Bureau Tradeline Analysis", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    if bureau_report:
        ei = bureau_report.executive_inputs

        # Portfolio Summary
        pdf.section_title("Portfolio Summary")
        pdf.key_value("Live Tradelines", str(ei.live_tradelines))
        pdf.key_value("Total Sanction Amount", f"INR {format_inr(ei.total_sanctioned)}")
        pdf.key_value("Total Outstanding", f"INR {format_inr(ei.total_outstanding)}")
        pdf.key_value("Unsecured Sanction Amount", f"INR {format_inr(ei.unsecured_sanctioned)}")
        # Unsecured outstanding %
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

        # Largest Single Loan
        if ei.max_single_sanction_amount > 0:
            max_loan_str = f"INR {format_inr(ei.max_single_sanction_amount)}"
            if ei.max_single_sanction_loan_type:
                max_loan_str += f" ({ei.max_single_sanction_loan_type})"
            pdf.key_value("Largest Single Loan", max_loan_str)

        # Joint Loans
        if ei.total_joint_count > 0:
            joint_str = f"{ei.total_joint_count} tradeline(s) — {', '.join(ei.joint_product_types)}"
            pdf.key_value("Joint Loans", joint_str)

        # Kotak (On-Us) sub-section
        if ei.on_us_total_tradelines > 0:
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 6, "Kotak Relationship (On-Us)", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            pdf.key_value("On-Us Tradelines", f"{ei.on_us_total_tradelines} ({ei.on_us_live_tradelines} live)")
            pdf.key_value("Products", ", ".join(ei.on_us_product_types))
            pdf.key_value("Sanctioned", f"INR {format_inr(ei.on_us_total_sanctioned)}")
            pdf.key_value("Outstanding", f"INR {format_inr(ei.on_us_total_outstanding)}")
            if ei.on_us_max_dpd is not None and ei.on_us_max_dpd > 0:
                pdf.key_value("On-Us Max DPD", str(ei.on_us_max_dpd))

        pdf.ln(5)

        # Defaulted / Delinquent Loan Types table
        if ei.defaulted_loan_summaries:
            pdf.section_title("Defaulted / Delinquent Loan Types")
            d_headers = ["Loan Type", "Sanctioned", "Outstanding", "Max DPD", "Kotak"]
            d_widths = [40, 40, 40, 25, 20]
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_fill_color(220, 220, 220)
            for header, width in zip(d_headers, d_widths):
                pdf.cell(width, 7, header, border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_font("Helvetica", "", 7)
            for d in ei.defaulted_loan_summaries:
                vals = [
                    d["type"],
                    format_inr(d["sanction"]),
                    format_inr(d["outstanding"]),
                    str(d["dpd"]) if d["dpd"] is not None else "-",
                    "Yes" if d["on_us"] else "No",
                ]
                for val, width in zip(vals, d_widths):
                    pdf.cell(width, 6, val, border=1, align="C")
                pdf.ln()
            pdf.ln(3)

        # Bureau Narrative
        if bureau_report.narrative:
            pdf.section_title("Bureau Executive Summary")
            pdf.section_text(bureau_report.narrative)
            pdf.ln(3)

        # Key Findings
        if bureau_report.key_findings:
            pdf.add_page()
            pdf.section_title("Key Findings & Inferences")
            pdf.ln(2)
            for finding in bureau_report.key_findings:
                _render_key_finding(pdf, finding)

        # Product-wise Table
        pdf.add_page()
        pdf.section_title("Product-wise Breakdown")
        headers = [
            "Type", "Sec", "Count", "Live", "Closed",
            "Sanctioned", "Outstanding", "Max DPD", "Util%", "On-Us"
        ]
        widths = [30, 12, 16, 14, 16, 30, 30, 18, 14, 16]
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_fill_color(220, 220, 220)
        for header, width in zip(headers, widths):
            pdf.cell(width, 7, header, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        for loan_type, vec in bureau_report.feature_vectors.items():
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
                max_dpd, util,
                str(vec.on_us_count),
            ]
            for val, width in zip(values, widths):
                pdf.cell(width, 6, str(val)[:14], border=1, align="C")
            pdf.ln()

        # Totals row
        pdf.set_font("Helvetica", "B", 7)
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

        # Behavioral & Risk Features
        if bureau_report.tradeline_features is not None:
            pdf.add_page()
            pdf.section_title("Behavioral & Risk Features")
            tf = bureau_report.tradeline_features

            _render_group_header(pdf, "Loan Activity")
            _render_feature_pair(pdf, "Months Since Last PL Trade Opened", tf.months_since_last_trade_pl)
            _render_feature_pair(pdf, "Months Since Last Unsecured Trade Opened", tf.months_since_last_trade_uns)
            _render_feature_pair(pdf, "New PL Trades in Last 6 Months", tf.new_trades_6m_pl)
            pdf.ln(3)

            _render_group_header(pdf, "DPD & Delinquency")
            _render_feature_pair(pdf, "Max DPD Last 6M (CC)", tf.max_dpd_6m_cc)
            _render_feature_pair(pdf, "Max DPD Last 6M (PL)", tf.max_dpd_6m_pl)
            _render_feature_pair(pdf, "Max DPD Last 9M (CC)", tf.max_dpd_9m_cc)
            _render_feature_pair(pdf, "Months Since Last 0+ DPD (Unsecured)", tf.months_since_last_0p_uns)
            _render_feature_pair(pdf, "Months Since Last 0+ DPD (PL)", tf.months_since_last_0p_pl)
            pdf.ln(3)

            _render_group_header(pdf, "Payment Behavior")
            _render_feature_pair(pdf, "% Trades with 0+ DPD in 24M (All)", tf.pct_0plus_24m_all)
            _render_feature_pair(pdf, "% Trades with 0+ DPD in 24M (PL)", tf.pct_0plus_24m_pl)
            _render_feature_pair(pdf, "% Missed Payments Last 18M", tf.pct_missed_payments_18m)
            _render_feature_pair(pdf, "% Trades with 0+ DPD in 12M (All)", tf.pct_trades_0plus_12m)
            _render_feature_pair(pdf, "Ratio Good Closed Loans (PL) %",
                                tf.ratio_good_closed_pl * 100 if tf.ratio_good_closed_pl is not None else None)
            pdf.ln(3)

            _render_group_header(pdf, "Utilization")
            _render_feature_pair(pdf, "CC Balance Utilization %", tf.cc_balance_utilization_pct)
            _render_feature_pair(pdf, "PL Outstanding %", tf.pl_balance_remaining_pct)
            pdf.ln(3)

            _render_group_header(pdf, "Enquiry Behavior")
            _render_feature_pair(pdf, "Unsecured Enquiries Last 12M", tf.unsecured_enquiries_12m)
            _render_feature_pair(pdf, "Trade-to-Enquiry Ratio (Unsec 24M)", tf.trade_to_enquiry_ratio_uns_24m)
            pdf.ln(3)

            _render_group_header(pdf, "Loan Acquisition Velocity")
            _render_feature_pair(pdf, "Avg Interpurchase Time 12M (PL/BL)", tf.interpurchase_time_12m_plbl)
            _render_feature_pair(pdf, "Avg Interpurchase Time 6M (PL/BL)", tf.interpurchase_time_6m_plbl)
            _render_feature_pair(pdf, "Avg Interpurchase Time 24M (All)", tf.interpurchase_time_24m_all)
            _render_feature_pair(pdf, "Avg Interpurchase Time 9M (HL/LAP)", tf.interpurchase_time_9m_hl_lap)
            _render_feature_pair(pdf, "Avg Interpurchase Time 24M (HL/LAP)", tf.interpurchase_time_24m_hl_lap)
            _render_feature_pair(pdf, "Avg Interpurchase Time 24M (TWL)", tf.interpurchase_time_24m_twl)
            _render_feature_pair(pdf, "Avg Interpurchase Time 12M (Consumer Loan)", tf.interpurchase_time_12m_cl)
    else:
        _render_absence_note(pdf, "Bureau tradeline")

    # =====================================================================
    # DIVIDER
    # =====================================================================
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_fill_color(44, 62, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, "  Banking / Transaction Report", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    # =====================================================================
    # PART 2: BANKING / TRANSACTION REPORT
    # =====================================================================

    if customer_report:
        # Customer Profile (LLM persona)
        if customer_report.customer_persona:
            pdf.section_title("Customer Profile")
            pdf.section_text(customer_report.customer_persona)
            pdf.ln(3)

        # Executive Summary (LLM review)
        if customer_report.customer_review:
            pdf.section_title("Executive Summary")
            pdf.section_text(customer_report.customer_review)
            pdf.ln(3)

        # Salary
        if customer_report.salary:
            pdf.section_title("Salary Information")
            pdf.key_value("Average Amount", f"{customer_report.salary.avg_amount:,.2f} {customer_report.meta.currency}")
            pdf.key_value("Frequency", f"{customer_report.salary.frequency} transactions")
            if customer_report.salary.narration:
                pdf.key_value("Description", customer_report.salary.narration[:50])
            if customer_report.salary.latest_transaction:
                latest = customer_report.salary.latest_transaction
                pdf.key_value("Latest Transaction", f"{latest.get('amount', 0):,.2f} {customer_report.meta.currency}")
                pdf.key_value("Latest Date", latest.get('date', 'N/A')[:10])
            pdf.ln(3)

        # Category Overview
        if customer_report.category_overview:
            pdf.section_title("Spending by Category")
            sorted_cats = sorted(customer_report.category_overview.items(), key=lambda x: x[1], reverse=True)
            widths = [80, 50, 60]
            pdf.table_header(["Category", "Amount", "% of Total"], widths)
            total = sum(customer_report.category_overview.values())
            for cat, amount in sorted_cats:
                pct = (amount / total * 100) if total > 0 else 0
                pdf.table_row([cat, f"{amount:,.0f}", f"{pct:.1f}%"], widths)
            pdf.ln(5)

        # Monthly Cash Flow
        if customer_report.monthly_cashflow:
            pdf.section_title("Monthly Cash Flow")
            widths = [40, 45, 45, 45]
            pdf.table_header(["Month", "Inflow", "Outflow", "Net"], widths)
            for m in customer_report.monthly_cashflow:
                pdf.table_row([
                    m.get("month", "N/A"),
                    f"{m.get('inflow', 0):,.0f}",
                    f"{m.get('outflow', 0):,.0f}",
                    f"{m.get('net', 0):,.0f}"
                ], widths)
            total_in = sum(m.get('inflow', 0) for m in customer_report.monthly_cashflow)
            total_out = sum(m.get('outflow', 0) for m in customer_report.monthly_cashflow)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(40, 6, "TOTAL", border=1, align="C")
            pdf.cell(45, 6, f"{total_in:,.0f}", border=1, align="C")
            pdf.cell(45, 6, f"{total_out:,.0f}", border=1, align="C")
            pdf.cell(45, 6, f"{total_in - total_out:,.0f}", border=1, align="C")
            pdf.ln(8)

        # EMI Payments
        if customer_report.emis:
            pdf.section_title("EMI Payments")
            widths = [80, 50, 60]
            pdf.table_header(["Name", "Amount", "Frequency"], widths)
            for emi in customer_report.emis:
                pdf.table_row([emi.name, f"{emi.amount:,.2f}", f"{emi.frequency}x"], widths)
            pdf.ln(3)

        # Rent
        if customer_report.rent:
            pdf.section_title("Rent")
            pdf.key_value("Direction", customer_report.rent.direction.capitalize())
            pdf.key_value("Amount", f"{customer_report.rent.amount:,.2f} {customer_report.meta.currency}")
            pdf.key_value("Frequency", f"{customer_report.rent.frequency} transactions")
            pdf.ln(3)

        # Utility Bills
        if customer_report.bills:
            pdf.section_title("Utility Bills")
            widths = [80, 50, 60]
            pdf.table_header(["Type", "Avg Amount", "Frequency"], widths)
            for bill in customer_report.bills:
                pdf.table_row([bill.bill_type, f"{bill.avg_amount:,.2f}", f"{bill.frequency}x"], widths)
            pdf.ln(3)

        # Top Merchants
        if customer_report.top_merchants:
            pdf.section_title("Top Merchants")
            widths = [70, 30, 45, 45]
            pdf.table_header(["Merchant", "Count", "Total", "Avg"], widths)
            for m in customer_report.top_merchants:
                pdf.table_row([
                    str(m.get("name", "N/A"))[:25],
                    str(m.get("count", 0)),
                    f"{m.get('total', 0):,.0f}",
                    f"{m.get('avg', 0):,.0f}"
                ], widths)
            pdf.ln(5)
    else:
        _render_absence_note(pdf, "Banking transaction")

    # =====================================================================
    # PART 3: COMBINED EXECUTIVE SUMMARY
    # =====================================================================
    if combined_summary:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_fill_color(44, 62, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 12, "  Combined Executive Summary", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(8)
        pdf.section_text(combined_summary)
        pdf.ln(3)

    return pdf


def render_combined_report(
    customer_report: Optional[CustomerReport],
    bureau_report: Optional[BureauReport],
    output_path: Optional[str] = None,
    combined_summary: Optional[str] = None,
    rg_salary_data: Optional[dict] = None,
    theme: str = "emerald",
    save_pdf: bool = True,
) -> str:
    """Render combined PDF + HTML from both reports.

    Args:
        customer_report: Fully populated CustomerReport, or None if unavailable.
        bureau_report: Fully populated BureauReport, or None if unavailable.
        output_path: Desired output file path (.pdf).
                      Defaults to reports/combined_{customer_id}_report.pdf.
        combined_summary: LLM-generated synthesised executive summary.
        rg_salary_data: Optional internal salary algorithm data dict.
        save_pdf: When False, skip PDF generation — only save HTML.

    Returns:
        Path where the output was saved (PDF path if save_pdf, else HTML path).
    """
    if output_path is None:
        # Derive customer_id from whichever report is available
        if customer_report:
            cid = customer_report.meta.customer_id
        elif bureau_report:
            cid = bureau_report.meta.customer_id
        else:
            cid = "unknown"
        output_path = f"reports/combined_{cid}_report.pdf"

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Build and save PDF (optional)
    if save_pdf:
        pdf = _build_combined_pdf(customer_report, bureau_report, combined_summary)
        pdf.output(str(output_file))

    # Save HTML version alongside the PDF
    html_path = str(output_file).replace(".pdf", ".html")
    html_content = render_combined_report_html(
        customer_report, bureau_report, combined_summary=combined_summary,
        rg_salary_data=rg_salary_data, theme=theme,
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Also copy HTML to dedicated combined_report_html_version folder
    html_version_dir = output_file.parent / "combined_report_html_version"
    html_version_dir.mkdir(parents=True, exist_ok=True)
    html_version_path = html_version_dir / Path(html_path).name
    with open(str(html_version_path), "w", encoding="utf-8") as f:
        f.write(html_content)

    return str(output_file) if save_pdf else html_path


_ADVERSE_FLAGS = {"WRF", "SET", "SMA", "SUB", "DBT", "LSS", "WOF"}
_BETTING_CATS = {"Digital_Betting_Gaming", "Betting_Gaming", "Betting", "Gaming"}


def compute_checklist(
    customer_report: Optional[CustomerReport],
    bureau_report: Optional[BureauReport],
    rg_salary_data: Optional[dict],
) -> dict:
    """Compute yes/no checklist items from existing report data.

    Returns dict with keys ``bureau`` and ``banking``, each a list of
    dicts: {label, checked, severity, detail}.
    """
    bureau_items: list = []
    banking_items: list = []
    events = (customer_report.events or []) if customer_report else []

    def _events_of_type(etype):
        return [e for e in events if e.get("type") == etype]

    # ── BUREAU CHECKLIST ──────────────────────────────────────────

    # B1. Max DPD occurred
    has_dpd = False
    dpd_detail = None
    if bureau_report:
        ei = bureau_report.executive_inputs
        if ei.max_dpd is not None and ei.max_dpd > 0:
            has_dpd = True
            parts = [f"{ei.max_dpd} days"]
            if ei.max_dpd_loan_type:
                parts.append(ei.max_dpd_loan_type)
            if ei.max_dpd_months_ago is not None:
                parts.append(f"{ei.max_dpd_months_ago}M ago")
            dpd_detail = " — ".join(parts)
    bureau_items.append({
        "label": "MAX DPD occurred",
        "checked": has_dpd,
        "severity": "high" if has_dpd else "positive",
        "detail": dpd_detail,
    })

    # B2. Adverse events (write-off / settlement)
    adverse_flags = []
    if bureau_report:
        for vec in bureau_report.feature_vectors.values():
            for f in (vec.forced_event_flags or []):
                if f in _ADVERSE_FLAGS:
                    adverse_flags.append(f)
    has_adverse = bool(adverse_flags)
    bureau_items.append({
        "label": "Adverse events (write-off / settlement)",
        "checked": has_adverse,
        "severity": "high" if has_adverse else "positive",
        "detail": f"Flags: {', '.join(sorted(set(adverse_flags)))}" if has_adverse else None,
    })

    # B3. High FOIR (>50%)
    foir_val = None
    if bureau_report and bureau_report.tradeline_features:
        foir_val = bureau_report.tradeline_features.foir
    has_high_foir = foir_val is not None and foir_val > 50
    bureau_items.append({
        "label": "High FOIR (> 50%)",
        "checked": has_high_foir,
        "severity": "high" if (foir_val and foir_val > 65) else ("medium" if has_high_foir else "neutral"),
        "detail": f"Bureau FOIR: {foir_val:.1f}%" if foir_val is not None else None,
    })

    # B4. CC utilization elevated (>=30%)
    cc_util = None
    if bureau_report:
        from schemas.loan_type import LoanType
        cc_vec = bureau_report.feature_vectors.get(LoanType.CC)
        if cc_vec and cc_vec.utilization_ratio is not None:
            cc_util = cc_vec.utilization_ratio * 100  # convert fraction to percentage
    bureau_items.append({
        "label": "CC utilization elevated (\u226530%)",
        "checked": cc_util is not None and cc_util >= 30,
        "severity": "high" if (cc_util is not None and cc_util >= 75) else (
            "medium" if (cc_util is not None and cc_util >= 30) else "positive"
        ),
        "detail": f"CC utilization: {cc_util:.1f}%" if cc_util is not None else None,
    })

    # B5. Kotak loan presence
    kotak_total = 0
    kotak_type_dist: list = []
    if bureau_report:
        from schemas.loan_type import LoanType
        for lt, vec in bureau_report.feature_vectors.items():
            if vec.on_us_count > 0:
                kotak_total += vec.on_us_count
                kotak_type_dist.append(f"{lt.value}({vec.on_us_count})")
    kotak_detail = None
    if kotak_total > 0:
        kotak_detail = f"{kotak_total} Kotak loan(s): {', '.join(kotak_type_dist)}"
    bureau_items.append({
        "label": "Customer has Kotak loan",
        "checked": kotak_total > 0,
        "severity": "neutral" if kotak_total > 0 else "neutral",
        "detail": kotak_detail,
    })

    # B6. Kotak loan default (live loans only) — query raw bureau data
    kotak_defaults: list = []
    try:
        if bureau_report:
            from pipeline.extractors.bureau_feature_extractor import _load_bureau_data
            from schemas.loan_type import ON_US_SECTORS, normalize_loan_type
            cust_id = bureau_report.meta.customer_id
            if cust_id is not None:
                _CLOSED = {"closed", "written off", "written-off", "settled", "npa", "loss", "doubtful", "write-off"}
                raw_rows = _load_bureau_data()
                cust_str = str(cust_id)
                for row in raw_rows:
                    if str(row.get("crn", "")).strip() != cust_str:
                        continue
                    sector = str(row.get("sector", "")).strip().upper()
                    if sector not in ON_US_SECTORS:
                        continue
                    status = str(row.get("loan_status", "")).strip().lower()
                    if status in _CLOSED:
                        continue
                    # Live Kotak tradeline — check for default
                    raw_dpd = 0
                    try:
                        raw_dpd = int(float(row.get("max_dpd", 0) or 0))
                    except (ValueError, TypeError):
                        pass
                    dpd_str = str(row.get("dpd_string", "")).upper()
                    has_adverse_flag = any(f in dpd_str for f in _ADVERSE_FLAGS)
                    if raw_dpd > 0 or has_adverse_flag:
                        lt_raw = str(row.get("loan_type_new", "")).strip()
                        lt_canonical = normalize_loan_type(lt_raw)
                        parts = [lt_canonical.value]
                        if raw_dpd > 0:
                            parts.append(f"DPD {raw_dpd}")
                        if has_adverse_flag:
                            flags = [f for f in _ADVERSE_FLAGS if f in dpd_str]
                            parts.append(f"Flags: {','.join(flags)}")
                        kotak_defaults.append(" — ".join(parts))
    except Exception:
        pass  # fail-soft
    has_kotak_default = bool(kotak_defaults)
    bureau_items.append({
        "label": "Kotak loan default (live)",
        "checked": has_kotak_default,
        "severity": "high" if has_kotak_default else ("positive" if kotak_total > 0 else "neutral"),
        "detail": "; ".join(kotak_defaults[:5]) if has_kotak_default else None,
    })

    # B7. Live Home Loan detected
    hl_live = False
    hl_detail = None
    if bureau_report:
        from schemas.loan_type import LoanType
        hl_vec = bureau_report.feature_vectors.get(LoanType.HL)
        if hl_vec and hl_vec.live_count > 0:
            hl_live = True
            sanc = hl_vec.total_sanctioned_amount
            on_us = hl_vec.on_us_count
            off_us = hl_vec.off_us_count
            hl_detail = f"Sanctioned: ₹{sanc:,.0f} | On-Us: {on_us}, Off-Us: {off_us}"
    bureau_items.append({
        "label": "Live Home Loan detected",
        "checked": hl_live,
        "severity": "neutral" if hl_live else "neutral",
        "detail": hl_detail,
    })

    # B8. Bureau thickness
    bu_grp_val = None
    if bureau_report and bureau_report.tradeline_features:
        bu_grp_val = bureau_report.tradeline_features.bu_grp
    bu_thick = bu_grp_val is not None and "thick" in bu_grp_val.lower()
    bureau_items.append({
        "label": "Bureau thick",
        "checked": bu_thick,
        "severity": "positive" if bu_thick else "medium",
        "detail": None if bu_thick else (bu_grp_val if bu_grp_val else "Data unavailable"),
    })

    # B9. Banking thickness
    bank_grp_val = None
    if bureau_report and bureau_report.tradeline_features:
        bank_grp_val = bureau_report.tradeline_features.bank_grp
    bank_thick = bank_grp_val is not None and "thick" in bank_grp_val.lower()
    bureau_items.append({
        "label": "Banking thick",
        "checked": bank_thick,
        "severity": "positive" if bank_thick else "medium",
        "detail": None if bank_thick else (bank_grp_val if bank_grp_val else "Data unavailable"),
    })

    # B10. Exposure trend elevated
    exposure_elevated = False
    exposure_detail = None
    exposure_rag = "neutral"
    if bureau_report:
        from tools.scorecard import _exposure_signals
        signals = _exposure_signals(getattr(bureau_report, "monthly_exposure", None))
        if signals:
            chip = signals[0]
            exposure_rag = chip.get("rag", "neutral")
            exposure_elevated = exposure_rag in ("amber", "red")
            exposure_detail = f"{chip.get('label', 'Exposure')}: {chip.get('value', '')}"
    bureau_items.append({
        "label": "Exposure elevated",
        "checked": exposure_elevated,
        "severity": "high" if exposure_rag == "red" else (
            "medium" if exposure_elevated else ("positive" if exposure_rag == "green" else "neutral")
        ),
        "detail": exposure_detail,
    })

    # ── BANKING CHECKLIST ─────────────────────────────────────────

    # K1. ECS/NACH bounces
    bounces = _events_of_type("ecs_bounce")
    banking_items.append({
        "label": "ECS / NACH bounces",
        "checked": bool(bounces),
        "severity": "high" if bounces else "neutral",
        "detail": bounces[0].get("description") if bounces else None,
    })

    # K2. Loan disbursement detected
    loan_events = (_events_of_type("loan_disbursal")
                   or _events_of_type("loan_redistribution_suspect")
                   or [e for e in _events_of_type("large_single_credit")
                       if "lender" in str(e.get("description", "")).lower()
                       or "loan" in str(e.get("description", "")).lower()])
    banking_items.append({
        "label": "Loan disbursement detected",
        "checked": bool(loan_events),
        "severity": "high" if loan_events else "neutral",
        "detail": loan_events[0].get("description") if loan_events else None,
    })

    # K3. Post-disbursement fund usage
    disb_usage = _events_of_type("post_disbursement_usage")
    if disb_usage:
        ev = disb_usage[0]
        match_flag = ev.get("_amounts_match", False)
        conc_pct   = ev.get("_concentration_pct", 0)
        severity = "high" if match_flag else ("high" if conc_pct >= 50 else "medium")
        banking_items.append({
            "label": "Post-disbursement fund diversion",
            "checked": True,
            "severity": severity,
            "detail": ev.get("description"),
        })
    else:
        banking_items.append({
            "label": "Post-disbursement fund diversion",
            "checked": False,
            "severity": "neutral",
            "detail": None,
        })

    # K4. Salary detected
    has_salary = customer_report and customer_report.salary is not None
    sal_detail = None
    if has_salary:
        sal = customer_report.salary
        sal_detail = f"₹{sal.avg_amount:,.0f} avg ({sal.frequency} transactions)"
    banking_items.append({
        "label": "Salary detected in banking",
        "checked": has_salary,
        "severity": "positive" if has_salary else "neutral",
        "detail": sal_detail,
    })

    # K5. Post-salary self-transfer (paired with salary above)
    self_transfers = _events_of_type("self_transfer_post_salary")
    banking_items.append({
        "label": "Post-salary self-transfer",
        "checked": bool(self_transfers),
        "severity": "medium" if self_transfers else "neutral",
        "detail": self_transfers[0].get("description") if self_transfers else None,
    })

    # K6. EMI obligations
    has_emis = customer_report and customer_report.emis and len(customer_report.emis) > 0
    emi_detail = None
    if has_emis:
        total_emi = sum(e.amount for e in customer_report.emis)
        emi_detail = f"₹{total_emi:,.0f} total across {len(customer_report.emis)} lender(s)"
    banking_items.append({
        "label": "EMI obligations present",
        "checked": bool(has_emis),
        "severity": "medium" if has_emis else "neutral",
        "detail": emi_detail,
    })

    # K7. NACH mandate / SPLN EMI (paired with EMI above)
    mandate_emis = _events_of_type("mandate_emi")
    banking_items.append({
        "label": "NACH mandate EMI detected",
        "checked": bool(mandate_emis),
        "severity": "medium" if mandate_emis else "neutral",
        "detail": mandate_emis[0].get("description") if mandate_emis else None,
    })

    # K8. Rent payments
    has_rent = customer_report and customer_report.rent is not None
    banking_items.append({
        "label": "Rent payments present",
        "checked": bool(has_rent),
        "severity": "neutral",
        "detail": f"₹{customer_report.rent.amount:,.0f} ({customer_report.rent.frequency} transactions)" if has_rent else None,
    })

    # K9. Credit card bill payments
    cc_payments = _events_of_type("cc_payment")
    banking_items.append({
        "label": "Credit card bill payments",
        "checked": bool(cc_payments),
        "severity": "positive" if cc_payments else "neutral",
        "detail": cc_payments[0].get("description") if cc_payments else None,
    })

    # K11. Land payments
    land_events = _events_of_type("land_payment")
    banking_items.append({
        "label": "Land purchase payments",
        "checked": bool(land_events),
        "severity": "medium" if land_events else "neutral",
        "detail": land_events[0].get("description") if land_events else None,
    })

    # K12. ATM withdrawals — trend and location
    atm_events = _events_of_type("atm_withdrawal")
    if atm_events:
        ev = atm_events[0]
        is_elevated = ev.get("_is_elevated", False)
        addrs = ev.get("_addresses", [])
        detail = ev.get("description", "")
        if addrs:
            detail += f" | Likely nearby: {', '.join(addrs[:3])}"
        banking_items.append({
            "label": "ATM withdrawals elevated",
            "checked": is_elevated,
            "severity": "medium" if is_elevated else "neutral",
            "detail": detail,
        })
    else:
        banking_items.append({
            "label": "ATM withdrawals elevated",
            "checked": False,
            "severity": "neutral",
            "detail": None,
        })

    # K13–K15. Transaction-level checks (require raw DataFrame)
    try:
        from data.loader import get_transactions_df
        from utils.narration_utils import extract_recipient_name, clean_narration

        cust_id = customer_report.meta.customer_id if customer_report else None
        if cust_id is not None:
            df = get_transactions_df()
            cdf = df[df["cust_id"] == cust_id].copy()

            if not cdf.empty:
                narrations = cdf["tran_partclr"].fillna("")
                amounts = cdf["tran_amt_in_ac"].fillna(0).astype(float)
                directions = cdf["dr_cr_indctor"].fillna("")

                # --- K13. Credits / debits above 95th percentile ---------------
                outlier_parts = []
                for direction, label in [("C", "credit"), ("D", "debit")]:
                    mask = directions == direction
                    dir_amounts = amounts[mask]
                    if len(dir_amounts) < 5:
                        continue
                    p95 = np.percentile(dir_amounts, 95)
                    outliers = cdf[mask & (amounts > p95)]
                    for _, row in outliers.iterrows():
                        narr = str(row.get("tran_partclr", ""))
                        merchant = extract_recipient_name(narr) or clean_narration(narr) or "Unknown"
                        amt = float(row.get("tran_amt_in_ac", 0))
                        outlier_parts.append(f"{merchant}: ₹{amt:,.0f} ({label})")

                has_outliers = bool(outlier_parts)
                banking_items.append({
                    "label": "Transactions above 95th percentile",
                    "checked": has_outliers,
                    "severity": "medium" if has_outliers else "neutral",
                    "detail": "; ".join(outlier_parts[:5]) if has_outliers else None,
                })

                # --- K14. Automated (NACH / mandate) debit & credit count ------
                narr_upper = narrations.str.upper()
                auto_mask = narr_upper.str.contains("NACH|MANDATE", na=False, regex=True)
                auto_debits = int((auto_mask & (directions == "D")).sum())
                auto_credits = int((auto_mask & (directions == "C")).sum())
                auto_total = auto_debits + auto_credits
                banking_items.append({
                    "label": "Automated (NACH/mandate) transactions",
                    "checked": auto_total > 0,
                    "severity": "neutral",
                    "detail": f"{auto_total} total ({auto_debits} debits, {auto_credits} credits)" if auto_total > 0 else None,
                })

                # --- K15. Payment mode distribution shift -----------------
                import pandas as pd

                def _infer_mode(row):
                    """Infer payment mode from tran_type, falling back to narration."""
                    tt = row.get("tran_type")
                    if pd.notna(tt) and str(tt).strip():
                        return str(tt).strip()
                    nu = str(row.get("tran_partclr", "")).strip().upper()
                    if "UPI" in nu:
                        return "UPI"
                    if "NEFT" in nu:
                        return "NEFT"
                    if "IMPS" in nu:
                        return "IMPS"
                    if "RTGS" in nu:
                        return "RTGS"
                    if "NACH-" in nu:
                        return "NACH"
                    if "MB:RECEIVED" in nu or "MB:SENT" in nu:
                        return "Mobile Banking"
                    if "IFT-" in nu:
                        return "IFT"
                    if nu.startswith("IB:RECEIVED FROM") or "IB:FUND" in nu:
                        return "Internet Banking"
                    if nu.startswith("FUND TRF FROM") or nu.startswith("FT FROM") or nu.startswith("FUNDS TRF FROM"):
                        return "Funds Transfer"
                    if nu.startswith("ATL/") or nu.startswith("ATW/"):
                        return "ATM"
                    if nu.startswith("PG "):
                        return "Payment Gateway"
                    if nu.startswith("PCD/"):
                        return "Card Payment"
                    if nu.startswith("CLG TO "):
                        return "Cheque"
                    return "Other"

                _mode_col = cdf.apply(_infer_mode, axis=1)
                _dates = pd.to_datetime(cdf["tran_date"], format="%Y-%m-%d", errors="coerce")
                _periods = _dates.dt.to_period("M")
                _months_all = sorted(_periods.dropna().unique())

                if len(_months_all) >= T.MODE_SHIFT_MIN_MONTHS:
                    _recent_set = set(_months_all[-T.MODE_SHIFT_RECENT_MONTHS:])
                    _is_recent = _periods.map(
                        lambda m: m in _recent_set if pd.notna(m) else False
                    )

                    _earlier_mask = ~_is_recent & _periods.notna()
                    _recent_mask = _is_recent

                    if (int(_earlier_mask.sum()) >= T.MODE_SHIFT_MIN_TRANSACTIONS
                            and int(_recent_mask.sum()) >= T.MODE_SHIFT_MIN_TRANSACTIONS):

                        _e_dist = _mode_col[_earlier_mask].value_counts(normalize=True) * 100
                        _r_dist = _mode_col[_recent_mask].value_counts(normalize=True) * 100

                        _all_modes = sorted(set(_e_dist.index) | set(_r_dist.index))
                        _shifts = {}
                        for _m in _all_modes:
                            _old = _e_dist.get(_m, 0.0)
                            _new = _r_dist.get(_m, 0.0)
                            _delta = _new - _old
                            if abs(_delta) >= T.MODE_SHIFT_THRESHOLD_PP:
                                _shifts[_m] = (_old, _new, _delta)

                        if _shifts:
                            _parts = []
                            for _m, (_old, _new, _delta) in sorted(
                                _shifts.items(), key=lambda x: -abs(x[1][2])
                            ):
                                _sign = "+" if _delta > 0 else ""
                                _parts.append(
                                    f"{_m}: {_old:.0f}% \u2192 {_new:.0f}% ({_sign}{_delta:.0f}pp)"
                                )
                            banking_items.append({
                                "label": "Payment mode distribution shift",
                                "checked": True,
                                "severity": "medium",
                                "detail": "; ".join(_parts),
                            })
                        else:
                            banking_items.append({
                                "label": "Payment mode distribution shift",
                                "checked": False,
                                "severity": "neutral",
                                "detail": None,
                            })
                    else:
                        banking_items.append({
                            "label": "Payment mode distribution shift",
                            "checked": False,
                            "severity": "neutral",
                            "detail": None,
                        })
                else:
                    banking_items.append({
                        "label": "Payment mode distribution shift",
                        "checked": False,
                        "severity": "neutral",
                        "detail": None,
                    })
    except Exception:
        pass  # fail-soft: skip transaction-level checks if data unavailable

    # K16. Emerging merchants (new in recent months, absent before)
    if customer_report and customer_report.merchant_features:
        em = customer_report.merchant_features.get("emerging_merchants", {})
        em_list = em.get("emerging_merchants", [])
        if em_list:
            names = ", ".join(e["name"] for e in em_list[:3])
            detail = f"{len(em_list)} new: {names}"
            banking_items.append({"label": "Emerging merchants detected", "checked": True,
                                   "severity": "medium", "detail": detail})

    return {"bureau": bureau_items, "banking": banking_items}


# ---------------------------------------------------------------------------
# Persona classification — raw loan type sets
# ---------------------------------------------------------------------------
_MF_BL = {"Microfinance - Business Loan"}
_MF_HL = {"Microfinance - Housing Loan"}
_MF_PL = {"Microfinance - Personal Loan"}
_TRACTOR = {"Tractor Loan"}
_CE = {"Construction Equipment Loan"}
_CV = {"Commercial Vehicle Loan"}
_FLEET_CARD = {"Fleet Card"}
_GECL = {"GECL Loan Secured", "GECL Loan Unsecured"}
_EDUCATION = {"Education Loan", "P2P Education Loan"}
_LAS = {"Loan_against_securities", "Loan Against Shares/Securities"}
_NON_FUNDED = {
    "Non-Funded Credit Facility",
    "Business Non-Funded Credit Facility - General",
    "Business Non-Funded Credit Facility - Priority Sector-Others",
    "Business Non-Funded Credit Facility - Priority Sector - Agriculture",
    "Business Non-Funded Credit Facility - Priority Sector - Small Business",
}
_LOAN_TO_PROF = {"Loan to Professional"}
_CORP_CC = {"Corporate Credit Card"}
_SHORT_TERM_PL = {"Short Term Personal Loan"}
_TEMP_OD = {"Temporary Overdraft"}
_OD = {"Overdraft", "Prime Minister Jaan Dhan Yojana - Overdraft"}
_BL_ALL = {
    "Business Loan - General", "Business Loan - Secured", "Business Loan - Unsecured",
    "Business Loan - Priority Sector - Agriculture", "Business Loan - Priority Sector - Others",
    "Business Loan - Priority Sector - Small Business", "Business Loan Against Bank Deposits",
    "Mudra Loans - Shishu / Kishor / Tarun",
}
_BL_AGRI = {
    "Business Loan - Priority Sector - Agriculture",
    "Business Non-Funded Credit Facility - Priority Sector - Agriculture",
}
_HL_ALL = {"Housing Loan", "Home Loan", "Pradhan Mantri Awas Yojana - Credit Link Subsidy Scheme MAY CLSS"}
_CC_ALL = {"Credit Card", "Secured Credit Card"}
_PL_PLAIN = {"Personal Loan"}
_AL_ALL = {"Auto Loan (Personal)", "Auto Loan", "Used Car Loan"}
_GL_ALL = {"Gold Loan", "Priority Sector - Gold Loan"}
_LAD_ALL = {"Loan Against Bank Deposits"}
_GENERIC_SINGLE = {"Personal Loan", "Credit Card", "Consumer Loan", "Short Term Personal Loan", "Secured Credit Card"}


def _count_raw(raw_counts: dict, type_set: set) -> int:
    """Sum counts for all raw types matching a set."""
    return sum(raw_counts.get(t, 0) for t in type_set)


def _sum_sanctioned(raw_sanctioned: dict, type_set: set) -> float:
    """Sum sanctioned amounts for all raw types matching a set."""
    return sum(raw_sanctioned.get(t, 0.0) for t in type_set)


def _fmt_inr_short(amount: float) -> str:
    """Format amount as short INR string (e.g. '15L', '2.5Cr')."""
    if amount >= 1_00_00_000:
        return f"{amount / 1_00_00_000:.1f}Cr"
    elif amount >= 1_00_000:
        return f"{amount / 1_00_000:.0f}L"
    elif amount >= 1_000:
        return f"{amount / 1_000:.0f}K"
    return f"{amount:.0f}"


def compute_probable_persona(bureau_report: Optional[BureauReport]) -> dict:
    """Compute probable customer persona from bureau tradeline data.

    Evaluates all persona rules in waterfall priority order, collects all
    matches, and returns the top 2-3 by priority. Stress overlays are
    evaluated independently.

    Returns:
        {
            "profiles": [{"label": str, "track": str, "detail": str|None}, ...],
            "stress_flags": [{"label": str, "severity": str, "detail": str|None}, ...],
            "summary": "Probable profile of customer is X, Y"
        }
    """
    empty = {"profiles": [], "stress_flags": [], "summary": ""}

    if bureau_report is None:
        return empty
    if bureau_report.raw_loan_profile is None:
        empty["profiles"] = [{"label": "Insufficient Data", "track": "Thin File", "detail": "No bureau data available"}]
        empty["summary"] = "Probable profile of customer is Insufficient Data"
        return empty

    raw = bureau_report.raw_loan_profile
    rc = raw.get("raw_counts", {})
    rs = raw.get("raw_sanctioned", {})
    rl = raw.get("raw_live_counts", {})
    total_tl = raw.get("total_tradelines", 0)

    # Edge: no tradelines
    if total_tl == 0:
        return {
            "profiles": [{"label": "New to Credit", "track": "NTC", "detail": "Zero bureau tradelines"}],
            "stress_flags": [],
            "summary": "Probable profile of customer is New to Credit",
        }

    # Edge: single generic product
    if total_tl == 1:
        single_type = next(iter(rc), "")
        if single_type in _GENERIC_SINGLE:
            return {
                "profiles": [{"label": "Insufficient Data", "track": "Thin File", "detail": f"Single {single_type}"}],
                "stress_flags": [],
                "summary": "Probable profile of customer is Insufficient Data (thin file)",
            }

    matches = []  # list of {"label", "track", "priority", "detail"}

    # --- MF Track (priority=10) ---
    mf_bl = _count_raw(rc, _MF_BL)
    mf_hl = _count_raw(rc, _MF_HL)
    mf_pl = _count_raw(rc, _MF_PL)
    if mf_bl > 0:
        matches.append({"label": "MF Entrepreneur", "track": "Microfinance", "priority": 10,
                         "detail": f"{mf_bl} MF Business Loan(s)"})
    elif mf_hl > 0:
        matches.append({"label": "MF Asset Builder", "track": "Microfinance", "priority": 11,
                         "detail": f"{mf_hl} MF Housing Loan(s)"})
    elif mf_pl > 0:
        matches.append({"label": "MF Consumer", "track": "Microfinance", "priority": 12,
                         "detail": f"{mf_pl} MF Personal Loan(s)"})

    # --- Business Track (priority=20) ---
    bl_count = _count_raw(rc, _BL_ALL) + _count_raw(rc, _GECL)
    bl_sanction = _sum_sanctioned(rs, _BL_ALL) + _sum_sanctioned(rs, _GECL)
    nf_count = _count_raw(rc, _NON_FUNDED)
    od_count = _count_raw(rc, _OD)
    od_sanction = _sum_sanctioned(rs, _OD)
    bl_agri_count = _count_raw(rc, _BL_AGRI)

    if bl_count >= T.PERSONA_BL_LARGE_MIN_COUNT and bl_count > 0 and (bl_sanction / bl_count) > T.PERSONA_BL_LARGE_AVG_SANCTION:
        detail = f"{bl_count} BL, avg {_fmt_inr_short(bl_sanction / bl_count)}"
        if nf_count > 0:
            detail += " + Non-Funded CF (trade/export)"
        matches.append({"label": "Large Business", "track": "Business", "priority": 20, "detail": detail})
    elif (bl_count > 0 and od_sanction > T.PERSONA_OD_SALARY_MAX) or nf_count > 0:
        total_biz = bl_sanction + od_sanction
        if T.PERSONA_BL_SME_MIN_SANCTION <= total_biz <= T.PERSONA_BL_LARGE_AVG_SANCTION * 2:
            matches.append({"label": "SME / Growing Business", "track": "Business", "priority": 21,
                             "detail": f"{bl_count} BL + OD {_fmt_inr_short(od_sanction)}, total {_fmt_inr_short(total_biz)}"})
    if 1 <= bl_count <= 2 and bl_sanction <= T.PERSONA_BL_LARGE_AVG_SANCTION:
        sub = "micro/shopkeeper" if bl_count > 0 and (bl_sanction / bl_count) < T.PERSONA_BL_MICRO_MAX else None
        detail = f"{bl_count} BL, {_fmt_inr_short(bl_sanction)}"
        if sub:
            detail += f" ({sub})"
        matches.append({"label": "Small Business Owner", "track": "Business", "priority": 22, "detail": detail})

    if bl_agri_count > 0:
        tractor_count = _count_raw(rc, _TRACTOR)
        label = "Agri Entrepreneur" if tractor_count > 0 else "Agri Priority Business"
        matches.append({"label": label, "track": "Business", "priority": 23,
                         "detail": f"{bl_agri_count} Agri BL" + (f" + {tractor_count} Tractor" if tractor_count > 0 else "")})

    # --- Transport Track (priority=30) ---
    cv_count = _count_raw(rc, _CV)
    fleet_count = _count_raw(rc, _FLEET_CARD)
    ce_count = _count_raw(rc, _CE)
    al_count = _count_raw(rc, _AL_ALL)
    al_sanction = _sum_sanctioned(rs, _AL_ALL)

    if cv_count >= T.PERSONA_CV_FLEET_MIN_COUNT or (cv_count >= 2 and fleet_count > 0):
        matches.append({"label": "Fleet Owner", "track": "Transport", "priority": 30,
                         "detail": f"{cv_count} CV" + (f" + Fleet Card" if fleet_count > 0 else "")})
    elif cv_count >= 1:
        matches.append({"label": "Transport Operator", "track": "Transport", "priority": 31,
                         "detail": f"{cv_count} CV (LCV/HCV)"})

    if al_count >= T.PERSONA_AL_CLUSTER_MIN and al_count > 0 and (al_sanction / al_count) <= T.PERSONA_PL_ENTRY_MAX:
        matches.append({"label": "Transport Operator (Cab/Taxi)", "track": "Transport", "priority": 32,
                         "detail": f"{al_count} AL cluster, avg {_fmt_inr_short(al_sanction / al_count)}"})

    if ce_count >= 1:
        label = "Established Contractor" if ce_count >= 2 else "Contractor"
        matches.append({"label": label, "track": "Transport", "priority": 33,
                         "detail": f"{ce_count} CE Loan(s)"})

    # --- Agriculture Track (priority=40) ---
    tractor_count = _count_raw(rc, _TRACTOR)
    if tractor_count > 0 or bl_agri_count > 0:
        if tractor_count > 0 and bl_agri_count > 0:
            label = "Agri Entrepreneur"
            detail = f"{tractor_count} Tractor + {bl_agri_count} Agri BL"
        elif tractor_count > 0:
            label = "Farmer / Agriculture"
            detail = f"{tractor_count} Tractor Loan(s)"
        else:
            label = "Farmer / Agriculture"
            detail = f"{bl_agri_count} Agri BL"
        matches.append({"label": label, "track": "Agriculture", "priority": 40, "detail": detail})

    # --- Salaried Track (priority=50) ---
    hl_count = _count_raw(rc, _HL_ALL)
    hl_sanction = _sum_sanctioned(rs, _HL_ALL)
    cc_count = _count_raw(rc, _CC_ALL)
    pl_count = _count_raw(rc, _PL_PLAIN)
    pl_sanction = _sum_sanctioned(rs, _PL_PLAIN)
    edu_count = _count_raw(rc, _EDUCATION)
    corp_cc = _count_raw(rc, _CORP_CC)

    if hl_count > 0 and hl_sanction > T.PERSONA_HL_MATURE_SANCTION and (cc_count > 0 or al_count > 0):
        detail = f"HL {_fmt_inr_short(hl_sanction)}"
        if hl_sanction > T.PERSONA_HL_METRO_SANCTION:
            detail += " (Metro Senior)"
        matches.append({"label": "Mature Salaried", "track": "Salaried", "priority": 50, "detail": detail})
    elif hl_count > 0 and (cc_count > 0 or pl_count > 0):
        detail = f"HL {_fmt_inr_short(hl_sanction)}"
        if hl_sanction <= T.PERSONA_HL_AFFORDABLE_MAX:
            detail += " (Affordable housing)"
        matches.append({"label": "Established Salaried", "track": "Salaried", "priority": 51, "detail": detail})
    elif pl_count > 0 and pl_sanction <= T.PERSONA_PL_ENTRY_MAX and cc_count > 0:
        detail = f"PL {_fmt_inr_short(pl_sanction)} + CC"
        if edu_count > 0:
            detail += " + Education (Young Professional)"
        matches.append({"label": "Entry Salaried", "track": "Salaried", "priority": 52, "detail": detail})

    if corp_cc > 0:
        las_count = _count_raw(rc, _LAS)
        label = "HNI Executive" if las_count > 0 else "Corporate Professional"
        matches.append({"label": label, "track": "Salaried", "priority": 53,
                         "detail": f"Corporate CC" + (f" + LAS" if las_count > 0 else "")})

    # --- Professional Track (priority=60) ---
    ltp_count = _count_raw(rc, _LOAN_TO_PROF)
    if ltp_count > 0:
        matches.append({"label": "Self-Employed Professional", "track": "Professional", "priority": 60,
                         "detail": f"{ltp_count} Loan to Professional"})

    # --- Asset Track (priority=70) ---
    las_count = _count_raw(rc, _LAS)
    gl_count = _count_raw(rc, _GL_ALL)
    gl_sanction = _sum_sanctioned(rs, _GL_ALL)
    lad_count = _count_raw(rc, _LAD_ALL)

    if las_count > 0:
        detail = f"{las_count} LAS"
        if hl_count > 0 and hl_sanction > T.PERSONA_HL_MATURE_SANCTION:
            detail += " + large HL (Senior Professional)"
        matches.append({"label": "HNI / Investor", "track": "Asset", "priority": 70, "detail": detail})

    # HL alone (no BL, no PL, no CC)
    if hl_count > 0 and bl_count == 0 and pl_count == 0 and cc_count == 0:
        matches.append({"label": "Asset Holder", "track": "Asset", "priority": 71,
                         "detail": f"HL alone {_fmt_inr_short(hl_sanction)}"})

    # Gold alone or LAD alone
    non_gl_lad = total_tl - gl_count - lad_count
    if gl_count > 0 and gl_sanction > T.PERSONA_GOLD_STRESS_MIN and non_gl_lad == 0:
        matches.append({"label": "Asset Stress", "track": "Asset", "priority": 72,
                         "detail": f"Gold Loan alone {_fmt_inr_short(gl_sanction)}"})
    if lad_count > 0 and non_gl_lad == 0:
        matches.append({"label": "Asset Stress", "track": "Asset", "priority": 73,
                         "detail": "LAD alone — pledging deposits"})

    # OD alone checks
    if od_count > 0 and total_tl == od_count:
        if od_sanction <= T.PERSONA_OD_SALARY_MAX:
            matches.append({"label": "Salaried (Salary OD)", "track": "Salaried", "priority": 54,
                             "detail": f"OD alone {_fmt_inr_short(od_sanction)}"})
        else:
            matches.append({"label": "Business / Self-Employed", "track": "Business", "priority": 24,
                             "detail": f"OD alone {_fmt_inr_short(od_sanction)} (>5L)"})

    # --- Stressed Track (priority=80) ---
    spl_count = _count_raw(rc, _SHORT_TERM_PL)
    tod_count = _count_raw(rc, _TEMP_OD)

    if spl_count > 0 and tod_count > 0:
        detail = [f"{spl_count} Short PL", f"{tod_count} Temp OD"]
        combo = " + ".join(detail)
        if gl_count > 0 and gl_sanction > T.PERSONA_GOLD_STRESS_MIN:
            combo += f" + Gold {_fmt_inr_short(gl_sanction)} — possible debt trap"
        matches.append({"label": "Stressed Borrower", "track": "Stressed", "priority": 80,
                         "detail": combo})

    # --- Stress Overlay (independent, always evaluated) ---
    stress_flags = []
    if gl_count > 0 and gl_sanction > T.PERSONA_GOLD_STRESS_MIN:
        if gl_sanction > T.PERSONA_GOLD_HIGH_STRESS:
            stress_flags.append({"label": "High Asset Stress", "severity": "high",
                                  "detail": f"Gold Loan {_fmt_inr_short(gl_sanction)}"})
        elif non_gl_lad < total_tl:  # has other products too
            stress_flags.append({"label": "Asset Stress", "severity": "moderate",
                                  "detail": f"Gold Loan {_fmt_inr_short(gl_sanction)} alongside other products"})
    if spl_count > 0:
        stress_flags.append({"label": "Soft Stress", "severity": "low",
                              "detail": f"{spl_count} Short Term PL"})
    if tod_count > 0:
        stress_flags.append({"label": "Cash Flow Stress", "severity": "moderate",
                              "detail": f"{tod_count} Temporary OD"})

    # --- Select top 2-3 by priority ---
    # Deduplicate by label (keep highest priority)
    seen_labels = set()
    unique_matches = []
    for m in sorted(matches, key=lambda x: x["priority"]):
        if m["label"] not in seen_labels:
            seen_labels.add(m["label"])
            unique_matches.append(m)

    top = unique_matches[:3]

    if not top:
        top = [{"label": "Unclassified", "track": "Unknown", "priority": 99, "detail": f"{total_tl} tradeline(s), no clear profile match"}]

    profiles = [{"label": m["label"], "track": m["track"], "detail": m.get("detail")} for m in top]
    labels = ", ".join(p["label"] for p in profiles)
    summary = f"Probable profile of customer is {labels}"

    return {"profiles": profiles, "stress_flags": stress_flags, "summary": summary}


def render_combined_report_html(
    customer_report: Optional[CustomerReport],
    bureau_report: Optional[BureauReport],
    combined_summary: Optional[str] = None,
    rg_salary_data: Optional[dict] = None,
    theme: str = "emerald",
) -> str:
    """Render combined HTML from both reports using Jinja2 template.

    Args:
        theme: Color scheme to use. Options: "emerald" (default), "original".

    Returns:
        HTML string.
    """
    THEME_TEMPLATES = {
        "emerald":  "combined_report.html",
        "original": "combined_report_original.html",
        "bank":     "bank_report.html",
    }
    template_name = THEME_TEMPLATES.get(theme, THEME_TEMPLATES["emerald"])
    template_dir = Path(__file__).parent.parent.parent / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    env.filters["mask_id"] = mask_customer_id
    env.filters["inr"] = format_inr
    env.filters["inr_units"] = format_inr_units
    env.filters["segment"] = strip_segment_prefix

    # Prepare bureau data for template
    vectors_data = []
    tl_features_data = None
    key_findings_data = []
    if bureau_report:
        for loan_type, vec in bureau_report.feature_vectors.items():
            vec_dict = asdict(vec)
            vec_dict["loan_type_display"] = get_loan_type_display_name(loan_type)
            vec_dict["secured"] = vec.secured
            vectors_data.append(vec_dict)

        if bureau_report.tradeline_features is not None:
            tl_features_data = asdict(bureau_report.tradeline_features)

        key_findings_data = findings_to_dicts(bureau_report.key_findings) if bureau_report.key_findings else []

    chart_data = _compute_html_chart_data(vectors_data, bureau_report.executive_inputs, bureau_report.monthly_exposure) if bureau_report else None

    from tools.scorecard import compute_scorecard
    scorecard = compute_scorecard(customer_report=customer_report, bureau_report=bureau_report, rg_salary_data=rg_salary_data)
    if combined_summary:
        scorecard["narrative"] = combined_summary

    from pipeline.reports.report_summary_chain import summarize_exposure_timeline
    exposure_summary = summarize_exposure_timeline(
        bureau_report.monthly_exposure if bureau_report else None
    )

    checklist = compute_checklist(customer_report, bureau_report, rg_salary_data)
    persona = compute_probable_persona(bureau_report)

    # Feature flags — flip to True to restore hidden sections
    section_flags = {
        "show_scorecard_narrative": False,   # summary text inside Risk Variables
        "show_combined_executive": False,    # Combined Executive Summary at bottom
    }

    template = env.get_template(template_name)
    return template.render(
        customer_report=customer_report,
        bureau_report=bureau_report,
        vectors_data=vectors_data,
        tl_features=tl_features_data,
        key_findings=key_findings_data,
        combined_summary=combined_summary,
        chart_data=chart_data,
        rg_salary_data=rg_salary_data,
        scorecard=scorecard,
        exposure_summary=exposure_summary,
        bureau_checklist=checklist["bureau"],
        banking_checklist=checklist["banking"],
        persona=persona,
        section_flags=section_flags,
    )
