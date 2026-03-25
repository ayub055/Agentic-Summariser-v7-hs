"""Report orchestrator - high-level control flow for report generation.

This module coordinates the planner-driven report generation pipeline:
1. Build data profile (quick availability check)
2. Call planner to decide which sections to include
3. Execute sections based on plan
4. Aggregate into CustomerReport
5. Generate LLM summary (optional, fail-soft)
6. Render PDF

Includes caching by (customer_id, analysis_period).
"""

from datetime import datetime
from typing import Dict, Tuple, Optional, List
import logging

from schemas.customer_report import CustomerReport, ReportMeta, ReportSectionMeta

logger = logging.getLogger(__name__)


class CustomerNotFoundError(Exception):
    """Raised when a customer ID is not found in the dataset."""
    pass


class ReportGenerationError(Exception):
    """Raised when report generation fails."""
    pass
from .customer_report_builder import (
    build_customer_report,
    build_data_profile,
    execute_section
)
from .report_planner import ReportPlanner, ReportPlan, PlannedSection
from .report_summary_chain import generate_customer_review, generate_customer_persona
from tools.account_quality import compute_account_quality
from tools.event_detector import detect_events
from ..renderers.pdf_renderer import render_report_pdf
from ..extractors.tradeline_feature_extractor import extract_tradeline_features
from data.loader import get_transactions_df, load_rg_salary_data


# Cache for report data - keyed by (customer_id, period)
_REPORT_CACHE: Dict[Tuple[int, str], CustomerReport] = {}


def generate_customer_report_pdf(
    customer_id: int,
    months: int = 6,
    include_summary: bool = True,
    output_path: Optional[str] = None,
    use_cache: bool = True,
    use_planner: bool = True
) -> Tuple[CustomerReport, str]:
    """
    Orchestrate planner-driven customer report generation.

    This is the main entry point for report generation. It:
    1. Validates customer exists
    2. Builds a data profile (quick availability check)
    3. Calls the planner to decide which sections to include
    4. Executes sections based on the plan
    5. Aggregates results into CustomerReport
    6. Optionally generates LLM summaries
    7. Renders to PDF

    Args:
        customer_id: Customer identifier
        months: Analysis period in months (default 6)
        include_summary: Whether to generate LLM summary (default True)
        output_path: Output file path (default: reports/customer_{id}_report.pdf)
        use_cache: Whether to use cached report data (default True)
        use_planner: Whether to use LLM planner (default True, falls back to build_customer_report if False)

    Returns:
        Tuple of (CustomerReport, pdf_path)

    Raises:
        CustomerNotFoundError: If customer_id is not in the dataset
        ReportGenerationError: If report generation fails critically
    """
    # Validate months parameter
    if months < 1:
        logger.warning(f"Invalid months value {months}, defaulting to 6")
        months = 6

    cache_key = (customer_id, f"{months}m")

    # Check cache first
    if use_cache and cache_key in _REPORT_CACHE:
        report = _REPORT_CACHE[cache_key]
        logger.debug(f"Using cached report for customer {customer_id}")
    else:
        if use_planner:
            # Planner-driven flow (includes customer validation)
            report = _build_report_with_planner(customer_id, months)
        else:
            # Fallback to original flow - validate customer first
            if not _validate_customer_exists(customer_id):
                raise CustomerNotFoundError(f"Customer {customer_id} not found in dataset")
            report = build_customer_report(customer_id, months)

        _REPORT_CACHE[cache_key] = report

    # Load internal salary algorithm data (fail-soft) — must precede LLM review
    # so the authoritative salary amount matches what the scorecard shows.
    rg_salary_data = None
    try:
        rg_salary_data = load_rg_salary_data(customer_id) or None
    except Exception as e:
        logger.warning(f"RG salary data unavailable for [{customer_id}]: {e}")

    # Generate LLM summaries (optional, fail-soft)
    # Skip if insufficient transaction data (< 10 transactions)
    if include_summary and report.meta.transaction_count >= 10:
        try:
            if report.customer_review is None:
                report.customer_review = generate_customer_review(report, rg_salary_data=rg_salary_data)
        except Exception as e:
            logger.warning(f"Failed to generate customer review: {e}")

    # Load tradeline features for customer profile block (fail-soft)
    tl_features = None
    try:
        tl_features = extract_tradeline_features(customer_id)
    except Exception as e:
        logger.warning(f"Tradeline features unavailable for customer profile [{customer_id}]: {e}")

    # Render PDF
    if output_path is None:
        output_path = f"reports/customer_{customer_id}_report.pdf"

    try:
        pdf_path = render_report_pdf(report, output_path, tl_features=tl_features, rg_salary_data=rg_salary_data)
    except Exception as e:
        logger.error(f"Failed to render PDF: {e}")
        raise ReportGenerationError(f"PDF rendering failed: {e}")

    return report, pdf_path


