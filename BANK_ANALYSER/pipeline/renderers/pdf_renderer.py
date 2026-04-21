"""PDF renderer - CustomerReport to PDF/HTML conversion.

This module renders the CustomerReport to:
1. PDF using fpdf2 (pure Python, no system dependencies)
2. HTML using Jinja2 templates (for browser viewing)

NO LLM calls - NO data manipulation - just rendering.
"""

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from fpdf import FPDF

from dataclasses import asdict

from schemas.customer_report import CustomerReport
from features.tradeline_features import TradelineFeatures
from utils.helpers import mask_customer_id, format_inr_units, strip_segment_prefix


def _sanitize_text(text: str) -> str:
    """Sanitize text for PDF rendering by replacing Unicode characters."""
    if not text:
        return text
    # Replace common Unicode characters with ASCII alternatives
    replacements = {
        '₹': 'INR ',
        '€': 'EUR ',
        '£': 'GBP ',
        '¥': 'JPY ',
        '—': '-',
        '–': '-',
        '"': '"',
        '"': '"',
        ''': "'",
        ''': "'",
        '…': '...',
    }
    for unicode_char, ascii_replacement in replacements.items():
        text = text.replace(unicode_char, ascii_replacement)
    # Remove any remaining non-Latin-1 characters
    return text.encode('latin-1', errors='ignore').decode('latin-1')


