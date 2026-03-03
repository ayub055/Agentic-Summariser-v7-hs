"""Scorecard computation — one-page risk verdict for all report types.

Computes a structured scorecard dict from CustomerReport and/or BureauReport.
No LLM calls — pure deterministic threshold logic using config/thresholds.py.

The scorecard contains:
  - verdict:     "LOW RISK" / "CAUTION" / "HIGH RISK"
  - verdict_rag: "green" / "amber" / "red"
  - signals:     list of RAG-tagged metric chips
  - strengths:   up to 3 positive findings
  - concerns:    up to 3 risk findings
  - verify:      items to cross-check
  - narrative:   LLM summary text (injected by caller)
"""

import logging
from typing import Optional
from utils.helpers import format_inr

import config.thresholds as T

logger = logging.getLogger(__name__)

_ADVERSE_HIGH = {"WRF", "SET", "SMA"}
_ADVERSE_MODERATE = {"SUB", "DBT", "LSS", "WOF"}


def _rag(value, green_max=None, amber_max=None, green_min=None, amber_min=None,
         invert=False):
    """Return 'green' / 'amber' / 'red' for a numeric value.

    Two modes:
      Lower-is-better (invert=False, default):
        value <= green_max → green, <= amber_max → amber, else red
      Higher-is-better (invert=True):
        value >= green_min → green, >= amber_min → amber, else red
    """
    if value is None:
        return "neutral"
    if not invert:
        if green_max is not None and value <= green_max:
            return "green"
        if amber_max is not None and value <= amber_max:
            return "amber"
        return "red"
    else:
        if green_min is not None and value >= green_min:
            return "green"
        if amber_min is not None and value >= amber_min:
            return "amber"
        return "red"


def _bureau_signals(bureau_report) -> list:
    """Compute bureau risk signals from BureauReport."""
    signals = []
    ei = bureau_report.executive_inputs
    tl = bureau_report.tradeline_features

    # 1. Max DPD
    dpd = ei.max_dpd
    if dpd is not None:
        rag = _rag(dpd, green_max=0, amber_max=T.DPD_MODERATE_RISK)
        note_parts = []
        if ei.max_dpd_loan_type:
            note_parts.append(ei.max_dpd_loan_type)
        if ei.max_dpd_months_ago is not None:
            note_parts.append(f"{ei.max_dpd_months_ago}M ago")
        note = ", ".join(note_parts) if note_parts else ("Clean" if dpd == 0 else "Delinquent")
        signals.append({"label": "Max DPD", "value": f"{dpd} days", "rag": rag, "note": note})

    # 2. CC Utilization
    if tl and tl.cc_balance_utilization_pct is not None:
        util = tl.cc_balance_utilization_pct
        rag = _rag(util, green_max=T.CC_UTIL_HEALTHY, amber_max=T.CC_UTIL_HIGH_RISK)
        label_note = "Over-utilized" if util > T.CC_UTIL_HIGH_RISK else (
            "Elevated" if util > T.CC_UTIL_MODERATE_RISK else "Healthy"
        )
        signals.append({"label": "CC Util", "value": f"{util:.0f}%", "rag": rag, "note": label_note})

    # 3. Enquiry Pressure
    if tl and tl.unsecured_enquiries_12m is not None:
        enq = tl.unsecured_enquiries_12m
        rag = _rag(enq, green_max=T.ENQUIRY_HEALTHY, amber_max=T.ENQUIRY_MODERATE_RISK)
        note = "High pressure" if enq > T.ENQUIRY_MODERATE_RISK else (
            "Moderate" if enq > T.ENQUIRY_HEALTHY else "Minimal"
        )
        signals.append({"label": "Enquiries", "value": f"{enq} in 12M", "rag": rag, "note": note})

    # 4. Loan Stacking (new PLs in 6M)
    if tl and tl.new_trades_6m_pl is not None:
        new_pl = tl.new_trades_6m_pl
        rag = _rag(new_pl, green_max=0, amber_max=T.NEW_PL_6M_MODERATE_RISK - 1)
        note = "Rapid stacking" if new_pl >= T.NEW_PL_6M_HIGH_RISK else (
            "Multiple" if new_pl >= T.NEW_PL_6M_MODERATE_RISK else ("1 new PL" if new_pl == 1 else "None")
        )
        signals.append({"label": "Loan Stack", "value": f"{new_pl} new PLs", "rag": rag, "note": "6M window"})

    # 5. Missed Payments
    if tl and tl.pct_missed_payments_18m is not None:
        missed = tl.pct_missed_payments_18m
        rag = _rag(missed, green_max=0, amber_max=T.MISSED_PAYMENTS_HIGH_RISK)
        note = "Frequent missed" if missed > T.MISSED_PAYMENTS_HIGH_RISK else (
            "Some missed" if missed > 0 else "None missed"
        )
        signals.append({"label": "Payments", "value": f"{missed:.0f}% missed", "rag": rag, "note": "18M window"})

    # 6. Adverse Events (forced event flags across all loan type vectors)
    all_flags = []
    for vec in bureau_report.feature_vectors.values():
        all_flags.extend(vec.forced_event_flags or [])
    if all_flags:
        high_adv = [f for f in all_flags if f in _ADVERSE_HIGH]
        mod_adv = [f for f in all_flags if f in _ADVERSE_MODERATE]
        unique_flags = sorted(set(all_flags))
        rag = "red" if high_adv else ("amber" if mod_adv else "neutral")
        signals.append({
            "label": "Adverse Events",
            "value": ", ".join(unique_flags[:3]),
            "rag": rag,
            "note": "Forced events detected"
        })

    return signals


