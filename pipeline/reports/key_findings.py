"""Key findings extractor - deterministic bullet-point generation.

Scans all bureau features (executive inputs, per-loan-type vectors,
tradeline features) and produces structured key findings with inferences.
Each finding is severity-tagged for rendering.

NO LLM calls - purely threshold-based deterministic logic.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from schemas.loan_type import LoanType, get_loan_type_display_name
from features.bureau_features import BureauLoanFeatureVector
from features.tradeline_features import TradelineFeatures
from ..extractors.bureau_feature_aggregator import BureauExecutiveSummaryInputs
from utils.helpers import format_inr
import config.thresholds as T


@dataclass
class KeyFinding:
    """A single key finding with inference."""
    category: str       # Feature group (e.g., "Portfolio", "DPD & Delinquency")
    finding: str        # Factual observation
    inference: str      # Risk/positive interpretation
    severity: str       # "high_risk", "moderate_risk", "concern", "positive", "neutral"


def _timeline_str(vec: BureauLoanFeatureVector) -> str:
    """Build a compact timeline string from a loan type's date range."""
    parts = []
    if vec.earliest_opened:
        if vec.latest_opened and vec.earliest_opened != vec.latest_opened:
            parts.append(f"Opened: {vec.earliest_opened} – {vec.latest_opened}")
        else:
            parts.append(f"Opened: {vec.earliest_opened}")
    if vec.latest_closed:
        parts.append(f"Last Closed: {vec.latest_closed}")
    elif vec.live_count > 0:
        parts.append("Active")
    return " | ".join(parts)


def extract_key_findings(
    executive_inputs: BureauExecutiveSummaryInputs,
    feature_vectors: Dict[LoanType, BureauLoanFeatureVector],
    tradeline_features: Optional[TradelineFeatures] = None,
) -> List[KeyFinding]:
    """Extract key findings from all available bureau data.

    Deterministic: each finding is produced by threshold checks on
    pre-computed features. Returns findings ordered by severity
    (high_risk first, positive last).

    Args:
        executive_inputs: Portfolio-level aggregated data.
        feature_vectors: Per-loan-type feature vectors.
        tradeline_features: Optional customer-level behavioral features.

    Returns:
        List of KeyFinding objects, severity-ordered.
    """
    findings: List[KeyFinding] = []

    # --- Portfolio-level findings ---
    findings.extend(_portfolio_findings(executive_inputs, feature_vectors))

    # --- Per-loan-type findings ---
    findings.extend(_loan_type_findings(feature_vectors))

    # --- Tradeline behavioral findings ---
    if tradeline_features is not None:
        findings.extend(_tradeline_findings(tradeline_features, feature_vectors))

    # --- Composite / interaction findings ---
    if tradeline_features is not None:
        findings.extend(_composite_findings(executive_inputs, tradeline_features, feature_vectors))

    # Sort: high_risk > moderate_risk > concern > neutral > positive
    severity_order = {"high_risk": 0, "moderate_risk": 1, "concern": 2, "neutral": 3, "positive": 4}
    findings.sort(key=lambda f: severity_order.get(f.severity, 3))

    return findings


