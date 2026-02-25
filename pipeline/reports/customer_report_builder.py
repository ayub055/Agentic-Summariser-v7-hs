"""Customer report builder - data collection without LLM.

This module collects factual data from existing tools and populates
the CustomerReport schema. NO LLM calls are made here - this is
purely deterministic data aggregation.
"""

from datetime import datetime
from typing import Optional, Tuple
import logging

from data.loader import get_transactions_df
from config.section_tools import AVAILABLE_SECTIONS

logger = logging.getLogger(__name__)
from tools.analytics import (
    get_spending_by_category,
    get_cash_flow,
    get_total_income,
    debit_total,
    detect_anomalies,
    get_income_stability,
    get_balance_trend
)
from tools.transaction_fetcher import fetch_transaction_summary
from tools.category_resolver import resolve_category_presence
from schemas.customer_report import (
    CustomerReport,
    ReportMeta,
    SalaryBlock,
    EMIBlock,
    BillBlock,
    RentBlock,
    SavingsBlock,
    RiskIndicatorsBlock
)


def build_customer_report(customer_id: int, months: int = 6) -> CustomerReport:
    """
    Build a customer report by collecting data from existing tools.

    This function orchestrates calls to existing analytics and detection
    tools, adapting their outputs to the CustomerReport schema.

    Args:
        customer_id: Customer identifier
        months: Analysis period in months (default 6)

    Returns:
        CustomerReport with all available sections populated
    """
    # 1. Get transaction count for meta
    df = get_transactions_df()
    cust_df = df[df['cust_id'] == customer_id]
    transaction_count = len(cust_df)

    # 2. Get party name if available
    prty_name = None
    if 'prty_name' in cust_df.columns and len(cust_df) > 0:
        prty_name = cust_df['prty_name'].iloc[0]
        if prty_name and str(prty_name).lower() not in ['nan', 'none', '']:
            prty_name = str(prty_name)
        else:
            prty_name = None

    # 3. Build report meta
    meta = ReportMeta(
        customer_id=customer_id,
        prty_name=prty_name,
        generated_at=datetime.now().isoformat(),
        analysis_period=f"Last {months} months",
        currency="INR",
        transaction_count=transaction_count
    )

    # 3. Get category overview (reuse get_spending_by_category)
    category_overview = _get_category_overview(customer_id)

    # 4. Get monthly cashflow (reuse get_cash_flow)
    monthly_cashflow = _get_monthly_cashflow(customer_id)

    # 5. Get top merchants (from transaction summary high-freq groups)
    top_merchants = _get_top_merchants(customer_id)

    # 6. Get salary block (from transaction summary)
    salary_block = _get_salary_block(customer_id)

    # 7. Get EMI block (via category presence)
    emis = _get_emi_block(customer_id)

    # 8. Get rent block (via category presence)
    rent_block = _get_rent_block(customer_id)

    # 9. Get bills block (via category presence for utilities)
    bills = _get_bills_block(customer_id)

    return CustomerReport(
        meta=meta,
        category_overview=category_overview,
        monthly_cashflow=monthly_cashflow,
        top_merchants=top_merchants,
        salary=salary_block,
        emis=emis,
        rent=rent_block,
        bills=bills
    )


def _get_category_overview(customer_id: int) -> Optional[dict]:
    """Get category spending breakdown."""
    try:
        category_data = get_spending_by_category(customer_id)
        overview = category_data.get('all_categories_spending')
        return overview if overview else None
    except Exception:
        return None


def _get_monthly_cashflow(customer_id: int) -> Optional[list]:
    """Get monthly cashflow data."""
    try:
        cashflow_data = get_cash_flow(customer_id)
        monthly_data = cashflow_data.get('monthly_cash_flow', {})

        if not monthly_data:
            return None

        # Convert to list format for template
        cashflow_list = [
            {"month": k, "inflow": v.get('inflow', 0), "outflow": v.get('outflow', 0), "net": v.get('net', 0)}
            for k, v in sorted(monthly_data.items())
        ]
        return cashflow_list if cashflow_list else None
    except Exception:
        return None