def _validate_customer_exists(customer_id: int) -> bool:
    """Check if customer exists in the dataset."""
    df = get_transactions_df()
    return customer_id in df['cust_id'].values


def _build_report_with_planner(customer_id: int, months: int = 6) -> CustomerReport:
    """
    Build a customer report using the planner-driven approach.

    Flow:
    1. Validate customer exists
    2. Build quick data profile
    3. Call planner to decide sections
    4. Execute each planned section
    5. Aggregate results into CustomerReport

    Args:
        customer_id: Customer identifier
        months: Analysis period in months

    Returns:
        CustomerReport with sections populated based on plan

    Raises:
        CustomerNotFoundError: If customer_id is not in the dataset
        ReportGenerationError: If report generation fails critically
    """
    # Step 0: Validate customer exists
    if not _validate_customer_exists(customer_id):
        raise CustomerNotFoundError(f"Customer {customer_id} not found in dataset")

    # Step 1: Build data profile for planner
    try:
        data_profile = build_data_profile(customer_id)
    except Exception as e:
        logger.error(f"Failed to build data profile for customer {customer_id}: {e}")
        raise ReportGenerationError(f"Failed to build data profile: {e}")

    # Step 2: Get plan from planner (has internal fallback)
    try:
        planner = ReportPlanner()
        plan = planner.plan(customer_id, data_profile)
    except Exception as e:
        logger.error(f"Planner initialization failed: {e}")
        raise ReportGenerationError(f"Planner failed: {e}")

    # Step 3: Execute sections based on plan
    section_results = {}
    section_errors = []
    for section in plan.sections:
        result, error = execute_section(customer_id, section.section_name)
        if error:
            section_errors.append(f"{section.section_name}: {error}")
            logger.warning(f"Section '{section.section_name}' failed: {error}")
        if result is not None:
            section_results[section.section_name] = result

    if section_errors:
        logger.info(f"Report generated with {len(section_errors)} section errors: {section_errors}")

    # Step 4: Aggregate into CustomerReport
    return _aggregate_to_report(customer_id, months, section_results, plan)


