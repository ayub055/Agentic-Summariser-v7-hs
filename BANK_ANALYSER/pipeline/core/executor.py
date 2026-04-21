"""Tool executor - runs tools and collects structured results."""

from dataclasses import asdict
from typing import List, Dict, Any
from schemas.response import ToolResult
from tools import analytics
from tools.category_resolver import category_presence_lookup
from tools.bureau_chat import (
    bureau_credit_card_info, bureau_loan_type_info,
    bureau_delinquency_check, bureau_overview,
)
from ..reports.report_orchestrator import generate_customer_report_pdf


def _generate_customer_report_with_pdf(customer_id: int, **kwargs) -> Dict[str, Any]:
    """
    Generate customer report with PDF output.

    Wraps the report orchestrator to return data suitable for the pipeline.
    """
    report, pdf_path = generate_customer_report_pdf(customer_id, **kwargs)
    result = report.model_dump()
    result['pdf_path'] = pdf_path
    result['populated_sections'] = report.get_populated_sections()
    return result


def _generate_bureau_report_with_pdf(customer_id: int, **kwargs) -> Dict[str, Any]:
    """
    Generate bureau report with PDF output.

    Wraps the bureau tool to return data suitable for the pipeline.
    """
    from tools.bureau import generate_bureau_report_pdf  # lazy — avoids circular import
    report, pdf_path = generate_bureau_report_pdf(customer_id)
    result = asdict(report.executive_inputs)
    result['feature_vectors'] = {
        lt.value: asdict(vec) for lt, vec in report.feature_vectors.items()
    }
    result['narrative'] = report.narrative
    result['pdf_path'] = pdf_path
    return result


def _generate_combined_report_with_pdf(customer_id: int, **kwargs) -> Dict[str, Any]:
    """
    Generate combined (banking + bureau) report with PDF output.

    Wraps the combined report tool to return data suitable for the pipeline.
    """
    from tools.combined_report import generate_combined_report_pdf as _gen_combined_pdf  # lazy — avoids circular import
    customer_report, bureau_report, pdf_path = _gen_combined_pdf(customer_id)
    result = customer_report.model_dump() if customer_report else {}
    result['pdf_path'] = pdf_path
    result['report_type'] = 'combined'
    result['banking_available'] = customer_report is not None
    result['bureau_available'] = bureau_report is not None
    return result


class ToolExecutor:
    def __init__(self):
        self.tool_map = {
            # Existing tools
            "debit_total": analytics.debit_total,
            "get_total_income": analytics.get_total_income,
            "get_spending_by_category": analytics.get_spending_by_category,
            "top_spending_categories": analytics.top_spending_categories,
            "spending_in_date_range": analytics.spending_in_date_range,
            "list_customers": analytics.list_customers,
            "list_categories": analytics.list_categories,

            # New report-oriented tools
            "get_credit_statistics": analytics.get_credit_statistics,
            "get_debit_statistics": analytics.get_debit_statistics,
            "get_transaction_counts": analytics.get_transaction_counts,
            "get_balance_trend": analytics.get_balance_trend,
            "detect_anomalies": analytics.detect_anomalies,
            "get_income_stability": analytics.get_income_stability,
            "get_cash_flow": analytics.get_cash_flow,
            "generate_customer_report": _generate_customer_report_with_pdf,
            "generate_lender_profile": analytics.generate_lender_profile,

            # Bureau report
            "generate_bureau_report": _generate_bureau_report_with_pdf,

            # Combined report (banking + bureau)
            "generate_combined_report": _generate_combined_report_with_pdf,

            # Bureau chat tools
            "bureau_credit_card_info": bureau_credit_card_info,
            "bureau_loan_type_info": bureau_loan_type_info,
            "bureau_delinquency_check": bureau_delinquency_check,
            "bureau_overview": bureau_overview,

            # Category presence lookup
            "category_presence_lookup": category_presence_lookup,
        }

    def execute(self, plan: List[Dict[str, Any]]) -> List[ToolResult]:
        results = []

        for step in plan:
            tool_name = step["tool"]
            args = step["args"]

            try:
                if tool_name not in self.tool_map:
                    results.append(ToolResult(
                        tool_name=tool_name,
                        args=args,
                        result={},
                        success=False,
                        error=f"Unknown tool: {tool_name}"
                    ))
                    continue

                result = self.tool_map[tool_name](**args)
                results.append(ToolResult(
                    tool_name=tool_name,
                    args=args,
                    result=result,
                    success=True
                ))

            except Exception as e:
                results.append(ToolResult(
                    tool_name=tool_name,
                    args=args,
                    result={},
                    success=False,
                    error=str(e)
                ))

        return results