def _portfolio_findings(
    ei: BureauExecutiveSummaryInputs,
    vectors: Dict[LoanType, BureauLoanFeatureVector],
) -> List[KeyFinding]:
    """Extract findings from portfolio-level data."""
    findings = []

    # Delinquency flag — find timeline of loan type with max DPD
    dpd_timeline = ""
    if ei.max_dpd_loan_type:
        for lt, vec in vectors.items():
            if get_loan_type_display_name(lt) == ei.max_dpd_loan_type:
                tl = _timeline_str(vec)
                if tl:
                    dpd_timeline = f" [{ei.max_dpd_loan_type}: {tl}]"
                break

    if ei.has_delinquency:
        if ei.max_dpd is not None and ei.max_dpd > T.DPD_HIGH_RISK:
            findings.append(KeyFinding(
                category="Delinquency",
                finding=f"Active delinquency detected with Max DPD of {ei.max_dpd} days{dpd_timeline}",
                inference="Severe delinquency indicates significant repayment stress; loan may be classified as NPA",
                severity="high_risk",
            ))
        elif ei.max_dpd is not None and ei.max_dpd > T.DPD_MODERATE_RISK:
            findings.append(KeyFinding(
                category="Delinquency",
                finding=f"Active delinquency detected with Max DPD of {ei.max_dpd} days{dpd_timeline}",
                inference="Significant past-due status suggests repayment difficulty; close monitoring required",
                severity="moderate_risk",
            ))
        elif ei.max_dpd is not None and ei.max_dpd > 0:
            findings.append(KeyFinding(
                category="Delinquency",
                finding=f"Minor delinquency detected with Max DPD of {ei.max_dpd} days{dpd_timeline}",
                inference="Early-stage past-due status; may reflect temporary cash flow mismatch",
                severity="concern",
            ))
    else:
        findings.append(KeyFinding(
            category="Delinquency",
            finding="No delinquency detected across the portfolio",
            inference="Clean delinquency record is a positive indicator for repayment discipline",
            severity="positive",
        ))

    # Unsecured sanction proportion
    if ei.total_sanctioned > 0:
        unsecured_pct = (ei.unsecured_sanctioned / ei.total_sanctioned) * 100
        if unsecured_pct > T.UNSECURED_PCT_MODERATE_RISK:
            findings.append(KeyFinding(
                category="Portfolio",
                finding=f"Unsecured sanction is {unsecured_pct:.0f}% of total (INR {format_inr(ei.unsecured_sanctioned)} of INR {format_inr(ei.total_sanctioned)})",
                inference="Heavily skewed towards unsecured lending; higher risk in absence of collateral",
                severity="moderate_risk",
            ))
        elif unsecured_pct > T.UNSECURED_PCT_CONCERN:
            findings.append(KeyFinding(
                category="Portfolio",
                finding=f"Unsecured sanction is {unsecured_pct:.0f}% of total (INR {format_inr(ei.unsecured_sanctioned)} of INR {format_inr(ei.total_sanctioned)})",
                inference="Majority unsecured portfolio; monitor for over-leveraging on unsecured products",
                severity="concern",
            ))

    # Outstanding as % of sanctioned
    if ei.total_sanctioned > 0:
        outstanding_pct = (ei.total_outstanding / ei.total_sanctioned) * 100
        if outstanding_pct > T.OUTSTANDING_PCT_CONCERN:
            findings.append(KeyFinding(
                category="Portfolio",
                finding=f"Outstanding balance is {outstanding_pct:.0f}% of total sanctioned amount",
                inference="Most sanctioned amount still outstanding; limited repayment progress on existing obligations",
                severity="concern",
            ))

    # Product diversity
    product_count = len(vectors)
    if product_count >= T.PRODUCT_DIVERSITY_NEUTRAL:
        product_names = ", ".join(get_loan_type_display_name(lt) for lt in vectors)
        findings.append(KeyFinding(
            category="Portfolio",
            finding=f"Portfolio spans {product_count} loan products ({product_names})",
            inference="Diversified credit portfolio indicates established borrowing history across products",
            severity="neutral",
        ))

    return findings


def _loan_type_findings(
    vectors: Dict[LoanType, BureauLoanFeatureVector],
) -> List[KeyFinding]:
    """Extract findings from per-loan-type feature vectors."""
    findings = []

    for loan_type, vec in vectors.items():
        lt_name = get_loan_type_display_name(loan_type)
        tl = _timeline_str(vec)
        tl_suffix = f" [{tl}]" if tl else ""

        # CC utilization (utilization_ratio is stored as 0-1; convert to %)
        if loan_type == LoanType.CC and vec.utilization_ratio is not None:
            util = vec.utilization_ratio * 100
            if util > T.CC_UTIL_HIGH_RISK:
                findings.append(KeyFinding(
                    category="Utilization",
                    finding=f"Credit card utilization at {util:.0f}%{tl_suffix}",
                    inference="Over-utilization of credit card limits signals high credit dependency and potential cash flow stress",
                    severity="high_risk",
                ))
            elif util > T.CC_UTIL_MODERATE_RISK:
                findings.append(KeyFinding(
                    category="Utilization",
                    finding=f"Credit card utilization at {util:.0f}%{tl_suffix}",
                    inference="Elevated utilization; approaching high-risk threshold for revolving credit",
                    severity="moderate_risk",
                ))
            elif util <= T.CC_UTIL_HEALTHY:
                findings.append(KeyFinding(
                    category="Utilization",
                    finding=f"Credit card utilization at {util:.0f}%{tl_suffix}",
                    inference="Healthy utilization indicates disciplined credit card usage",
                    severity="positive",
                ))

        # Per-type delinquency
        if vec.delinquency_flag and vec.max_dpd is not None and vec.max_dpd > 0:
            if vec.max_dpd > T.DPD_HIGH_RISK:
                findings.append(KeyFinding(
                    category="Delinquency",
                    finding=f"{lt_name}: Delinquent with Max DPD of {vec.max_dpd} days{tl_suffix}",
                    inference=f"Severe delinquency on {lt_name} account; may indicate deep financial distress",
                    severity="high_risk",
                ))
            elif vec.max_dpd > T.DPD_MODERATE_RISK:
                findings.append(KeyFinding(
                    category="Delinquency",
                    finding=f"{lt_name}: Delinquent with Max DPD of {vec.max_dpd} days{tl_suffix}",
                    inference=f"Significant past-due on {lt_name}; repayment discipline is compromised",
                    severity="moderate_risk",
                ))

        # Overdue amount
        if vec.overdue_amount > 0:
            findings.append(KeyFinding(
                category="Outstanding",
                finding=f"{lt_name}: Overdue amount of INR {format_inr(vec.overdue_amount)}{tl_suffix}",
                inference=f"Active overdue balance on {lt_name} indicates unresolved payment obligation",
                severity="concern",
            ))

        # Forced events (write-off, settlement, etc.)
        if vec.forced_event_flags:
            events = ", ".join(vec.forced_event_flags)
            findings.append(KeyFinding(
                category="Adverse Events",
                finding=f"{lt_name}: Forced events detected — {events}{tl_suffix}",
                inference=f"Adverse credit events on {lt_name} are strong negative signals for creditworthiness",
                severity="high_risk",
            ))

    return findings