class ReportPDF(FPDF):
    """Custom PDF class for customer reports."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "Customer Financial Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 8, _sanitize_text(title), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def section_text(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 6, _sanitize_text(text))
        self.ln(2)

    def key_value(self, key: str, value: str):
        self.set_font("Helvetica", "B", 10)
        self.cell(60, 6, _sanitize_text(key) + ":")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, _sanitize_text(str(value)), new_x="LMARGIN", new_y="NEXT")

    def table_header(self, headers: list, widths: list):
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(220, 220, 220)
        for header, width in zip(headers, widths):
            self.cell(width, 7, header, border=1, fill=True, align="C")
        self.ln()

    def table_row(self, values: list, widths: list):
        self.set_font("Helvetica", "", 9)
        for value, width in zip(values, widths):
            # Truncate long values
            display_val = str(value)[:25] if len(str(value)) > 25 else str(value)
            self.cell(width, 6, display_val, border=1, align="C")
        self.ln()


def _build_pdf(report: CustomerReport) -> FPDF:
    """Build PDF document from CustomerReport."""
    pdf = ReportPDF()
    pdf.add_page()

    # Meta information
    pdf.section_title("Report Information")
    pdf.key_value("Customer ID", mask_customer_id(report.meta.customer_id))
    if report.meta.prty_name:
        pdf.key_value("Customer Name", report.meta.prty_name)
    pdf.key_value("Generated", report.meta.generated_at[:10] if report.meta.generated_at else "N/A")
    pdf.key_value("Period", report.meta.analysis_period)
    pdf.key_value("Currency", report.meta.currency)
    pdf.key_value("Transactions", str(report.meta.transaction_count))
    pdf.ln(5)

    # Customer Profile (LLM persona)
    if report.customer_persona:
        pdf.section_title("Customer Profile")
        pdf.section_text(report.customer_persona)
        pdf.ln(3)

    # Executive Summary (LLM review)
    if report.customer_review:
        pdf.section_title("Executive Summary")
        pdf.section_text(report.customer_review)
        pdf.ln(3)

    # Salary Information
    if report.salary:
        pdf.section_title("Salary Information")
        pdf.key_value("Average Amount", f"{report.salary.avg_amount:,.2f} {report.meta.currency}")
        pdf.key_value("Frequency", f"{report.salary.frequency} transactions")
        if report.salary.narration:
            pdf.key_value("Description", report.salary.narration[:50])
        if report.salary.latest_transaction:
            latest = report.salary.latest_transaction
            pdf.key_value("Latest Transaction", f"{latest.get('amount', 0):,.2f} {report.meta.currency}")
            pdf.key_value("Latest Date", latest.get('date', 'N/A')[:10])
        pdf.ln(3)

    # Category Overview
    if report.category_overview:
        pdf.section_title("Spending by Category")
        sorted_cats = sorted(report.category_overview.items(), key=lambda x: x[1], reverse=True)
        widths = [80, 50, 60]
        pdf.table_header(["Category", "Amount", "% of Total"], widths)
        total = sum(report.category_overview.values())
        for cat, amount in sorted_cats:
            pct = (amount / total * 100) if total > 0 else 0
            pdf.table_row([cat, f"{amount:,.0f}", f"{pct:.1f}%"], widths)
        pdf.ln(5)

    # Monthly Cash Flow
    if report.monthly_cashflow:
        pdf.section_title("Monthly Cash Flow")
        widths = [40, 45, 45, 45]
        pdf.table_header(["Month", "Inflow", "Outflow", "Net"], widths)
        for m in report.monthly_cashflow:
            pdf.table_row([
                m.get("month", "N/A"),
                f"{m.get('inflow', 0):,.0f}",
                f"{m.get('outflow', 0):,.0f}",
                f"{m.get('net', 0):,.0f}"
            ], widths)

        # Summary row
        total_in = sum(m.get('inflow', 0) for m in report.monthly_cashflow)
        total_out = sum(m.get('outflow', 0) for m in report.monthly_cashflow)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 6, "TOTAL", border=1, align="C")
        pdf.cell(45, 6, f"{total_in:,.0f}", border=1, align="C")
        pdf.cell(45, 6, f"{total_out:,.0f}", border=1, align="C")
        pdf.cell(45, 6, f"{total_in - total_out:,.0f}", border=1, align="C")
        pdf.ln(8)

    # EMI Payments
    if report.emis:
        pdf.section_title("EMI Payments")
        widths = [80, 50, 60]
        pdf.table_header(["Name", "Amount", "Frequency"], widths)
        for emi in report.emis:
            pdf.table_row([emi.name, f"{emi.amount:,.2f}", f"{emi.frequency}x"], widths)
        pdf.ln(3)

    # Rent
    if report.rent:
        pdf.section_title("Rent")
        pdf.key_value("Direction", report.rent.direction.capitalize())
        pdf.key_value("Amount", f"{report.rent.amount:,.2f} {report.meta.currency}")
        pdf.key_value("Frequency", f"{report.rent.frequency} transactions")
        pdf.ln(3)

    # Utility Bills
    if report.bills:
        pdf.section_title("Utility Bills")
        widths = [80, 50, 60]
        pdf.table_header(["Type", "Avg Amount", "Frequency"], widths)
        for bill in report.bills:
            pdf.table_row([bill.bill_type, f"{bill.avg_amount:,.2f}", f"{bill.frequency}x"], widths)
        pdf.ln(3)

    # Top Merchants
    if report.top_merchants:
        pdf.section_title("Top Merchants")
        widths = [70, 30, 45, 45]
        pdf.table_header(["Merchant", "Count", "Total", "Avg"], widths)
        for m in report.top_merchants:
            pdf.table_row([
                str(m.get("name", "N/A"))[:25],
                str(m.get("count", 0)),
                f"{m.get('total', 0):,.0f}",
                f"{m.get('avg', 0):,.0f}"
            ], widths)

    return pdf


def render_report_pdf(
    report: CustomerReport,
    output_path: str,
    tl_features: Optional[TradelineFeatures] = None,
    rg_salary_data: Optional[dict] = None,
) -> str:
    """
    Render a CustomerReport to PDF.

    Args:
        report: Fully populated CustomerReport
        output_path: Desired output file path (.pdf)
        tl_features: Optional pre-computed tradeline features for customer profile block
        rg_salary_data: Optional internal salary algorithm data dict

    Returns:
        Path where PDF was saved
    """
    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Build and save PDF
    pdf = _build_pdf(report)
    pdf.output(str(output_file))

    # Also save HTML version for browser viewing
    html_path = str(output_file).replace('.pdf', '.html')
    html_content = render_report_html(report, tl_features=tl_features, rg_salary_data=rg_salary_data)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return str(output_file)


def render_report_html(
    report: CustomerReport,
    tl_features: Optional[TradelineFeatures] = None,
    rg_salary_data: Optional[dict] = None,
) -> str:
    """
    Render a CustomerReport to HTML string.

    Args:
        report: CustomerReport to render
        tl_features: Optional pre-computed tradeline features for customer profile block
        rg_salary_data: Optional internal salary algorithm data dict

    Returns:
        HTML string
    """
    template_dir = Path(__file__).parent.parent.parent / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True
    )
    env.filters['mask_id'] = mask_customer_id
    env.filters['inr_units'] = format_inr_units
    env.filters['segment'] = strip_segment_prefix

    tl_features_data = asdict(tl_features) if tl_features is not None else None

    from tools.scorecard import compute_scorecard
    scorecard = compute_scorecard(customer_report=report, rg_salary_data=rg_salary_data)

    template = env.get_template("customer_report.html")
    return template.render(
        report=report,
        tl_features=tl_features_data,
        rg_salary_data=rg_salary_data,
        scorecard=scorecard,
    )


def is_pdf_available() -> bool:
    """Check if PDF generation is available."""
    return True  # fpdf2 is always available (pure Python)