def _banking_signals(customer_report, rg_salary_data: dict = None) -> list:
    """Compute banking risk signals from CustomerReport."""
    signals = []
    rg_salary_data = rg_salary_data or {}

    # 7. Income / Salary — prefer rg_salary_data (authoritative algorithm), fall back to report.salary
    rg_sal = rg_salary_data.get("rg_sal")

    if rg_sal:
        # Primary salary detected by internal algorithm
        amt = rg_sal.get("salary_amount") or 0
        n = rg_sal.get("transaction_count") or 1
        merchant = rg_sal.get("merchant", "")
        rag = "green" if n >= 3 else "amber"
        note = f"{merchant}" if merchant else ("Consistent" if rag == "green" else "Irregular")
        signals.append({
            "label": "Income",
            "value": f"INR {format_inr(amt)} /mo",
            "rag": rag,
            "note": note,
        })
    elif customer_report.salary:
        avg = customer_report.salary.avg_amount
        freq = customer_report.salary.frequency
        rag = "green" if freq >= 3 else "amber"
        signals.append({
            "label": "Income",
            "value": f"INR {format_inr(avg)} avg",
            "rag": rag,
            "note": "Consistent" if rag == "green" else "Irregular",
        })
    else:
        signals.append({"label": "Income", "value": "Not detected", "rag": "red", "note": "No salary found"})

    # 8. FOIR (Fixed Obligation to Income Ratio)
    _salary_for_foir = (rg_sal.get("salary_amount") if rg_sal else None) or (
        customer_report.salary.avg_amount if customer_report.salary else None
    )
    if _salary_for_foir and _salary_for_foir > 0:
        salary = _salary_for_foir
        emi_total = sum(e.amount for e in customer_report.emis) if customer_report.emis else 0
        rent_amt = customer_report.rent.amount if customer_report.rent else 0
        foir = (emi_total + rent_amt) / salary * 100
        rag = _rag(foir, green_max=40, amber_max=65)
        signals.append({
            "label": "FOIR",
            "value": f"{foir:.0f}%",
            "rag": rag,
            "note": "EMI+Rent/Salary"
        })

    # 9. Red Flag Spending
    betting = 0.0
    if customer_report.category_overview:
        for key in ("Digital_Betting_Gaming", "Betting_Gaming", "Betting", "Gaming"):
            if key in customer_report.category_overview:
                betting = customer_report.category_overview[key]
                break
    if betting > 0:
        rag = "red" if betting >= 500 else "amber"
        signals.append({
            "label": "Red Flags",
            "value": f"INR {format_inr(betting)}",
            "rag": rag,
            "note": "Betting/Gaming detected"
        })
    else:
        signals.append({"label": "Red Flags", "value": "None", "rag": "green", "note": "No flag categories"})

    # 10. Account Type (from account_quality)
    if customer_report.account_quality:
        aq           = customer_report.account_quality
        account_type = aq.get("account_type", "unknown")
        score        = aq.get("primary_score", 50)
        rag_map      = {"primary": "green", "secondary": "amber", "conduit": "red", "unknown": "neutral"}
        rag          = rag_map.get(account_type, "neutral")
        signals.append({
            "label": "Account Type",
            "value": account_type.title(),
            "rag":   rag,
            "note":  f"Score {score}/100",
        })

    return signals