def _get_top_merchants(customer_id: int) -> Optional[list]:
    """Get top merchants from high-frequency transaction groups."""
    try:
        summary = fetch_transaction_summary(customer_id)

        if not summary.high_frequency_transactions:
            return None

        top_merchants = [
            {
                "name": t.representative_narration,
                "count": t.count,
                "total": t.total_amount,
                "avg": t.average_amount,
                "type": t.transaction_type
            }
            for t in summary.high_frequency_transactions[:5]
        ]
        return top_merchants if top_merchants else None
    except Exception:
        return None


def _get_salary_block(customer_id: int) -> Optional[SalaryBlock]:
    """Get salary information from transaction summary."""
    try:
        summary = fetch_transaction_summary(customer_id)

        if not summary.salary_summary:
            return None

        salary = summary.salary_summary

        # Get latest salary transaction from raw data
        latest_transaction = _get_latest_salary_transaction(customer_id)

        return SalaryBlock(
            avg_amount=salary.average_amount,
            frequency=salary.transaction_count,
            narration=salary.narrations[0] if salary.narrations else "",
            sample_transaction={
                "amount": salary.average_amount,
                "total": salary.total_amount
            },
            latest_transaction=latest_transaction
        )
    except Exception:
        return None


def _get_latest_salary_transaction(customer_id: int) -> Optional[dict]:
    """Get the most recent salary transaction for a customer."""
    try:
        from utils.narration_utils import is_salary_narration

        df = get_transactions_df()
        cust_df = df[df['cust_id'] == customer_id].copy()

        if len(cust_df) == 0:
            return None

        # Filter for credit transactions that are salary
        salary_txns = []
        for _, row in cust_df.iterrows():
            if row.get('dr_cr_indctor') != 'C':
                continue

            category = str(row.get('category_of_txn', '')).upper()
            narration = str(row.get('tran_partclr', ''))

            if category == 'SALARY' or is_salary_narration(narration):
                salary_txns.append({
                    'date': str(row.get('tran_date', '')),
                    'amount': float(row.get('tran_amt_in_ac', 0)),
                    'narration': narration[:80] if narration else ''
                })

        if not salary_txns:
            return None

        # Sort by date descending and return the latest
        salary_txns.sort(key=lambda x: x['date'], reverse=True)
        return salary_txns[0]

    except Exception:
        return None


def _get_emi_block(customer_id: int) -> Optional[list]:
    """Detect EMI payments using category presence lookup."""
    try:
        emi_result = resolve_category_presence(customer_id, "emi")

        if not emi_result.get('present'):
            return None

        txn_count = emi_result.get('transaction_count', 1)
        total_amount = emi_result.get('total_amount', 0)
        avg_amount = total_amount / max(1, txn_count)

        # Get sample transaction
        supporting = emi_result.get('supporting_transactions', [])
        sample = supporting[0] if supporting else {}

        return [EMIBlock(
            name="EMI Payment",
            amount=avg_amount,
            frequency=txn_count,
            sample_transaction=sample
        )]
    except Exception:
        return None


def _get_rent_block(customer_id: int) -> Optional[RentBlock]:
    """Detect rent payments using category presence lookup."""
    try:
        rent_result = resolve_category_presence(customer_id, "rent")

        if not rent_result.get('present'):
            return None

        txn_count = rent_result.get('transaction_count', 1)
        total_amount = rent_result.get('total_amount', 0)
        avg_amount = total_amount / max(1, txn_count)

        # Get sample transaction
        supporting = rent_result.get('supporting_transactions', [])
        sample = supporting[0] if supporting else {}

        return RentBlock(
            direction="paid",
            frequency=txn_count,
            amount=avg_amount,
            sample_transaction=sample
        )
    except Exception:
        return None


