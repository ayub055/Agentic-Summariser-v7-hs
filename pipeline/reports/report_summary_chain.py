"""Report summary chain - LLM-based customer review and persona generation.

This module generates:
1. Executive summary (3-4 lines) - financial metrics focus
2. Customer persona (4-5 lines) - lifestyle/behavior focus

Uses LangChain Expression Language (LCEL) with Ollama models.
"""

import logging
from dataclasses import asdict
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama

from schemas.customer_report import CustomerReport
from data.loader import get_transactions_df
from utils.helpers import mask_customer_id, format_inr
from schemas.loan_type import LoanType, get_loan_type_display_name
from config.settings import EXPLAINER_MODEL, SUMMARY_MODEL, LLM_TEMPERATURE, LLM_TEMPERATURE_CREATIVE, LLM_SEED
from utils.llm_utils import strip_think
from config.prompts import (
    CUSTOMER_REVIEW_PROMPT,
    CUSTOMER_PERSONA_PROMPT,
    BUREAU_REVIEW_PROMPT,
    COMBINED_EXECUTIVE_PROMPT,
)
import config.thresholds as T

logger = logging.getLogger(__name__)

# Default model for summary generation — dedicated reasoning model
_SUMMARY_MODEL = SUMMARY_MODEL


def create_summary_chain(model_name: str = _SUMMARY_MODEL):
    """
    Create an LCEL chain for generating customer reviews.

    Args:
        model_name: Ollama model to use (default: llama3.1:8b)

    Returns:
        LCEL chain that takes {customer_id, data_summary} and returns str
    """
    prompt = ChatPromptTemplate.from_template(CUSTOMER_REVIEW_PROMPT)
    llm = ChatOllama(model=model_name, temperature=LLM_TEMPERATURE, seed=LLM_SEED)

    return prompt | llm | StrOutputParser()


def generate_customer_review(
    report: CustomerReport,
    rg_salary_data: dict = None,
    model_name: str = _SUMMARY_MODEL,
) -> Optional[str]:
    """
    Generate an LLM-based customer review from populated report sections.

    This function:
    1. Extracts only populated sections from the report
    2. Builds a data summary string
    3. Invokes the LLM chain
    4. Returns the generated review (or None on failure)

    Args:
        report: CustomerReport with populated sections
        rg_salary_data: Optional RG salary algorithm output — used to prefer
                        the authoritative salary amount over banking detection.
        model_name: Ollama model to use

    Returns:
        Generated review string, or None if generation fails
    """
    # Build data summary from populated sections only
    sections = _build_data_summary(report, rg_salary_data=rg_salary_data)

    if not sections:
        return None

    data_summary = "\n".join(sections)

    try:
        chain = create_summary_chain(model_name)
        raw = chain.invoke({
            "customer_id": mask_customer_id(report.meta.customer_id),
            "data_summary": data_summary,
        })
        review = strip_think(raw, label="CustomerReview")
        return review.strip() if review else None
    except Exception as e:
        logger.warning("Customer review generation failed: %s", e)
        return None


