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
from schemas.loan_type import get_loan_type_display_name
from config.settings import EXPLAINER_MODEL, LLM_TEMPERATURE, LLM_TEMPERATURE_CREATIVE, LLM_SEED
from config.prompts import (
    CUSTOMER_REVIEW_PROMPT,
    CUSTOMER_PERSONA_PROMPT,
    BUREAU_REVIEW_PROMPT,
    COMBINED_EXECUTIVE_PROMPT,
)
import config.thresholds as T

logger = logging.getLogger(__name__)

# Default model for summary generation (from settings)
SUMMARY_MODEL = EXPLAINER_MODEL


def create_summary_chain(model_name: str = SUMMARY_MODEL):
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
    model_name: str = SUMMARY_MODEL
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
        model_name: Ollama model to use

    Returns:
        Generated review string, or None if generation fails
    """
    # Build data summary from populated sections only
    sections = _build_data_summary(report)

    if not sections:
        return None

    data_summary = "\n".join(sections)

    try:
        chain = create_summary_chain(model_name)
        review = chain.invoke({
            "customer_id": mask_customer_id(report.meta.customer_id),
            "data_summary": data_summary
        })
        return review.strip() if review else None
    except Exception as e:
        logger.warning("Customer review generation failed: %s", e)
        return None


def _build_data_summary(report: CustomerReport) -> list:
    """
    Build data summary lines from populated report sections.

    Only includes sections that have data - never mentions
    missing sections.

    Args:
        report: CustomerReport to summarize

    Returns:
        List of summary strings for each populated section
    """
    sections = []

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

    # Salary
    if report.salary:
        sections.append(
            f"Salary income: {report.salary.avg_amount:,.0f} INR average "
            f"({report.salary.frequency} transactions)"
        )

    # EMIs
    if report.emis:
        total_emi = sum(e.amount for e in report.emis)
        emi_count = sum(e.frequency for e in report.emis)
        sections.append(f"EMI commitments: {total_emi:,.0f} INR ({emi_count} payments)")

    # Rent
    if report.rent:
        sections.append(
            f"Rent payments: {report.rent.amount:,.0f} INR "
            f"({report.rent.frequency} transactions)"
        )

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


def create_persona_chain(model_name: str = SUMMARY_MODEL):
    """Create an LCEL chain for generating customer persona."""
    prompt = ChatPromptTemplate.from_template(CUSTOMER_PERSONA_PROMPT)
    llm = ChatOllama(model=model_name, temperature=LLM_TEMPERATURE_CREATIVE, seed=LLM_SEED)
    return prompt | llm | StrOutputParser()


def generate_customer_persona(
    report: CustomerReport,
    model_name: str = SUMMARY_MODEL
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
        persona = chain.invoke({
            "customer_id": mask_customer_id(report.meta.customer_id),
            "comprehensive_data": comprehensive_data,
            "transaction_sample": transaction_sample
        })
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


def _format_tradeline_features_for_prompt(tf) -> str:
    """Format TradelineFeatures with risk annotations for the LLM prompt.

    Each feature is annotated with a risk interpretation tag based on
    deterministic thresholds. Interaction signals are appended at the end.
    """
    tf_dict = asdict(tf) if not isinstance(tf, dict) else tf

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
    if v is not None:
        tag = _annotate_value(v, [(">=", T.NEW_PL_6M_HIGH_RISK, " [HIGH RISK — rapid PL acquisition]"),
                                   (">=", T.NEW_PL_6M_MODERATE_RISK, " [MODERATE RISK — multiple recent PLs]")])
        lines.append(f"    New PL Trades in Last 6M: {v}{tag}")
    v = _val("months_since_last_trade_pl")
    if v is not None:
        tag = _annotate_value(v, [("<", T.MONTHS_SINCE_TRADE_CONCERN, " [CONCERN — very recent PL activity]")])
        lines.append(f"    Months Since Last PL Trade: {_fmt(v)}{tag}")
    v = _val("months_since_last_trade_uns")
    if v is not None:
        tag = _annotate_value(v, [("<", T.MONTHS_SINCE_TRADE_CONCERN, " [CONCERN — very recent unsecured activity]")])
        lines.append(f"    Months Since Last Unsecured Trade: {_fmt(v)}{tag}")
    # total_trades omitted — already shown in Portfolio Summary from executive inputs

    # --- DPD & Delinquency ---
    lines.append("  DPD & DELINQUENCY:")
    for field, label in [("max_dpd_6m_cc", "Max DPD Last 6M (CC)"),
                          ("max_dpd_6m_pl", "Max DPD Last 6M (PL)"),
                          ("max_dpd_9m_cc", "Max DPD Last 9M (CC)")]:
        v = _val(field)
        if v is not None:
            tag = _annotate_value(v, [(">", T.DPD_HIGH_RISK, " [HIGH RISK — severe delinquency]"),
                                       (">", T.DPD_MODERATE_RISK, " [MODERATE RISK — significant DPD]"),
                                       (">", 0, " [CONCERN — past due detected]"),
                                       ("==", 0, " [CLEAN]")])
            lines.append(f"    {label}: {v}{tag}")
    v = _val("months_since_last_0p_pl")
    if v is not None:
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
    if v is not None:
        tag = _annotate_value(v, [(">", T.PCT_0PLUS_HIGH_RISK, " [HIGH RISK]"), (">", 0, " [CONCERN]"),
                                   ("==", 0, " [CLEAN]")])
        lines.append(f"    % Trades with 0+ DPD in 24M (PL): {_fmt(v)}{tag}")
    v = _val("pct_trades_0plus_12m")
    if v is not None:
        tag = _annotate_value(v, [(">", T.PCT_0PLUS_HIGH_RISK, " [HIGH RISK]"), (">", 0, " [CONCERN]"),
                                   ("==", 0, " [CLEAN]")])
        lines.append(f"    % Trades with 0+ DPD in 12M (All): {_fmt(v)}{tag}")
    v = _val("ratio_good_closed_pl")
    if v is not None:
        tag = _annotate_value(v, [(">=", T.GOOD_CLOSURE_POSITIVE, " [POSITIVE — strong closure track record]"),
                                   ("<", T.GOOD_CLOSURE_HIGH_RISK, " [HIGH RISK — poor closure history]"),
                                   ("<", T.GOOD_CLOSURE_CONCERN, " [CONCERN — below average closure quality]")])
        lines.append(f"    Ratio Good Closed PL Loans: {v * 100:.0f}%{tag}")

    # --- Utilization ---
    lines.append("  UTILIZATION:")
    v = _val("cc_balance_utilization_pct")
    if v is not None:
        tag = _annotate_value(v, [(">", T.CC_UTIL_HIGH_RISK, " [HIGH RISK — over-utilized]"),
                                   (">", T.CC_UTIL_MODERATE_RISK, " [MODERATE RISK — elevated utilization]"),
                                   ("<=", T.CC_UTIL_HEALTHY, " [HEALTHY]")])
        lines.append(f"    CC Balance Utilization: {_fmt(v)}%{tag}")
    v = _val("pl_balance_remaining_pct")
    if v is not None:
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
        if v is not None:
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


def _build_bureau_data_summary(executive_inputs, tradeline_features=None) -> str:
    """Format BureauExecutiveSummaryInputs into a text block for the LLM prompt.

    Args:
        executive_inputs: BureauExecutiveSummaryInputs dataclass instance.
        tradeline_features: Optional TradelineFeatures dataclass instance.

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
        lines.append(_format_tradeline_features_for_prompt(tradeline_features))

    return "\n".join(lines)