def _get_bills_block(customer_id: int) -> Optional[list]:
    """Detect utility bill payments using category presence lookup."""
    try:
        bills_result = resolve_category_presence(customer_id, "utilities")

        if not bills_result.get('present'):
            return None

        txn_count = bills_result.get('transaction_count', 1)
        total_amount = bills_result.get('total_amount', 0)
        avg_amount = total_amount / max(1, txn_count)

        # Get sample transaction
        supporting = bills_result.get('supporting_transactions', [])
        sample = supporting[0] if supporting else {}

        return [BillBlock(
            bill_type="Utilities",
            frequency=txn_count,
            avg_amount=avg_amount,
            sample_transaction=sample
        )]
    except Exception:
        return None


def _get_savings_block(customer_id: int) -> Optional[SavingsBlock]:
    """
    Calculate savings analysis from income vs spending.

    Uses get_total_income and debit_total to compute savings metrics.
    """
    try:
        income_data = get_total_income(customer_id)
        spending_data = debit_total(customer_id)
        cashflow_data = get_cash_flow(customer_id)

        total_income = income_data.get('total_income', 0)
        total_spending = spending_data.get('total_spending', 0)
        net_savings = total_income - total_spending

        # Calculate savings rate (0-1)
        savings_rate = net_savings / total_income if total_income > 0 else 0

        # Get monthly data for average calculation
        monthly_cashflow = cashflow_data.get('monthly_cash_flow', {})
        months_analyzed = len(monthly_cashflow)

        # Calculate average monthly savings
        if months_analyzed > 0:
            monthly_nets = [m.get('net', 0) for m in monthly_cashflow.values()]
            avg_monthly_savings = sum(monthly_nets) / months_analyzed
        else:
            avg_monthly_savings = 0

        return SavingsBlock(
            total_income=total_income,
            total_spending=total_spending,
            net_savings=net_savings,
            savings_rate=round(savings_rate, 4),
            avg_monthly_savings=round(avg_monthly_savings, 2),
            months_analyzed=months_analyzed
        )
    except Exception:
        return None


def _get_risk_indicators_block(customer_id: int) -> Optional[RiskIndicatorsBlock]:
    """
    Assess risk indicators from income stability, anomalies, and balance trends.

    Uses detect_anomalies, get_income_stability, and get_balance_trend.
    """
    try:
        stability_data = get_income_stability(customer_id)
        anomaly_data = detect_anomalies(customer_id)
        balance_data = get_balance_trend(customer_id)

        income_stability_score = stability_data.get('stability_score', 0)
        balance_trend = balance_data.get('trend', 'unknown')
        credit_spike_count = anomaly_data.get('credit_spike_count', 0)
        debit_spike_count = anomaly_data.get('debit_spike_count', 0)

        # Identify risk flags
        risk_flags = []

        # Income stability risk
        if income_stability_score < 50:
            risk_flags.append("unstable_income")

        # Balance trend risk
        if balance_trend == 'decreasing':
            risk_flags.append("declining_balance")

        # Anomaly-based risks
        if credit_spike_count > 3:
            risk_flags.append("irregular_income_patterns")
        if debit_spike_count > 5:
            risk_flags.append("irregular_spending_patterns")

        # Negative balance risk
        min_balance = balance_data.get('min_balance', 0)
        if min_balance < 0:
            risk_flags.append("negative_balance_history")

        # Determine risk level
        if len(risk_flags) == 0:
            risk_level = "low"
        elif len(risk_flags) <= 2:
            risk_level = "medium"
        else:
            risk_level = "high"

        return RiskIndicatorsBlock(
            income_stability_score=income_stability_score,
            balance_trend=balance_trend,
            credit_spike_count=credit_spike_count,
            debit_spike_count=debit_spike_count,
            risk_flags=risk_flags,
            risk_level=risk_level
        )
    except Exception:
        return None