def _aggregate_to_report(
    customer_id: int,
    months: int,
    section_results: Dict[str, dict],
    plan: ReportPlan
) -> CustomerReport:
    """
    Aggregate section results into a CustomerReport object.

    Maps the outputs from execute_section() to the CustomerReport schema fields.

    Args:
        customer_id: Customer identifier
        months: Analysis period in months
        section_results: Dict mapping section names to their data
        plan: The ReportPlan used for section selection

    Returns:
        CustomerReport with all available sections populated
    """
    # Build report metadata
    df = get_transactions_df()
    cust_df = df[df['cust_id'] == customer_id]
    transaction_count = len(cust_df)

    prty_name = None
    if 'prty_name' in cust_df.columns and len(cust_df) > 0:
        prty_name = cust_df['prty_name'].iloc[0]
        if prty_name and str(prty_name).lower() not in ['nan', 'none', '']:
            prty_name = str(prty_name)
        else:
            prty_name = None

    meta = ReportMeta(
        customer_id=customer_id,
        prty_name=prty_name,
        generated_at=datetime.now().isoformat(),
        analysis_period=f"Last {months} months",
        currency="INR",
        transaction_count=transaction_count
    )

    # Extract data from section results
    # income_summary section -> salary field
    salary = None
    if "income_summary" in section_results:
        salary = section_results["income_summary"].get("salary")

    # spending_summary section -> category_overview, top_merchants fields
    category_overview = None
    top_merchants = None
    if "spending_summary" in section_results:
        category_overview = section_results["spending_summary"].get("category_overview")
        top_merchants = section_results["spending_summary"].get("top_merchants")

    # cashflow_analysis section -> monthly_cashflow field
    monthly_cashflow = None
    if "cashflow_analysis" in section_results:
        monthly_cashflow = section_results["cashflow_analysis"].get("monthly_cashflow")

    # emi_obligations section -> emis field
    emis = None
    if "emi_obligations" in section_results:
        emis = section_results["emi_obligations"].get("emis")

    # rent_payments section -> rent field
    rent = None
    if "rent_payments" in section_results:
        rent = section_results["rent_payments"].get("rent")

    # utility_bills section -> bills field
    bills = None
    if "utility_bills" in section_results:
        bills = section_results["utility_bills"].get("bills")

    # savings_analysis section -> savings field
    savings = None
    if "savings_analysis" in section_results:
        savings = section_results["savings_analysis"].get("savings")

    # risk_indicators section -> risk_indicators field
    risk_indicators = None
    if "risk_indicators" in section_results:
        risk_indicators = section_results["risk_indicators"].get("risk_indicators")

    # Build sections metadata from plan
    sections_meta = [
        ReportSectionMeta(
            section_name=s.section_name,
            emphasis=s.emphasis,
            included=s.section_name in section_results
        )
        for s in plan.sections
    ]

    # Merchant behavioral features (same as build_customer_report path)
    merchant_features = None
    try:
        from features.merchant_features import compute_all_merchant_features
        merchant_features = compute_all_merchant_features(customer_id) or None
    except Exception:
        pass

    base_report = CustomerReport(
        meta=meta,
        category_overview=category_overview,
        monthly_cashflow=monthly_cashflow,
        top_merchants=top_merchants,
        salary=salary,
        emis=emis,
        rent=rent,
        bills=bills,
        savings=savings,
        risk_indicators=risk_indicators,
        sections_meta=sections_meta,
        merchant_features=merchant_features,
    )

    # Attach account quality + events (same as build_customer_report path)
    updates = {}
    try:
        aq = compute_account_quality(customer_id, customer_report=base_report)
        if aq:
            updates["account_quality"] = aq
    except Exception as exc:
        logger.warning("account_quality failed in _aggregate_to_report for %s: %s", customer_id, exc)

    try:
        evts = detect_events(customer_id) or None
        if evts:
            updates["events"] = evts
    except Exception as exc:
        logger.warning("detect_events failed in _aggregate_to_report for %s: %s", customer_id, exc)

    return base_report.model_copy(update=updates) if updates else base_report


def get_customer_report_data(
    customer_id: int,
    months: int = 6,
    include_summary: bool = True,
    use_cache: bool = True,
    use_planner: bool = True
) -> CustomerReport:
    """
    Get customer report data without rendering PDF.

    Useful for API responses or when you need the data
    without generating a file.

    Args:
        customer_id: Customer identifier
        months: Analysis period in months
        include_summary: Whether to generate LLM summary
        use_cache: Whether to use cached data
        use_planner: Whether to use LLM planner

    Returns:
        CustomerReport with populated sections

    Raises:
        CustomerNotFoundError: If customer_id is not in the dataset
        ReportGenerationError: If report generation fails critically
    """
    # Validate months parameter
    if months < 1:
        logger.warning(f"Invalid months value {months}, defaulting to 6")
        months = 6

    cache_key = (customer_id, f"{months}m")

    # Build or retrieve from cache
    if use_cache and cache_key in _REPORT_CACHE:
        report = _REPORT_CACHE[cache_key]
    else:
        if use_planner:
            report = _build_report_with_planner(customer_id, months)
        else:
            # Validate customer first
            if not _validate_customer_exists(customer_id):
                raise CustomerNotFoundError(f"Customer {customer_id} not found in dataset")
            report = build_customer_report(customer_id, months)
        _REPORT_CACHE[cache_key] = report

    # Load RG salary data before LLM review for income consistency
    rg_salary_data = None
    try:
        rg_salary_data = load_rg_salary_data(customer_id) or None
    except Exception as e:
        logger.warning(f"RG salary data unavailable for [{customer_id}]: {e}")

    # Generate summaries if requested (fail-soft)
    if include_summary:
        try:
            if report.customer_review is None:
                report.customer_review = generate_customer_review(report, rg_salary_data=rg_salary_data)
        except Exception as e:
            logger.warning(f"Failed to generate customer review: {e}")

    return report


def clear_report_cache():
    """Clear the report cache."""
    global _REPORT_CACHE
    _REPORT_CACHE = {}


def invalidate_customer_cache(customer_id: int):
    """
    Invalidate cache entries for a specific customer.

    Args:
        customer_id: Customer whose cache entries to clear
    """
    global _REPORT_CACHE
    keys_to_remove = [k for k in _REPORT_CACHE if k[0] == customer_id]
    for key in keys_to_remove:
        del _REPORT_CACHE[key]