def _build_data_summary(report: CustomerReport, rg_salary_data: dict = None) -> list:
    """
    Build data summary lines from populated report sections.

    Only includes sections that have data - never mentions
    missing sections.

    Args:
        report: CustomerReport to summarize
        rg_salary_data: Optional RG salary algorithm output dict.

    Returns:
        List of summary strings for each populated section
    """
    sections = []

    # Resolve authoritative salary — rg_sal first (same priority as scorecard)
    _rg_sal = (rg_salary_data or {}).get("rg_sal") if rg_salary_data else None
    _auth_salary_amt = (
        (_rg_sal.get("salary_amount") if _rg_sal else None)
        or (report.salary.avg_amount if report.salary else None)
    )
    _auth_salary_merchant = (
        (_rg_sal.get("merchant") if _rg_sal else None)
        or (report.salary.narration.split()[0].title() if report.salary and report.salary.narration else None)
    )

    # Category spending
    if report.category_overview:
        top_cats = sorted(
            report.category_overview.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        cats_str = ", ".join(f"{k}: {v:,.0f}" for k, v in top_cats)
        sections.append(f"Top spending categories: {cats_str}")

    # Monthly cashflow
    if report.monthly_cashflow:
        total_inflow = sum(m.get('inflow', 0) for m in report.monthly_cashflow)
        total_outflow = sum(m.get('outflow', 0) for m in report.monthly_cashflow)
        avg_net = (total_inflow - total_outflow) / max(1, len(report.monthly_cashflow))
        sections.append(
            f"Monthly cashflow: Avg net {avg_net:,.0f} INR "
            f"(Total in: {total_inflow:,.0f}, out: {total_outflow:,.0f})"
        )

    # Salary — use authoritative amount (rg_sal preferred, same as scorecard)
    if _auth_salary_amt:
        merchant_str = f" from {_auth_salary_merchant}" if _auth_salary_merchant else ""
        # Use rg_sal count when rg_sal provides the amount; fall back to banking detection
        if _rg_sal and _rg_sal.get("salary_amount"):
            _rg_sal_count = _rg_sal.get("transaction_count")
            freq_str = f" ({_rg_sal_count} months)" if _rg_sal_count else ""
        elif report.salary:
            freq_str = f" ({report.salary.frequency} transactions)"
        else:
            freq_str = ""
        sections.append(
            f"Salary income: {_auth_salary_amt:,.0f} INR average{merchant_str}{freq_str}"
        )

    # EMIs — EMIBlock.amount is per-transaction average, not total
    if report.emis:
        avg_emi = sum(e.amount for e in report.emis)
        emi_count = sum(e.frequency for e in report.emis)
        sections.append(f"EMI commitments: {avg_emi:,.0f} INR average per payment ({emi_count} debit transactions)")

    # Rent
    if report.rent:
        sections.append(
            f"Rent payments: {report.rent.amount:,.0f} INR "
            f"({report.rent.frequency} transactions)"
        )

    # Banking FOIR (computed from available EMI + rent / salary)
    # Note: e.amount and rent.amount are per-transaction averages, which approximates monthly obligation
    if _auth_salary_amt and _auth_salary_amt > 0:
        _emi_avg = sum(e.amount for e in report.emis) if report.emis else 0
        _rent_amt = report.rent.amount if report.rent else 0
        _foir = (_emi_avg + _rent_amt) / _auth_salary_amt * 100
        _tag = " [OVER-LEVERAGED]" if _foir > 65 else (" [STRETCHED]" if _foir > 40 else " [COMFORTABLE]")
        sections.append(f"Banking FOIR (EMI+Rent/Salary): {_foir:.1f}%{_tag}")

    # Bills
    if report.bills:
        total_bills = sum(b.avg_amount * b.frequency for b in report.bills)
        sections.append(f"Utility bills: {total_bills:,.0f} INR total")

    # Top merchants
    if report.top_merchants:
        top_merchant = report.top_merchants[0]
        sections.append(
            f"Most frequent merchant: {top_merchant.get('name', 'Unknown')} "
            f"({top_merchant.get('count', 0)} transactions, "
            f"{top_merchant.get('total', 0):,.0f} INR)"
        )

    # Account quality observations — presented as plain facts, no score label
    if report.account_quality:
        obs = report.account_quality.get("observations", [])
        for ob in obs:
            sections.append(ob)

    # Detected transaction events (PF withdrawal, post-salary routing, etc.)
    if report.events:
        from tools.event_detector import format_events_for_prompt
        events_block = format_events_for_prompt(report.events)
        if events_block:
            sections.append(events_block)

    return sections


def create_persona_chain(model_name: str = _SUMMARY_MODEL):
    """Create an LCEL chain for generating customer persona."""
    prompt = ChatPromptTemplate.from_template(CUSTOMER_PERSONA_PROMPT)
    llm = ChatOllama(model=model_name, temperature=LLM_TEMPERATURE_CREATIVE, seed=LLM_SEED)
    return prompt | llm | StrOutputParser()


def generate_customer_persona(
    report: CustomerReport,
    model_name: str = _SUMMARY_MODEL,
) -> Optional[str]:
    """
    Generate an LLM-based customer persona from all available data.

    Uses comprehensive report data plus transaction samples to create
    a 4-5 line persona description of the customer.

    Args:
        report: CustomerReport with populated sections
        model_name: Ollama model to use

    Returns:
        Generated persona string, or None if generation fails
    """
    # Build comprehensive data from report
    comprehensive_data = _build_comprehensive_data(report)

    # Get transaction sample
    transaction_sample = _get_transaction_sample(report.meta.customer_id)

    if not comprehensive_data:
        return None

    try:
        chain = create_persona_chain(model_name)
        raw = chain.invoke({
            "customer_id": mask_customer_id(report.meta.customer_id),
            "comprehensive_data": comprehensive_data,
            "transaction_sample": transaction_sample,
        })
        persona = strip_think(raw, label="CustomerPersona")
        return persona.strip() if persona else None
    except Exception as e:
        logger.warning("Customer persona generation failed: %s", e)
        return None


def _build_comprehensive_data(report: CustomerReport) -> str:
    """
    Build comprehensive data string from all report sections.

    Includes all available data for persona generation.
    """
    lines = []

    # Customer info
    if report.meta.prty_name:
        lines.append(f"Customer Name: {report.meta.prty_name}")
    lines.append(f"Total Transactions: {report.meta.transaction_count}")
    lines.append(f"Analysis Period: {report.meta.analysis_period}")

    # Compute overall financial metrics
    if report.monthly_cashflow:
        total_inflow = sum(m.get('inflow', 0) for m in report.monthly_cashflow)
        total_outflow = sum(m.get('outflow', 0) for m in report.monthly_cashflow)
        savings_rate = (total_inflow - total_outflow) / total_inflow if total_inflow > 0 else 0
        lines.append(f"\nFINANCIAL OVERVIEW:")
        lines.append(f"Total Income: {total_inflow:,.0f} INR")
        lines.append(f"Total Expenses: {total_outflow:,.0f} INR")
        lines.append(f"Net Position: {total_inflow - total_outflow:,.0f} INR")
        lines.append(f"Savings Rate: {savings_rate:.1%}")

    # Salary info
    if report.salary:
        lines.append(f"\nINCOME:")
        lines.append(f"Salary: {report.salary.avg_amount:,.0f} INR average ({report.salary.frequency} payments)")
        if report.salary.narration:
            lines.append(f"Source: {report.salary.narration[:60]}")

    # All spending categories
    if report.category_overview:
        lines.append(f"\nSPENDING BY CATEGORY:")
        sorted_cats = sorted(report.category_overview.items(), key=lambda x: x[1], reverse=True)
        for cat, amount in sorted_cats:
            lines.append(f"  - {cat}: {amount:,.0f} INR")

    # Monthly cashflow trend
    if report.monthly_cashflow:
        lines.append(f"\nMONTHLY CASHFLOW:")
        positive_months = sum(1 for m in report.monthly_cashflow if m.get('net', 0) > 0)
        negative_months = len(report.monthly_cashflow) - positive_months
        lines.append(f"Positive months: {positive_months}, Negative months: {negative_months}")

    # EMI commitments
    if report.emis:
        total_emi = sum(e.amount for e in report.emis)
        lines.append(f"\nEMI COMMITMENTS: {total_emi:,.0f} INR total")

    # Rent
    if report.rent:
        lines.append(f"\nRENT: {report.rent.amount:,.0f} INR ({report.rent.frequency} payments)")

    # Bills
    if report.bills:
        total_bills = sum(b.avg_amount * b.frequency for b in report.bills)
        lines.append(f"\nUTILITY BILLS: {total_bills:,.0f} INR total")

    # Top merchants
    if report.top_merchants:
        lines.append(f"\nTOP MERCHANTS:")
        for m in report.top_merchants[:5]:
            lines.append(f"  - {m.get('name', 'Unknown')[:40]}: {m.get('count', 0)} txns, {m.get('total', 0):,.0f} INR")

    return "\n".join(lines)


def _get_transaction_sample(customer_id: int, limit: int = 20) -> str:
    """
    Get sample of recent transactions for persona context.

    Args:
        customer_id: Customer to get transactions for
        limit: Maximum transactions to include

    Returns:
        Formatted string of transaction samples
    """
    try:
        df = get_transactions_df()
        cust_df = df[df['cust_id'] == customer_id].copy()

        if len(cust_df) == 0:
            return "No transactions available"

        # Sort by date descending to get recent transactions
        cust_df = cust_df.sort_values('tran_date', ascending=False).head(limit)

        lines = []
        for _, row in cust_df.iterrows():
            date = str(row.get('tran_date', 'N/A'))[:10]
            direction = row.get('dr_cr_indctor', 'D')
            amount = row.get('tran_amt_in_ac', 0)
            category = row.get('category_of_txn', 'Unknown')
            narration = str(row.get('tran_partclr', ''))[:50]

            dir_symbol = '+' if direction == 'C' else '-'
            lines.append(f"{date} | {dir_symbol}{amount:,.0f} | {category} | {narration}")

        return "\n".join(lines)
    except Exception:
        return "Transaction sample unavailable"


# =============================================================================
# Bureau Report — LLM Narration
# =============================================================================


def _annotate_value(value, thresholds):
    """Annotate a value with risk tag based on thresholds.

    Args:
        value: The numeric value (or None).
        thresholds: List of (comparator, threshold, tag) tuples, checked in order.
                    comparator is one of '>', '<', '>=', '<=', '=='.

    Returns:
        Tag string like '[HIGH RISK]' or '[POSITIVE]', or '' if no threshold matched.
    """
    if value is None:
        return ""
    for comparator, threshold, tag in thresholds:
        if comparator == ">" and value > threshold:
            return tag
        elif comparator == ">=" and value >= threshold:
            return tag
        elif comparator == "<" and value < threshold:
            return tag
        elif comparator == "<=" and value <= threshold:
            return tag
        elif comparator == "==" and value == threshold:
            return tag
    return ""


def _format_tradeline_features_for_prompt(tf, product_types: set = None) -> str:
    """Format TradelineFeatures with risk annotations for the LLM prompt.

    Each feature is annotated with a risk interpretation tag based on
    deterministic thresholds. Interaction signals are appended at the end.

    Args:
        tf: TradelineFeatures dataclass or dict.
        product_types: Set of LoanType values present in the portfolio.
                       Product-specific metrics are suppressed when the
                       corresponding product is absent. None = no filtering.
    """
    tf_dict = asdict(tf) if not isinstance(tf, dict) else tf

    # Product-existence guards — prevents narrating metrics for absent products
    has_cc = product_types is None or LoanType.CC in product_types
    has_pl = product_types is None or LoanType.PL in product_types

    def _val(key):
        return tf_dict.get(key)

    def _fmt(value):
        if value is None:
            return "N/A"
        return f"{value:.2f}" if isinstance(value, float) else str(value)

    lines = []

    # --- Loan Activity ---
    lines.append("  LOAN ACTIVITY:")
    v = _val("new_trades_6m_pl")
    if v is not None and has_pl:
        tag = _annotate_value(v, [(">=", T.NEW_PL_6M_HIGH_RISK, " [HIGH RISK — rapid PL acquisition]"),
                                   (">=", T.NEW_PL_6M_MODERATE_RISK, " [MODERATE RISK — multiple recent PLs]")])
        lines.append(f"    New PL Trades in Last 6M: {v}{tag}")
    v = _val("months_since_last_trade_pl")
    if v is not None and has_pl:
        tag = _annotate_value(v, [("<", T.MONTHS_SINCE_TRADE_CONCERN, " [CONCERN — very recent PL activity]")])
        lines.append(f"    Months Since Last PL Trade: {_fmt(v)}{tag}")
    v = _val("months_since_last_trade_uns")
    if v is not None:
        tag = _annotate_value(v, [("<", T.MONTHS_SINCE_TRADE_CONCERN, " [CONCERN — very recent unsecured activity]")])
        lines.append(f"    Months Since Last Unsecured Trade: {_fmt(v)}{tag}")
    # total_trades omitted — already shown in Portfolio Summary from executive inputs

    # --- DPD & Delinquency ---
    lines.append("  DPD & DELINQUENCY:")
    for field, label, required_product in [
        ("max_dpd_6m_cc", "Max DPD Last 6M (CC)", has_cc),
        ("max_dpd_6m_pl", "Max DPD Last 6M (PL)", has_pl),
        ("max_dpd_9m_cc", "Max DPD Last 9M (CC)", has_cc),
    ]:
        if not required_product:
            continue
        v = _val(field)
        if v is not None:
            tag = _annotate_value(v, [(">", T.DPD_HIGH_RISK, " [HIGH RISK — severe delinquency]"),
                                       (">", T.DPD_MODERATE_RISK, " [MODERATE RISK — significant DPD]"),
                                       (">", 0, " [CONCERN — past due detected]"),
                                       ("==", 0, " [CLEAN]")])
            lines.append(f"    {label}: {v}{tag}")
    v = _val("months_since_last_0p_pl")
    if v is not None and has_pl:
        tag = _annotate_value(v, [(">=", T.CLEAN_HISTORY_STRONG_MONTHS, " [POSITIVE — no PL delinquency in 2+ years]"),
                                   (">=", T.CLEAN_HISTORY_GOOD_MONTHS, " [POSITIVE — clean for 1+ year]"),
                                   ("<", T.RECENT_DELINQUENCY_MONTHS, " [CONCERN — recent PL delinquency]")])
        lines.append(f"    Months Since Last 0+ DPD (PL): {_fmt(v)}{tag}")
    v = _val("months_since_last_0p_uns")
    if v is not None:
        tag = _annotate_value(v, [(">=", T.CLEAN_HISTORY_STRONG_MONTHS, " [POSITIVE — no unsecured delinquency in 2+ years]"),
                                   ("<", T.RECENT_DELINQUENCY_MONTHS, " [CONCERN — recent unsecured delinquency]")])
        lines.append(f"    Months Since Last 0+ DPD (Unsecured): {_fmt(v)}{tag}")

    # --- Payment Behavior ---
    lines.append("  PAYMENT BEHAVIOR:")
    v = _val("pct_missed_payments_18m")
    if v is not None:
        if v > T.MISSED_PAYMENTS_HIGH_RISK:
            tag = " [HIGH RISK — frequent missed payments]"
        elif v > 0:
            tag = " [CONCERN — some missed payments]"
        elif v == 0:
            # Check if DPD values are non-zero — if so, 0% missed payments
            # is misleading and should not be tagged as POSITIVE
            has_dpd = any(
                _val(f) is not None and _val(f) > 0
                for f in ["max_dpd_6m_cc", "max_dpd_6m_pl", "max_dpd_9m_cc"]
            )
            if has_dpd:
                tag = " [NOTE — 0% formally missed but DPD delays detected on some products; payments were late]"
            else:
                tag = " [POSITIVE — no missed payments]"
        else:
            tag = ""
        lines.append(f"    % Missed Payments Last 18M: {_fmt(v)}{tag}")
    v = _val("pct_0plus_24m_all")
    if v is not None:
        tag = _annotate_value(v, [(">", T.PCT_0PLUS_HIGH_RISK, " [HIGH RISK]"), (">", 0, " [CONCERN]"),
                                   ("==", 0, " [CLEAN]")])
        lines.append(f"    % Trades with 0+ DPD in 24M (All): {_fmt(v)}{tag}")
    v = _val("pct_0plus_24m_pl")
    if v is not None and has_pl:
        tag = _annotate_value(v, [(">", T.PCT_0PLUS_HIGH_RISK, " [HIGH RISK]"), (">", 0, " [CONCERN]"),
                                   ("==", 0, " [CLEAN]")])
        lines.append(f"    % Trades with 0+ DPD in 24M (PL): {_fmt(v)}{tag}")
    v = _val("pct_trades_0plus_12m")
    if v is not None:
        tag = _annotate_value(v, [(">", T.PCT_0PLUS_HIGH_RISK, " [HIGH RISK]"), (">", 0, " [CONCERN]"),
                                   ("==", 0, " [CLEAN]")])
        lines.append(f"    % Trades with 0+ DPD in 12M (All): {_fmt(v)}{tag}")
    v = _val("ratio_good_closed_pl")
    if v is not None and has_pl:
        tag = _annotate_value(v, [(">=", T.GOOD_CLOSURE_POSITIVE, " [POSITIVE — strong closure track record]"),
                                   ("<", T.GOOD_CLOSURE_HIGH_RISK, " [HIGH RISK — poor closure history]"),
                                   ("<", T.GOOD_CLOSURE_CONCERN, " [CONCERN — below average closure quality]")])
        lines.append(f"    Ratio Good Closed PL Loans: {v * 100:.0f}%{tag}")

    # --- Utilization ---
    lines.append("  UTILIZATION:")
    v = _val("cc_balance_utilization_pct")
    if v is not None and has_cc:
        tag = _annotate_value(v, [(">", T.CC_UTIL_HIGH_RISK, " [HIGH RISK — over-utilized]"),
                                   (">", T.CC_UTIL_MODERATE_RISK, " [MODERATE RISK — elevated utilization]"),
                                   ("<=", T.CC_UTIL_HEALTHY, " [HEALTHY]")])
        lines.append(f"    CC Balance Utilization: {_fmt(v)}%{tag}")
    v = _val("pl_balance_remaining_pct")
    if v is not None and has_pl:
        tag = _annotate_value(v, [(">", T.PL_BAL_REMAINING_HIGH_RISK, " [HIGH RISK — most PL balance still outstanding]"),
                                   (">", T.PL_BAL_REMAINING_MODERATE_RISK, " [MODERATE — significant PL balance remaining]"),
                                   ("<=", T.PL_BAL_REMAINING_POSITIVE, " [POSITIVE — largely repaid]")])
        lines.append(f"    PL Balance Remaining: {_fmt(v)}%{tag}")

    # --- Enquiry Behavior ---
    lines.append("  ENQUIRY BEHAVIOR:")
    v = _val("unsecured_enquiries_12m")
    if v is not None:
        tag = _annotate_value(v, [(">", T.ENQUIRY_HIGH_RISK, " [HIGH RISK — very high enquiry pressure]"),
                                   (">", T.ENQUIRY_MODERATE_RISK, " [MODERATE RISK — elevated enquiry pressure]"),
                                   ("<=", T.ENQUIRY_HEALTHY, " [HEALTHY — minimal enquiry activity]")])
        lines.append(f"    Unsecured Enquiries Last 12M: {v}{tag}")
    v = _val("trade_to_enquiry_ratio_uns_24m")
    if v is not None:
        tag = _annotate_value(v, [(">", T.TRADE_RATIO_POSITIVE, " [POSITIVE — high conversion rate]"),
                                   ("<", T.TRADE_RATIO_CONCERN, " [CONCERN — low conversion, possible rejections]")])
        lines.append(f"    Trade-to-Enquiry Ratio (Unsec 24M): {_fmt(v)}%{tag}")

    # --- Loan Acquisition Velocity ---
    lines.append("  LOAN ACQUISITION VELOCITY:")
    for field, label in [("interpurchase_time_12m_plbl", "PL/BL (12M)"),
                          ("interpurchase_time_6m_plbl", "PL/BL (6M)"),
                          ("interpurchase_time_24m_all", "All Loans (24M)"),
                          ("interpurchase_time_12m_cl", "Consumer Loans (12M)")]:
        v = _val(field)
        if v is None or v == 0.0:   # 0.0 = no loans opened in window; not measurable
            continue
        tag = _annotate_value(v, [("<", T.IPT_HIGH_RISK, " [HIGH RISK — rapid loan stacking]"),
                                   ("<", T.IPT_CONCERN, " [CONCERN — frequent acquisitions]"),
                                   (">=", T.IPT_HEALTHY, " [HEALTHY — measured pace]")])
        lines.append(f"    Avg Interpurchase Time {label}: {_fmt(v)} months{tag}")
    # Include HL/LAP and TWL only if present (less common)
    for field, label in [("interpurchase_time_9m_hl_lap", "HL/LAP (9M)"),
                          ("interpurchase_time_24m_hl_lap", "HL/LAP (24M)"),
                          ("interpurchase_time_24m_twl", "TWL (24M)")]:
        v = _val(field)
        if v is not None:
            lines.append(f"    Avg Interpurchase Time {label}: {_fmt(v)} months")

    # --- Interaction Signals (deterministic, computed from feature combinations) ---
    interaction_signals = _compute_interaction_signals(tf_dict)
    if interaction_signals:
        lines.append("  COMPOSITE RISK SIGNALS:")
        for signal in interaction_signals:
            lines.append(f"    >> {signal}")

    return "\n".join(lines)


def _compute_interaction_signals(tf_dict: dict) -> list:
    """Compute interaction-based risk signals from feature combinations.

    These are deterministic interpretations that require looking at
    multiple features together — something the LLM shouldn't do.
    """
    signals = []

    enquiries = tf_dict.get("unsecured_enquiries_12m")
    ipt_plbl = tf_dict.get("interpurchase_time_12m_plbl")
    new_pl_6m = tf_dict.get("new_trades_6m_pl")

    # Credit hungry + loan stacking
    if enquiries is not None and enquiries > T.COMPOSITE_ENQUIRY_THRESHOLD and new_pl_6m is not None and new_pl_6m >= T.COMPOSITE_NEW_PL_TRIGGER:
        signals.append("CREDIT HUNGRY + LOAN STACKING: High enquiry activity ({}x in 12M) "
                        "combined with {} new PL trades in 6M".format(enquiries, new_pl_6m))

    # Rapid loan stacking with low interpurchase time
    if ipt_plbl is not None and ipt_plbl < T.IPT_CONCERN and new_pl_6m is not None and new_pl_6m >= T.COMPOSITE_NEW_PL_TRIGGER:
        signals.append("RAPID PL STACKING: Avg {:.1f} months between PL/BL acquisitions "
                        "with {} new trades in 6M".format(ipt_plbl, new_pl_6m))

    # Clean repayment profile
    dpd_6m_cc = tf_dict.get("max_dpd_6m_cc")
    dpd_6m_pl = tf_dict.get("max_dpd_6m_pl")
    dpd_9m_cc = tf_dict.get("max_dpd_9m_cc")
    missed = tf_dict.get("pct_missed_payments_18m")
    good_ratio = tf_dict.get("ratio_good_closed_pl")
    pct_0p_24m = tf_dict.get("pct_0plus_24m_all")

    all_dpd_clean = all(v is not None and v == 0 for v in [dpd_6m_cc, dpd_6m_pl, dpd_9m_cc])
    missed_clean = missed is not None and missed == 0
    pct_clean = pct_0p_24m is not None and pct_0p_24m == 0

    if all_dpd_clean and missed_clean and pct_clean:
        msg = "CLEAN REPAYMENT PROFILE: Zero DPD across all products and windows, no missed payments"
        if good_ratio is not None and good_ratio >= T.GOOD_CLOSURE_POSITIVE:
            msg += f", {good_ratio:.0%} good PL closure ratio"
        signals.append(msg)

    # Missed payments = 0 but DPD detected — apparent contradiction
    if missed_clean and not all_dpd_clean:
        dpd_details = []
        if dpd_6m_cc is not None and dpd_6m_cc > 0:
            dpd_details.append(f"CC 6M: {dpd_6m_cc} days")
        if dpd_6m_pl is not None and dpd_6m_pl > 0:
            dpd_details.append(f"PL 6M: {dpd_6m_pl} days")
        if dpd_9m_cc is not None and dpd_9m_cc > 0:
            dpd_details.append(f"CC 9M: {dpd_9m_cc} days")
        if dpd_details:
            signals.append(
                "PAYMENT TIMING NUANCE: 0% missed payments in 18M but DPD detected ({}) — "
                "payments were eventually made but past due date; do NOT describe payment "
                "record as clean or positive".format(", ".join(dpd_details))
            )

    # High utilization + high outstanding
    cc_util = tf_dict.get("cc_balance_utilization_pct")
    pl_bal = tf_dict.get("pl_balance_remaining_pct")
    if cc_util is not None and cc_util > T.COMPOSITE_UTIL_LEVERAGE and pl_bal is not None and pl_bal > T.COMPOSITE_BAL_LEVERAGE:
        signals.append("ELEVATED LEVERAGE: CC utilization at {:.1f}% and {:.1f}% "
                        "PL balance still outstanding".format(cc_util, pl_bal))

    # High enquiries but low conversion (possible repeated rejections)
    trade_ratio = tf_dict.get("trade_to_enquiry_ratio_uns_24m")
    if enquiries is not None and enquiries > T.COMPOSITE_ENQUIRY_THRESHOLD and trade_ratio is not None and trade_ratio < T.COMPOSITE_TRADE_RATIO_LOW:
        signals.append("LOW CONVERSION: High enquiry volume ({}) but only {:.1f}% "
                        "trade-to-enquiry conversion — suggests possible rejections".format(
                            enquiries, trade_ratio))

    return signals


def _build_bureau_data_summary(executive_inputs, tradeline_features=None, monthly_exposure=None) -> str:
    """Format BureauExecutiveSummaryInputs into a text block for the LLM prompt.

    Args:
        executive_inputs: BureauExecutiveSummaryInputs dataclass instance.
        tradeline_features: Optional TradelineFeatures dataclass instance.
        monthly_exposure: Optional monthly_exposure dict from BureauReport.

    Returns:
        Formatted text summary string.
    """
    data = asdict(executive_inputs) if not isinstance(executive_inputs, dict) else executive_inputs
    product_breakdown = data.pop("product_breakdown", {})

    # Max DPD with timing info
    max_dpd = data.get('max_dpd', 'N/A')
    max_dpd_str = str(max_dpd) if max_dpd is not None else "N/A"
    dpd_months = data.get('max_dpd_months_ago')
    dpd_lt = data.get('max_dpd_loan_type')
    if max_dpd is not None and max_dpd != 'N/A':
        details = []
        if dpd_months is not None:
            details.append(f"{dpd_months} months ago")
        if dpd_lt:
            details.append(dpd_lt)
        if details:
            max_dpd_str += f" ({', '.join(details)})"

    # Unsecured outstanding as % of total outstanding
    total_os = data.get('total_outstanding', 0)
    unsec_os = data.get('unsecured_outstanding', 0)
    unsec_os_pct = f"{(unsec_os / total_os * 100):.0f}%" if total_os > 0 else "N/A"

    lines = [
        f"Total Tradelines: {data.get('total_tradelines', 0)}",
        f"Live Tradelines: {data.get('live_tradelines', 0)}",
        f"Closed Tradelines: {data.get('closed_tradelines', 0)}",
        f"Total Sanction Amount: INR {format_inr(data.get('total_sanctioned', 0))}",
        f"Total Outstanding: INR {format_inr(data.get('total_outstanding', 0))}",
        f"Unsecured Sanction Amount: INR {format_inr(data.get('unsecured_sanctioned', 0))}",
        f"Unsecured Outstanding: {unsec_os_pct} of total outstanding",
        f"Max DPD (Days Past Due): {max_dpd_str}",
    ]

    # Add CC utilization if available in product breakdown
    for loan_type_key, vec in product_breakdown.items():
        vec_data = asdict(vec) if not isinstance(vec, dict) else vec
        util = vec_data.get("utilization_ratio")
        if util is not None:
            lt_display = get_loan_type_display_name(loan_type_key)
            lines.append(f"{lt_display} Utilization: {util * 100:.1f}%")

    # Obligation & FOIR
    if tradeline_features is not None:
        tl = tradeline_features
        tl_d = asdict(tl) if not isinstance(tl, dict) else tl
        aff_emi = tl_d.get("aff_emi")
        unsecured_emi = tl_d.get("unsecured_emi")
        foir = tl_d.get("foir")
        foir_unsec = tl_d.get("foir_unsec")
        affluence_amt = tl_d.get("affluence_amt")
        if any(v is not None for v in [aff_emi, foir, foir_unsec]):
            lines.append("\nObligation & FOIR:")
            if affluence_amt is not None:
                lines.append(f"  Affluence Income (6M est.): INR {format_inr(affluence_amt)}")
            if aff_emi is not None:
                lines.append(f"  Total Bureau EMI Obligation (all products): INR {format_inr(aff_emi)}")
            if unsecured_emi is not None:
                lines.append(f"  Unsecured EMI Obligation: INR {format_inr(unsecured_emi)}")
            if foir is not None:
                tag = " [OVER-LEVERAGED]" if foir > 65 else (" [STRETCHED]" if foir > 40 else " [COMFORTABLE]")
                lines.append(f"  FOIR (total): {foir:.1f}%{tag}")
            if foir_unsec is not None:
                tag_u = " [OVER-LEVERAGED]" if foir_unsec > 65 else (" [STRETCHED]" if foir_unsec > 40 else " [COMFORTABLE]")
                lines.append(f"  FOIR (unsecured only): {foir_unsec:.1f}%{tag_u}")

    # Product breakdown
    if product_breakdown:
        lines.append("\nProduct-wise Breakdown:")
        for loan_type_key, vec in product_breakdown.items():
            vec_data = asdict(vec) if not isinstance(vec, dict) else vec
            lt_display = get_loan_type_display_name(loan_type_key)
            lines.append(
                f"  - {lt_display}: {vec_data.get('loan_count', 0)} accounts "
                f"(Live: {vec_data.get('live_count', 0)}, Closed: {vec_data.get('closed_count', 0)}), "
                f"Sanctioned: INR {format_inr(vec_data.get('total_sanctioned_amount', 0))}, "
                f"Outstanding: INR {format_inr(vec_data.get('total_outstanding_amount', 0))}"
            )

    # Tradeline behavioral features
    if tradeline_features is not None:
        lines.append("\nBehavioral & Risk Features:")
        _product_types = set(product_breakdown.keys()) if product_breakdown else None
        lines.append(_format_tradeline_features_for_prompt(tradeline_features, product_types=_product_types))

    # Exposure trend (12M point-in-time + 6M avg)
    if monthly_exposure:
        months_list = monthly_exposure.get("months", [])
        series = monthly_exposure.get("series", {})
        if months_list and series:
            n = len(months_list)
            totals = [
                sum(series[lt][i] for lt in series if i < len(series[lt]))
                for i in range(n)
            ]
            if any(t > 0 for t in totals):
                trend_lines = []
                if n >= 13:
                    cur, ago = totals[-1], totals[-13]
                    if ago > 0:
                        pct = (cur - ago) / ago * 100
                        direction = "increased" if pct > 0 else "decreased"
                        trend_lines.append(
                            f"Sanctioned exposure 12M trend: {direction} by {abs(pct):.0f}% "
                            f"({_inr(ago)} → {_inr(cur)})"
                        )
                if n >= 7:
                    recent_avg = sum(totals[-6:]) / 6
                    prior_slice = totals[-12:-6] if n >= 12 else totals[:max(1, n - 6)]
                    prior_avg = sum(prior_slice) / len(prior_slice) if prior_slice else 0
                    if prior_avg > 0:
                        pct6 = (recent_avg - prior_avg) / prior_avg * 100
                        direction6 = "increased" if pct6 > 0 else "decreased"
                        trend_lines.append(
                            f"Sanctioned exposure 6M avg trend: {direction6} by {abs(pct6):.0f}% "
                            f"(prior 6M avg {_inr(prior_avg)} → recent 6M avg {_inr(recent_avg)})"
                        )
                if trend_lines:
                    lines.append("\nSanctioned Exposure Trend:")
                    lines.extend(trend_lines)

        # Human-readable exposure commentary (peak, current state, active products)
        exposure_text = summarize_exposure_timeline(monthly_exposure)
        if exposure_text:
            lines.append(f"\nExposure Commentary: {exposure_text}")

    return "\n".join(lines)


def generate_bureau_review(
    executive_inputs,
    tradeline_features=None,
    monthly_exposure=None,
    model_name: str = _SUMMARY_MODEL,
) -> Optional[str]:
    """Generate an LLM-based bureau portfolio review from executive summary inputs.

    The LLM receives ONLY pre-computed numbers — no raw tradeline data.

    Args:
        executive_inputs: BureauExecutiveSummaryInputs (dataclass or dict).
        tradeline_features: Optional TradelineFeatures (dataclass or dict).
        monthly_exposure: Optional monthly_exposure dict from BureauReport.
        model_name: Ollama model to use.

    Returns:
        Generated narrative string, or None if generation fails.
    """
    data_summary = _build_bureau_data_summary(executive_inputs, tradeline_features, monthly_exposure)

    if not data_summary:
        return None

    try:
        prompt = ChatPromptTemplate.from_template(BUREAU_REVIEW_PROMPT)
        llm = ChatOllama(model=model_name, temperature=LLM_TEMPERATURE, seed=LLM_SEED)
        chain = prompt | llm | StrOutputParser()

        raw = chain.invoke({"data_summary": data_summary})
        review = strip_think(raw, label="BureauReview")
        return review.strip() if review else None
    except Exception as e:
        logger.warning("Bureau review generation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Combined Executive Summary (banking + bureau synthesised)
# ---------------------------------------------------------------------------


def generate_combined_executive_summary(
    banking_summary: str,
    bureau_summary: str,
    customer_id: str,
    exposure_summary: str = "",
    foir_context: str = "",
    model_name: str = _SUMMARY_MODEL,
) -> Optional[str]:
    """Generate a unified executive summary from both banking and bureau narratives.

    Args:
        banking_summary: The customer_review text from the banking report.
        bureau_summary: The narrative text from the bureau report.
        customer_id: Masked customer identifier.
        exposure_summary: Optional human-readable 2-sentence exposure commentary.
        foir_context: Optional pre-formatted FOIR string (e.g. "FOIR (total): 68.5%, FOIR (unsecured): 60.8%").
        model_name: Ollama model to use.

    Returns:
        Synthesised summary string, or None if generation fails.
    """
    if not banking_summary and not bureau_summary:
        return None

    # Build additional structured context block
    additional_parts = []
    if foir_context:
        additional_parts.append(f"FOIR / Obligation: {foir_context}")
    if exposure_summary:
        additional_parts.append(f"Exposure Commentary: {exposure_summary}")
    additional_context = ("\nAdditional Data:\n" + "\n".join(additional_parts)) if additional_parts else ""

    try:
        prompt = ChatPromptTemplate.from_template(COMBINED_EXECUTIVE_PROMPT)
        llm = ChatOllama(model=model_name, temperature=0, seed=LLM_SEED)
        chain = prompt | llm | StrOutputParser()

        raw = chain.invoke({
            "customer_id": customer_id,
            "banking_summary": banking_summary or "(not available)",
            "bureau_summary": bureau_summary or "(not available)",
            "additional_context": additional_context,
        })
        result = strip_think(raw, label="CombinedSummary")
        return result.strip() if result else None
    except Exception as e:
        logger.warning("Combined executive summary generation failed: %s", e)
        return None


# =============================================================================
# Shared helpers
# =============================================================================

def _inr(amt: float) -> str:
    """Format INR amount as ₹X.XL (lakhs) or ₹X.XCr (crores)."""
    if amt >= 1e7:
        return f"₹{amt / 1e7:.1f}Cr"
    elif amt >= 1e5:
        return f"₹{amt / 1e5:.1f}L"
    else:
        return f"₹{amt:,.0f}"


# =============================================================================
# Loan Exposure Timeline Summary  (deterministic — no LLM)
# =============================================================================

def summarize_exposure_timeline(monthly_exposure: dict) -> str:
    """Generate a 2-sentence plain-English summary of the loan exposure chart.

    Reads the pre-computed monthly_exposure dict (from BureauReport.monthly_exposure)
    and returns two sentences covering:
      1. Peak total exposure — when it occurred, which products drove it.
      2. Current exposure vs peak — trend direction, active products.

    Args:
        monthly_exposure: {"months": [...], "series": {"PL": [...], "CC": [...], ...}}

    Returns:
        Two-sentence string, or empty string if data is missing/empty.
    """
    if not monthly_exposure:
        return ""

    months = monthly_exposure.get("months", [])
    series = monthly_exposure.get("series", {})

    if not months or not series:
        return ""

    n = len(months)

    # ── Per-month totals ──────────────────────────────────────────────────────
    totals = [sum(series[lt][i] for lt in series if i < len(series[lt])) for i in range(n)]

    peak_idx = totals.index(max(totals))
    peak_total = totals[peak_idx]
    peak_month = months[peak_idx]
    current_total = totals[-1]
    current_month = months[-1]

    if peak_total == 0:
        return ""

    # ── Sentence 1: peak breakdown ────────────────────────────────────────────
    # Top-2 products at peak month
    peak_by_product = {
        lt: series[lt][peak_idx]
        for lt in series
        if peak_idx < len(series[lt]) and series[lt][peak_idx] > 0
    }
    top_products = sorted(peak_by_product.items(), key=lambda x: x[1], reverse=True)[:2]
    product_str = " and ".join(f"{lt} ({_inr(amt)})" for lt, amt in top_products)

    if product_str:
        sent1 = (
            f"Sanctioned exposure peaked at {_inr(peak_total)} in {peak_month}, "
            f"led by {product_str}."
        )
    else:
        sent1 = f"Sanctioned exposure peaked at {_inr(peak_total)} in {peak_month}."

    # ── Sentence 2: current state + trend ────────────────────────────────────
    # Active products: non-zero in last 3 months
    recent_window = min(3, n)
    active_now = [
        lt for lt in series
        if any(series[lt][-(recent_window - j)] > 0 for j in range(recent_window)
               if -(recent_window - j) != 0 or n > 0)
    ]
    # Simpler: just check last value
    active_now = [lt for lt in series if series[lt][-1] > 0]
    active_str = ", ".join(active_now) if active_now else "none"

    # Trend: compare last 6M avg vs prior 6M avg
    if n >= 12:
        recent_avg = sum(totals[-6:]) / 6
        prior_avg = sum(totals[-12:-6]) / 6
        if prior_avg > 0:
            pct_change = (recent_avg - prior_avg) / prior_avg * 100
            if pct_change <= -10:
                trend = "declining"
            elif pct_change >= 10:
                trend = "rising"
            else:
                trend = "stable"
        else:
            trend = "rising" if recent_avg > 0 else "stable"
    else:
        trend = "stable"

    if current_total == 0:
        sent2 = f"As of {current_month}, no active sanctioned exposure remains."
    elif current_total == peak_total:
        sent2 = (
            f"Current exposure of {_inr(current_total)} ({active_str}) "
            f"remains at peak levels — trend {trend}."
        )
    else:
        pct_from_peak = (peak_total - current_total) / peak_total * 100
        sent2 = (
            f"Current exposure stands at {_inr(current_total)} ({active_str} active), "
            f"down {pct_from_peak:.0f}% from peak — trend {trend}."
        )

    return f"{sent1} {sent2}"
