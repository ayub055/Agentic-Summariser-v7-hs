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
            _render_feature_pair(pdf, "PL Balance Remaining %", tf.pl_balance_remaining_pct)
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
) -> list:
    """Compute yes/no checklist items from existing report data.

    Returns list of dicts: {label, checked, severity, detail}.
    """
    items = []
    events = (customer_report.events or []) if customer_report else []

    def _events_of_type(etype):
        return [e for e in events if e.get("type") == etype]

    # 1. ECS/NACH bounces
    bounces = _events_of_type("ecs_bounce")
    items.append({
        "label": "ECS / NACH bounces",
        "checked": bool(bounces),
        "severity": "high" if bounces else "neutral",
        "detail": bounces[0].get("description") if bounces else None,
    })

    # 2. Loan disbursement detected
    loan_events = (_events_of_type("loan_disbursal")
                   or _events_of_type("loan_redistribution_suspect")
                   or [e for e in _events_of_type("large_single_credit")
                       if "lender" in str(e.get("description", "")).lower()
                       or "loan" in str(e.get("description", "")).lower()])
    items.append({
        "label": "Loan disbursement detected",
        "checked": bool(loan_events),
        "severity": "high" if loan_events else "neutral",
        "detail": loan_events[0].get("description") if loan_events else None,
    })

    # 2b. Post-disbursement fund usage (spending analysis after loan credit)
    disb_usage = _events_of_type("post_disbursement_usage")
    if disb_usage:
        ev = disb_usage[0]
        match_flag = ev.get("_amounts_match", False)
        conc_pct   = ev.get("_concentration_pct", 0)
        severity = "high" if match_flag else ("high" if conc_pct >= 50 else "medium")
        items.append({
            "label": "Post-disbursement fund diversion",
            "checked": True,
            "severity": severity,
            "detail": ev.get("description"),
        })
    else:
        items.append({
            "label": "Post-disbursement fund diversion",
            "checked": False,
            "severity": "neutral",
            "detail": None,
        })

    # 3. Salary detected
    has_salary = customer_report and customer_report.salary is not None
    sal_detail = None
    if has_salary:
        sal = customer_report.salary
        sal_detail = f"₹{sal.avg_amount:,.0f} avg ({sal.frequency} transactions)"
    items.append({
        "label": "Salary detected in banking",
        "checked": has_salary,
        "severity": "positive" if has_salary else "neutral",
        "detail": sal_detail,
    })

    # 4. EMI obligations
    has_emis = customer_report and customer_report.emis and len(customer_report.emis) > 0
    emi_detail = None
    if has_emis:
        total_emi = sum(e.amount for e in customer_report.emis)
        emi_detail = f"₹{total_emi:,.0f} total across {len(customer_report.emis)} lender(s)"
    items.append({
        "label": "EMI obligations present",
        "checked": bool(has_emis),
        "severity": "medium" if has_emis else "neutral",
        "detail": emi_detail,
    })

    # 5. Rent payments
    has_rent = customer_report and customer_report.rent is not None
    items.append({
        "label": "Rent payments present",
        "checked": bool(has_rent),
        "severity": "neutral",
        "detail": f"₹{customer_report.rent.amount:,.0f} ({customer_report.rent.frequency} transactions)" if has_rent else None,
    })

    # 6. Post-salary self-transfer
    self_transfers = _events_of_type("self_transfer_post_salary")
    items.append({
        "label": "Post-salary self-transfer",
        "checked": bool(self_transfers),
        "severity": "medium" if self_transfers else "neutral",
        "detail": self_transfers[0].get("description") if self_transfers else None,
    })

    # 7. DPD > 0 in bureau
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
    items.append({
        "label": "DPD > 0 in bureau",
        "checked": has_dpd,
        "severity": "high" if has_dpd else "positive",
        "detail": dpd_detail,
    })

    # 8. Adverse events (write-off / settlement)
    adverse_flags = []
    if bureau_report:
        for vec in bureau_report.feature_vectors.values():
            for f in (vec.forced_event_flags or []):
                if f in _ADVERSE_FLAGS:
                    adverse_flags.append(f)
    has_adverse = bool(adverse_flags)
    items.append({
        "label": "Adverse events (write-off / settlement)",
        "checked": has_adverse,
        "severity": "high" if has_adverse else "positive",
        "detail": f"Flags: {', '.join(sorted(set(adverse_flags)))}" if has_adverse else None,
    })

    # 9. Betting / gaming spend
    betting = 0.0
    if customer_report and customer_report.category_overview:
        for key in _BETTING_CATS:
            if key in customer_report.category_overview:
                betting = customer_report.category_overview[key]
                break
    items.append({
        "label": "Betting / gaming transactions",
        "checked": betting > 0,
        "severity": "high" if betting >= 500 else ("medium" if betting > 0 else "neutral"),
        "detail": f"₹{betting:,.0f} total spend" if betting > 0 else None,
    })

    # 10. Account type (conduit / secondary)
    acct_type = "unknown"
    if customer_report and customer_report.account_quality:
        acct_type = customer_report.account_quality.get("account_type", "unknown")
    is_non_primary = acct_type in ("conduit", "secondary")
    items.append({
        "label": "Account is conduit / secondary",
        "checked": is_non_primary,
        "severity": "high" if acct_type == "conduit" else ("medium" if acct_type == "secondary" else "positive"),
        "detail": f"Classified as {acct_type}" if is_non_primary else f"Classified as {acct_type}",
    })

    # 11. High FOIR (>50%)
    foir_val = None
    if bureau_report and bureau_report.tradeline_features:
        foir_val = bureau_report.tradeline_features.foir
    has_high_foir = foir_val is not None and foir_val > 50
    items.append({
        "label": "High FOIR (> 50%)",
        "checked": has_high_foir,
        "severity": "high" if (foir_val and foir_val > 65) else ("medium" if has_high_foir else "neutral"),
        "detail": f"Bureau FOIR: {foir_val:.1f}%" if foir_val is not None else None,
    })

    # 12. NACH mandate / SPLN EMI
    mandate_emis = _events_of_type("mandate_emi")
    items.append({
        "label": "NACH mandate EMI detected",
        "checked": bool(mandate_emis),
        "severity": "medium" if mandate_emis else "neutral",
        "detail": mandate_emis[0].get("description") if mandate_emis else None,
    })

    # 13. Home loan EMI payments
    home_loan_events = _events_of_type("home_loan_emi")
    items.append({
        "label": "Home loan EMI payments",
        "checked": bool(home_loan_events),
        "severity": "neutral",
        "detail": home_loan_events[0].get("description") if home_loan_events else None,
    })

    # 15. Credit card bill payments
    cc_payments = _events_of_type("cc_payment")
    items.append({
        "label": "Credit card bill payments",
        "checked": bool(cc_payments),
        "severity": "positive" if cc_payments else "neutral",
        "detail": cc_payments[0].get("description") if cc_payments else None,
    })

    # 16. Land payments
    land_events = _events_of_type("land_payment")
    items.append({
        "label": "Land purchase payments",
        "checked": bool(land_events),
        "severity": "medium" if land_events else "neutral",
        "detail": land_events[0].get("description") if land_events else None,
    })

    # 17. ATM withdrawals — trend and location
    atm_events = _events_of_type("atm_withdrawal")
    if atm_events:
        ev = atm_events[0]
        is_elevated = ev.get("_is_elevated", False)
        addrs = ev.get("_addresses", [])
        detail = ev.get("description", "")
        if addrs:
            detail += f" | Likely nearby: {', '.join(addrs[:3])}"
        items.append({
            "label": "ATM withdrawals elevated",
            "checked": is_elevated,
            "severity": "medium" if is_elevated else "neutral",
            "detail": detail,
        })
    else:
        items.append({
            "label": "ATM withdrawals elevated",
            "checked": False,
            "severity": "neutral",
            "detail": None,
        })

    # 18 & 19. Transaction-level checks (require raw DataFrame)
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

                # --- 17. Credits / debits above 95th percentile ---------------
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
                items.append({
                    "label": "Transactions above 95th percentile",
                    "checked": has_outliers,
                    "severity": "medium" if has_outliers else "neutral",
                    "detail": "; ".join(outlier_parts[:5]) if has_outliers else None,
                })

                # --- 18. Automated (NACH / mandate) debit & credit count ------
                narr_upper = narrations.str.upper()
                auto_mask = narr_upper.str.contains("NACH|MANDATE", na=False, regex=True)
                auto_debits = int((auto_mask & (directions == "D")).sum())
                auto_credits = int((auto_mask & (directions == "C")).sum())
                auto_total = auto_debits + auto_credits
                items.append({
                    "label": "Automated (NACH/mandate) transactions",
                    "checked": auto_total > 0,
                    "severity": "neutral",
                    "detail": f"{auto_total} total ({auto_debits} debits, {auto_credits} credits)" if auto_total > 0 else None,
                })

                # --- 19. Payment mode distribution shift -----------------
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
                            items.append({
                                "label": "Payment mode distribution shift",
                                "checked": True,
                                "severity": "medium",
                                "detail": "; ".join(_parts),
                            })
                        else:
                            items.append({
                                "label": "Payment mode distribution shift",
                                "checked": False,
                                "severity": "neutral",
                                "detail": None,
                            })
                    else:
                        items.append({
                            "label": "Payment mode distribution shift",
                            "checked": False,
                            "severity": "neutral",
                            "detail": None,
                        })
                else:
                    items.append({
                        "label": "Payment mode distribution shift",
                        "checked": False,
                        "severity": "neutral",
                        "detail": None,
                    })
    except Exception:
        pass  # fail-soft: skip transaction-level checks if data unavailable

    # Emerging merchants (new in recent months, absent before)
    if customer_report and customer_report.merchant_features:
        em = customer_report.merchant_features.get("emerging_merchants", {})
        em_list = em.get("emerging_merchants", [])
        if em_list:
            names = ", ".join(e["name"] for e in em_list[:3])
            detail = f"{len(em_list)} new: {names}"
            items.append({"label": "Emerging merchants detected", "checked": True,
                           "severity": "medium", "detail": detail})

    return items


def render_combined_report_html(
    customer_report: Optional[CustomerReport],
    bureau_report: Optional[BureauReport],
    combined_summary: Optional[str] = None,
    rg_salary_data: Optional[dict] = None,
    theme: str = "emerald",
) -> str:
    """Render combined HTML from both reports using Jinja2 template.

    Args:
        theme: Color scheme to use. Options: "emerald" (default), "original",
               "teal", "blue", "sunset".

    Returns:
        HTML string.
    """
    THEME_TEMPLATES = {
        "emerald":  "combined_report.html",
        "original": "combined_report_original.html",
        "teal":     "combined_report_teal_coral.html",
        "blue":     "combined_report_blue_gold.html",
        "sunset":   "combined_report_sunset.html",
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
        checklist=checklist,
    )
