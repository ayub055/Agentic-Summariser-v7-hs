"""Pipeline module — banking report subset."""

from .reports.report_orchestrator import generate_customer_report_pdf

__all__ = [
    "generate_customer_report_pdf",
]