def execute_section(customer_id: int, section_name: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Execute a single report section by name.

    This function allows sections to be executed independently based on
    the planner's decisions. Each section maps to one or more data-gathering
    functions.

    Args:
        customer_id: Customer identifier
        section_name: Section name from AVAILABLE_SECTIONS

    Returns:
        Tuple of (section_data, error_message). If successful, error_message is None.
        If section has no data, returns (result_dict, None) where values may be None.
        If execution fails, returns (None, error_description).
    """
    # Validate section name
    if section_name not in AVAILABLE_SECTIONS:
        logger.warning(f"Invalid section name: {section_name}")
        return None, f"Invalid section name: {section_name}"

    section_executors = {
        "income_summary": lambda cid: {"salary": _get_salary_block(cid)},
        "spending_summary": lambda cid: {
            "category_overview": _get_category_overview(cid),
            "top_merchants": _get_top_merchants(cid)
        },
        "cashflow_analysis": lambda cid: {"monthly_cashflow": _get_monthly_cashflow(cid)},
        "emi_obligations": lambda cid: {"emis": _get_emi_block(cid)},
        "rent_payments": lambda cid: {"rent": _get_rent_block(cid)},
        "utility_bills": lambda cid: {"bills": _get_bills_block(cid)},
        "savings_analysis": lambda cid: {"savings": _get_savings_block(cid)},
        "risk_indicators": lambda cid: {"risk_indicators": _get_risk_indicators_block(cid)},
        # LLM-generated section - no deterministic tool
        "recommendations": lambda cid: None,
    }

    executor = section_executors.get(section_name)
    if executor is None:
        return None, f"No executor for section: {section_name}"

    try:
        result = executor(customer_id)
        return result, None
    except Exception as e:
        logger.error(f"Section '{section_name}' execution failed for customer {customer_id}: {e}")
        return None, str(e)


def build_data_profile(customer_id: int) -> dict:
    """
    Build a quick data availability profile for the planner.

    This is a lightweight check that determines what data exists for a customer
    without fully extracting it. Used by the planner to decide which sections
    to include.

    Args:
        customer_id: Customer identifier

    Returns:
        Dict with data availability flags
    """
    df = get_transactions_df()
    cust_df = df[df['cust_id'] == customer_id]

    transaction_count = len(cust_df)
    if transaction_count == 0:
        return {
            "transaction_count": 0,
            "has_salary": False,
            "has_emi": False,
            "has_rent": False,
            "has_utilities": False,
            "month_count": 0
        }

    # Check for salary
    has_salary = False
    try:
        salary = _get_salary_block(customer_id)
        has_salary = salary is not None
    except Exception:
        pass

    # Check for EMI
    has_emi = False
    try:
        emi_result = resolve_category_presence(customer_id, "emi")
        has_emi = emi_result.get('present', False)
    except Exception:
        pass

    # Check for rent
    has_rent = False
    try:
        rent_result = resolve_category_presence(customer_id, "rent")
        has_rent = rent_result.get('present', False)
    except Exception:
        pass

    # Check for utilities
    has_utilities = False
    try:
        util_result = resolve_category_presence(customer_id, "utilities")
        has_utilities = util_result.get('present', False)
    except Exception:
        pass

    # Count distinct months
    month_count = 0
    if 'tran_date' in cust_df.columns:
        try:
            dates = cust_df['tran_date'].dropna()
            if len(dates) > 0:
                months = set()
                for d in dates:
                    month_str = str(d)[:7]  # YYYY-MM format
                    months.add(month_str)
                month_count = len(months)
        except Exception:
            pass

    return {
        "transaction_count": transaction_count,
        "has_salary": has_salary,
        "has_emi": has_emi,
        "has_rent": has_rent,
        "has_utilities": has_utilities,
        "month_count": month_count
    }