def _derive_strengths_concerns(bureau_report, signals: list) -> tuple:
    """Derive strengths, concerns, verify from key_findings + signal list."""
    strengths, concerns, verify = [], [], []

    # From key findings (bureau)
    if bureau_report and bureau_report.key_findings:
        for f in bureau_report.key_findings:
            if f.severity == "positive" and len(strengths) < 3:
                strengths.append(f.finding)
            elif f.severity in ("high_risk", "moderate_risk") and len(concerns) < 3:
                concerns.append(f.finding)

    # From signal list (banking signals where key_findings not available)
    if not concerns:
        for s in signals:
            if s["rag"] == "red" and len(concerns) < 3:
                concerns.append(f"{s['label']}: {s['value']} ({s['note']})")
    if not strengths:
        for s in signals:
            if s["rag"] == "green" and len(strengths) < 3:
                strengths.append(f"{s['label']}: {s['value']}")

    # Verify items
    # Check FOIR signal
    for s in signals:
        if s["label"] == "FOIR" and s["rag"] in ("amber", "red"):
            verify.append("Cross-verify declared income vs salary deposits")
            break

    # EMI mismatch check
    if bureau_report and bureau_report.executive_inputs:
        live = bureau_report.executive_inputs.live_tradelines or 0
        # Count EMIs from banking if available
        if hasattr(bureau_report, "_banking_emi_count"):
            banking_emis = bureau_report._banking_emi_count
        else:
            banking_emis = None
        if live > 3 and banking_emis is not None and banking_emis < live - 1:
            verify.append(f"EMI mismatch: {live} live bureau tradelines vs {banking_emis} EMIs in banking")
        elif live > 4:
            verify.append(f"Verify all {live} live tradelines are reflected in banking obligations")

    # Forced events
    if bureau_report:
        all_flags = []
        for vec in bureau_report.feature_vectors.values():
            all_flags.extend(vec.forced_event_flags or [])
        high_adv = [f for f in all_flags if f in _ADVERSE_HIGH]
        if high_adv:
            verify.append(f"Resolve adverse event status: {', '.join(sorted(set(high_adv)))}")

    if not verify:
        verify.append("Confirm income source from employer or IT returns")

    return strengths[:3], concerns[:3], verify[:3]


def compute_scorecard(customer_report=None, bureau_report=None, rg_salary_data: dict = None) -> dict:
    """Compute a structured risk scorecard from available report data.

    Args:
        customer_report: CustomerReport or None
        bureau_report:   BureauReport or None

    Returns:
        dict with keys: verdict, verdict_rag, signals, strengths, concerns, verify, narrative
    """
    signals = []

    try:
        if bureau_report:
            signals.extend(_bureau_signals(bureau_report))
    except Exception as e:
        logger.warning("Bureau signal computation failed: %s", e)

    try:
        if customer_report:
            signals.extend(_banking_signals(customer_report, rg_salary_data=rg_salary_data))
    except Exception as e:
        logger.warning("Banking signal computation failed: %s", e)

    # Verdict from RED count
    red_count = sum(1 for s in signals if s["rag"] == "red")

    # Override: forced adverse events → always HIGH RISK
    forced_high = False
    if bureau_report:
        for vec in bureau_report.feature_vectors.values():
            if any(f in _ADVERSE_HIGH for f in (vec.forced_event_flags or [])):
                forced_high = True
                break

    if forced_high or red_count >= 3:
        verdict, verdict_rag = "HIGH RISK", "red"
    elif red_count >= 1:
        verdict, verdict_rag = "CAUTION", "amber"
    else:
        verdict, verdict_rag = "LOW RISK", "green"

    strengths, concerns, verify = _derive_strengths_concerns(bureau_report, signals)

    # Narrative: bureau narrative only. combined_summary injected by combined renderer.
    # customer_review is NOT included — it already appears as a separate section in the report.
    narrative = ""
    if bureau_report and bureau_report.narrative:
        narrative = bureau_report.narrative

    return {
        "verdict": verdict,
        "verdict_rag": verdict_rag,
        "signals": signals,
        "strengths": strengths,
        "concerns": concerns,
        "verify": verify,
        "narrative": narrative,
    }