def _tradeline_findings(
    tf: TradelineFeatures,
    vectors: Optional[Dict[LoanType, BureauLoanFeatureVector]] = None,
) -> List[KeyFinding]:
    """Extract findings from pre-computed tradeline features."""
    findings = []

    # Helper to look up timeline for CC or PL from vectors
    def _lt_timeline(lt: LoanType) -> str:
        if vectors and lt in vectors:
            tl = _timeline_str(vectors[lt])
            return f" [{tl}]" if tl else ""
        return ""

    pl_tl = _lt_timeline(LoanType.PL)

    # --- Loan Activity ---
    if tf.new_trades_6m_pl is not None:
        if tf.new_trades_6m_pl >= T.NEW_PL_6M_HIGH_RISK:
            findings.append(KeyFinding(
                category="Loan Activity",
                finding=f"{tf.new_trades_6m_pl} new personal loan trades opened in last 6 months{pl_tl}",
                inference="Rapid PL acquisition suggests urgent credit need or loan stacking behavior",
                severity="high_risk",
            ))
        elif tf.new_trades_6m_pl >= T.NEW_PL_6M_MODERATE_RISK:
            findings.append(KeyFinding(
                category="Loan Activity",
                finding=f"{tf.new_trades_6m_pl} new personal loan trades opened in last 6 months{pl_tl}",
                inference="Multiple recent PL acquisitions; monitor for emerging over-leverage",
                severity="moderate_risk",
            ))

    if tf.months_since_last_trade_pl is not None and tf.months_since_last_trade_pl < T.MONTHS_SINCE_TRADE_CONCERN:
        findings.append(KeyFinding(
            category="Loan Activity",
            finding=f"Last PL trade opened {tf.months_since_last_trade_pl:.1f} months ago{pl_tl}",
            inference="Very recent PL activity indicates active credit seeking",
            severity="concern",
        ))

    # --- DPD & Delinquency ---
    # Map field name to (label, LoanType) for timeline lookup
    dpd_field_map = [
        ("max_dpd_6m_cc", "Credit Card (6M)", LoanType.CC),
        ("max_dpd_6m_pl", "Personal Loan (6M)", LoanType.PL),
        ("max_dpd_9m_cc", "Credit Card (9M)", LoanType.CC),
    ]
    for field_name, label, lt in dpd_field_map:
        val = getattr(tf, field_name, None)
        lt_tl = _lt_timeline(lt)
        if val is not None and val > 0:
            if val > T.DPD_HIGH_RISK:
                findings.append(KeyFinding(
                    category="DPD & Delinquency",
                    finding=f"Max DPD for {label}: {val} days{lt_tl}",
                    inference=f"Severe delinquency on {label} — strong negative indicator",
                    severity="high_risk",
                ))
            elif val > T.DPD_MODERATE_RISK:
                findings.append(KeyFinding(
                    category="DPD & Delinquency",
                    finding=f"Max DPD for {label}: {val} days{lt_tl}",
                    inference=f"Significant past-due on {label}; repayment under stress",
                    severity="moderate_risk",
                ))
            else:
                findings.append(KeyFinding(
                    category="DPD & Delinquency",
                    finding=f"Max DPD for {label}: {val} days{lt_tl}",
                    inference=f"Minor past-due on {label}; may be a temporary delay",
                    severity="concern",
                ))

    # Clean DPD check (all zero)
    dpd_fields = [tf.max_dpd_6m_cc, tf.max_dpd_6m_pl, tf.max_dpd_9m_cc]
    if all(v is not None and v == 0 for v in dpd_fields):
        findings.append(KeyFinding(
            category="DPD & Delinquency",
            finding="Zero DPD across all products in recent 6-9 month windows",
            inference="Clean recent payment record demonstrates consistent repayment discipline",
            severity="positive",
        ))

    # --- Payment Behavior ---
    if tf.pct_missed_payments_18m is not None:
        if tf.pct_missed_payments_18m > T.MISSED_PAYMENTS_HIGH_RISK:
            findings.append(KeyFinding(
                category="Payment Behavior",
                finding=f"{tf.pct_missed_payments_18m:.1f}% missed payments in last 18 months",
                inference="Frequent missed payments indicate chronic repayment stress",
                severity="high_risk",
            ))
        elif tf.pct_missed_payments_18m > 0:
            findings.append(KeyFinding(
                category="Payment Behavior",
                finding=f"{tf.pct_missed_payments_18m:.1f}% missed payments in last 18 months",
                inference="Some missed payments detected; not habitual but warrants attention",
                severity="concern",
            ))
        else:
            # 0% missed payments — but cross-check against DPD fields
            has_dpd = any(
                getattr(tf, f, None) is not None and getattr(tf, f) > 0
                for f in ["max_dpd_6m_cc", "max_dpd_6m_pl", "max_dpd_9m_cc"]
            )
            if has_dpd:
                findings.append(KeyFinding(
                    category="Payment Behavior",
                    finding="No formal missed payments in last 18 months, but DPD delays detected on some products",
                    inference="Payments were eventually made but past due date; payment timing discipline is not fully clean",
                    severity="concern",
                ))
            else:
                findings.append(KeyFinding(
                    category="Payment Behavior",
                    finding="No missed payments in last 18 months",
                    inference="Perfect payment track record over 18 months is a strong positive",
                    severity="positive",
                ))

    if tf.ratio_good_closed_pl is not None:
        if tf.ratio_good_closed_pl >= T.GOOD_CLOSURE_POSITIVE:
            findings.append(KeyFinding(
                category="Payment Behavior",
                finding=f"Good closure ratio for PL loans: {tf.ratio_good_closed_pl:.0%}",
                inference="Strong track record of closing personal loans in good standing",
                severity="positive",
            ))
        elif tf.ratio_good_closed_pl < T.GOOD_CLOSURE_HIGH_RISK:
            findings.append(KeyFinding(
                category="Payment Behavior",
                finding=f"Good closure ratio for PL loans: {tf.ratio_good_closed_pl:.0%}",
                inference="Poor PL closure history — majority of closed PLs had issues",
                severity="high_risk",
            ))
        elif tf.ratio_good_closed_pl < T.GOOD_CLOSURE_CONCERN:
            findings.append(KeyFinding(
                category="Payment Behavior",
                finding=f"Good closure ratio for PL loans: {tf.ratio_good_closed_pl:.0%}",
                inference="Below-average PL closure quality; some loans closed with problems",
                severity="concern",
            ))

    # --- Utilization ---
    # CC utilization is already covered by _loan_type_findings (from feature vectors)

    if tf.pl_balance_remaining_pct is not None:
        if tf.pl_balance_remaining_pct > T.PL_BAL_REMAINING_HIGH_RISK:
            findings.append(KeyFinding(
                category="Utilization",
                finding=f"PL balance remaining: {tf.pl_balance_remaining_pct:.1f}%",
                inference="Most PL sanctioned amount still outstanding; limited principal repayment progress",
                severity="high_risk",
            ))
        elif tf.pl_balance_remaining_pct <= T.PL_BAL_REMAINING_POSITIVE:
            findings.append(KeyFinding(
                category="Utilization",
                finding=f"PL balance remaining: {tf.pl_balance_remaining_pct:.1f}%",
                inference="Significant PL principal already repaid; good repayment progress",
                severity="positive",
            ))

    # --- Enquiry Behavior ---
    if tf.unsecured_enquiries_12m is not None:
        if tf.unsecured_enquiries_12m > T.ENQUIRY_HIGH_RISK:
            findings.append(KeyFinding(
                category="Enquiry Behavior",
                finding=f"{tf.unsecured_enquiries_12m} unsecured enquiries in last 12 months",
                inference="Very high enquiry pressure suggests desperate credit seeking or multiple rejections",
                severity="high_risk",
            ))
        elif tf.unsecured_enquiries_12m > T.ENQUIRY_MODERATE_RISK:
            findings.append(KeyFinding(
                category="Enquiry Behavior",
                finding=f"{tf.unsecured_enquiries_12m} unsecured enquiries in last 12 months",
                inference="Elevated enquiry activity; may indicate difficulty securing credit",
                severity="moderate_risk",
            ))
        elif tf.unsecured_enquiries_12m <= T.ENQUIRY_HEALTHY:
            findings.append(KeyFinding(
                category="Enquiry Behavior",
                finding=f"{tf.unsecured_enquiries_12m} unsecured enquiries in last 12 months",
                inference="Minimal enquiry activity indicates stable credit position",
                severity="positive",
            ))

    if tf.trade_to_enquiry_ratio_uns_24m is not None:
        if tf.trade_to_enquiry_ratio_uns_24m < T.TRADE_RATIO_CONCERN:
            findings.append(KeyFinding(
                category="Enquiry Behavior",
                finding=f"Trade-to-enquiry ratio (unsecured, 24M): {tf.trade_to_enquiry_ratio_uns_24m:.1f}%",
                inference="Low conversion from enquiries to actual loans suggests possible rejections by lenders",
                severity="concern",
            ))
        elif tf.trade_to_enquiry_ratio_uns_24m > T.TRADE_RATIO_POSITIVE:
            findings.append(KeyFinding(
                category="Enquiry Behavior",
                finding=f"Trade-to-enquiry ratio (unsecured, 24M): {tf.trade_to_enquiry_ratio_uns_24m:.1f}%",
                inference="High conversion rate indicates strong acceptance by lenders",
                severity="positive",
            ))

    # --- Loan Acquisition Velocity ---
    if tf.interpurchase_time_12m_plbl is not None:
        if tf.interpurchase_time_12m_plbl < T.IPT_HIGH_RISK:
            findings.append(KeyFinding(
                category="Loan Velocity",
                finding=f"Avg time between PL/BL acquisitions (12M): {tf.interpurchase_time_12m_plbl:.1f} months",
                inference="Rapid loan stacking — acquiring unsecured loans faster than monthly; high risk of over-leverage",
                severity="high_risk",
            ))
        elif tf.interpurchase_time_12m_plbl < T.IPT_CONCERN:
            findings.append(KeyFinding(
                category="Loan Velocity",
                finding=f"Avg time between PL/BL acquisitions (12M): {tf.interpurchase_time_12m_plbl:.1f} months",
                inference="Frequent loan acquisitions; borrower is actively accumulating unsecured debt",
                severity="concern",
            ))
        elif tf.interpurchase_time_12m_plbl >= T.IPT_HEALTHY:
            findings.append(KeyFinding(
                category="Loan Velocity",
                finding=f"Avg time between PL/BL acquisitions (12M): {tf.interpurchase_time_12m_plbl:.1f} months",
                inference="Measured pace of loan acquisitions indicates no urgency or stacking behavior",
                severity="positive",
            ))

    return findings