def generate_bureau_review(
    executive_inputs,
    tradeline_features=None,
    model_name: str = SUMMARY_MODEL,
) -> Optional[str]:
    """Generate an LLM-based bureau portfolio review from executive summary inputs.

    The LLM receives ONLY pre-computed numbers — no raw tradeline data.

    Args:
        executive_inputs: BureauExecutiveSummaryInputs (dataclass or dict).
        tradeline_features: Optional TradelineFeatures (dataclass or dict).
        model_name: Ollama model to use.

    Returns:
        Generated narrative string, or None if generation fails.
    """
    data_summary = _build_bureau_data_summary(executive_inputs, tradeline_features)

    if not data_summary:
        return None

    try:
        prompt = ChatPromptTemplate.from_template(BUREAU_REVIEW_PROMPT)
        llm = ChatOllama(model=model_name, temperature=LLM_TEMPERATURE, seed=LLM_SEED)
        chain = prompt | llm | StrOutputParser()

        review = chain.invoke({"data_summary": data_summary})
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
    model_name: str = SUMMARY_MODEL,
) -> Optional[str]:
    """Generate a unified executive summary from both banking and bureau narratives.

    Args:
        banking_summary: The customer_review text from the banking report.
        bureau_summary: The narrative text from the bureau report.
        customer_id: Masked customer identifier.
        model_name: Ollama model to use.

    Returns:
        Synthesised summary string, or None if generation fails.
    """
    if not banking_summary and not bureau_summary:
        return None

    try:
        prompt = ChatPromptTemplate.from_template(COMBINED_EXECUTIVE_PROMPT)
        llm = ChatOllama(model=model_name, temperature=LLM_TEMPERATURE, seed=LLM_SEED)
        chain = prompt | llm | StrOutputParser()

        result = chain.invoke({
            "customer_id": customer_id,
            "banking_summary": banking_summary or "(not available)",
            "bureau_summary": bureau_summary or "(not available)",
        })
        return result.strip() if result else None
    except Exception as e:
        logger.warning("Combined executive summary generation failed: %s", e)
        return None