def _composite_findings(
    ei: BureauExecutiveSummaryInputs,
    tf: TradelineFeatures,
    vectors: Optional[Dict[LoanType, BureauLoanFeatureVector]] = None,
) -> List[KeyFinding]:
    """Extract findings from feature interactions (multi-feature signals)."""
    findings = []

    # Timeline helpers
    def _lt_timeline(lt: LoanType) -> str:
        if vectors and lt in vectors:
            tl = _timeline_str(vectors[lt])
            return f" [{tl}]" if tl else ""
        return ""

    pl_tl = _lt_timeline(LoanType.PL)
    cc_tl = _lt_timeline(LoanType.CC)

    enquiries = tf.unsecured_enquiries_12m
    new_pl_6m = tf.new_trades_6m_pl
    ipt_plbl = tf.interpurchase_time_12m_plbl

    # Credit hungry + loan stacking
    if enquiries is not None and enquiries > T.COMPOSITE_ENQUIRY_THRESHOLD and new_pl_6m is not None and new_pl_6m >= T.COMPOSITE_NEW_PL_TRIGGER:
        findings.append(KeyFinding(
            category="Composite Signal",
            finding=f"High enquiry volume ({enquiries} in 12M) combined with {new_pl_6m} new PL trades in 6M{pl_tl}",
            inference="Credit hungry behavior with active loan stacking — elevated risk of debt spiral",
            severity="high_risk",
        ))

    # Rapid stacking with low interpurchase time
    if ipt_plbl is not None and ipt_plbl < T.IPT_CONCERN and new_pl_6m is not None and new_pl_6m >= T.COMPOSITE_NEW_PL_TRIGGER:
        findings.append(KeyFinding(
            category="Composite Signal",
            finding=f"Avg {ipt_plbl:.1f} months between PL/BL with {new_pl_6m} new trades in 6M{pl_tl}",
            inference="Rapid PL stacking pattern — borrower is accumulating unsecured debt at an accelerating pace",
            severity="high_risk",
        ))

    # High utilization + high outstanding
    cc_util = tf.cc_balance_utilization_pct
    pl_bal = tf.pl_balance_remaining_pct
    if cc_util is not None and cc_util > T.COMPOSITE_UTIL_LEVERAGE and pl_bal is not None and pl_bal > T.COMPOSITE_BAL_LEVERAGE:
        findings.append(KeyFinding(
            category="Composite Signal",
            finding=f"CC utilization at {cc_util:.1f}%{cc_tl} and PL balance remaining at {pl_bal:.1f}%{pl_tl}",
            inference="Elevated leverage across both revolving and term products; limited debt servicing headroom",
            severity="moderate_risk",
        ))

    # High enquiries + low conversion
    trade_ratio = tf.trade_to_enquiry_ratio_uns_24m
    if enquiries is not None and enquiries > T.COMPOSITE_ENQUIRY_THRESHOLD and trade_ratio is not None and trade_ratio < T.COMPOSITE_TRADE_RATIO_LOW:
        findings.append(KeyFinding(
            category="Composite Signal",
            finding=f"High enquiries ({enquiries}) but only {trade_ratio:.1f}% trade-to-enquiry conversion",
            inference="Low conversion rate despite high enquiry volume suggests multiple lender rejections",
            severity="moderate_risk",
        ))

    # Clean profile composite
    dpd_clean = all(
        getattr(tf, f, None) is not None and getattr(tf, f) == 0
        for f in ["max_dpd_6m_cc", "max_dpd_6m_pl", "max_dpd_9m_cc"]
    )
    missed_clean = tf.pct_missed_payments_18m is not None and tf.pct_missed_payments_18m == 0
    good_ratio = tf.ratio_good_closed_pl
    if dpd_clean and missed_clean and good_ratio is not None and good_ratio >= T.GOOD_CLOSURE_POSITIVE:
        findings.append(KeyFinding(
            category="Composite Signal",
            finding=f"Zero DPD, no missed payments, and {good_ratio:.0%} good PL closure ratio",
            inference="Exemplary repayment profile — strong candidate from a credit discipline standpoint",
            severity="positive",
        ))

    # Missed payments = 0 but DPD detected (from tl_features or portfolio-level)
    has_tf_dpd = not dpd_clean
    has_portfolio_dpd = ei.has_delinquency and ei.max_dpd is not None and ei.max_dpd > 0
    if missed_clean and (has_tf_dpd or has_portfolio_dpd):
        dpd_details = []
        if tf.max_dpd_6m_cc is not None and tf.max_dpd_6m_cc > 0:
            dpd_details.append(f"CC 6M: {tf.max_dpd_6m_cc} days")
        if tf.max_dpd_6m_pl is not None and tf.max_dpd_6m_pl > 0:
            dpd_details.append(f"PL 6M: {tf.max_dpd_6m_pl} days")
        if tf.max_dpd_9m_cc is not None and tf.max_dpd_9m_cc > 0:
            dpd_details.append(f"CC 9M: {tf.max_dpd_9m_cc} days")
        if has_portfolio_dpd and not dpd_details:
            dpd_details.append(f"Portfolio Max DPD: {ei.max_dpd} days")
        if dpd_details:
            findings.append(KeyFinding(
                category="Composite Signal",
                finding=f"No formal missed payments but DPD detected ({', '.join(dpd_details)})",
                inference="Payments were made but with delays past due date; payment discipline is inconsistent despite no formal defaults",
                severity="concern",
            ))

    return findings


def findings_to_dicts(findings: List[KeyFinding]) -> List[Dict]:
    """Convert KeyFinding list to list of dicts for serialization."""
    return [asdict(f) for f in findings]
