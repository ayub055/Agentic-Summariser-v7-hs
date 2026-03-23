# Policy-Based Loan Offer Judgment — Implementation Plan

> **Classification:** Architecture Extension Plan
> **Scope:** Add policy evaluation layer to judge loan offer justification
> **Principle:** Deterministic policy rules, LLM only for narration — same as existing system
> **Author:** Staff Engineering Review

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [What We Already Have](#2-what-we-already-have)
3. [Implementation Tiers](#3-implementation-tiers)
4. [Tier 1 — Deterministic Policy Engine (POC)](#4-tier-1--deterministic-policy-engine-poc)
5. [Tier 2 — LLM-Assisted Policy Interpretation](#5-tier-2--llm-assisted-policy-interpretation)
6. [Tier 3 — RAG Policy Engine + Batch Pipeline](#6-tier-3--rag-policy-engine--batch-pipeline)
7. [Batch Processing Architecture](#7-batch-processing-architecture)
8. [Schema Design](#8-schema-design)
9. [File Structure & Module Placement](#9-file-structure--module-placement)
10. [Implementation Steps](#10-implementation-steps)
11. [Examples — Before and After](#11-examples--before-and-after)
12. [Architecture Decision Records](#12-architecture-decision-records)

---

## 1. Problem Statement

### The Input

1. **Policy Document** — A set of rules (internal credit policy) that define what loan offer parameters (amount, rate, tenure, product type) are appropriate for a customer given their financial profile.
2. **Customer Summary** — The system already generates rich structured data: `CustomerReport`, `BureauReport`, `KeyFindings`, `Scorecard`, and LLM narratives.
3. **Loan Offer** — The actual offer extended to the customer (amount, rate, tenure, product, conditions).

### The Output

A **Judgment** — was this offer justified given the policy? Specifically:

```
PolicyJudgment
├── verdict: "JUSTIFIED" | "UNJUSTIFIED" | "PARTIALLY_JUSTIFIED" | "INSUFFICIENT_DATA"
├── offer_vs_policy: [{rule_id, rule_text, customer_value, policy_threshold, pass/fail}]
├── risk_flags_missed: [flags the offer should have considered but didn't]
├── risk_flags_addressed: [flags the offer correctly accounted for]
├── recommended_adjustments: [{parameter, current_value, suggested_value, reason}]
├── confidence: float (0-1)
└── narrative: str (LLM-generated justification summary)
```

### Key Constraints

- **Batch scale:** Must evaluate 100s–1000s of offers in a single run
- **Auditability:** Every judgment must trace back to specific policy rules and data points
- **Deterministic core:** Policy rule evaluation must be pure Python — LLM only for narrative
- **Existing structure:** Fits into the current module layout, reuses existing schemas and tools

---

## 2. What We Already Have

The existing system provides **90% of the data infrastructure** needed. The gap is only the policy evaluation layer.

### Available Structured Data (Per Customer)

| Source | Key Fields for Policy Evaluation |
|---|---|
| `CustomerReport.salary` | `avg_amount`, `frequency` — income verification |
| `CustomerReport.savings` | `savings_rate`, `net_savings` — repayment capacity |
| `CustomerReport.emis` | EMI obligations — existing debt burden |
| `CustomerReport.rent` | Rent obligations — fixed outflows |
| `CustomerReport.monthly_cashflow` | Monthly `inflow`, `outflow`, `net` — stability |
| `CustomerReport.risk_indicators` | `income_stability_score`, `risk_level`, `risk_flags` |
| `CustomerReport.account_quality` | Primary/conduit classification — account legitimacy |
| `CustomerReport.events` | Semantic events (PF withdrawal, betting, loan redistribution) |
| `BureauReport.executive_inputs` | `total_tradelines`, `max_dpd`, `has_delinquency`, `tu_score` |
| `BureauReport.feature_vectors` | Per-loan-type: sanctioned, outstanding, DPD, utilization |
| `TradelineFeatures` | `foir`, `foir_unsec`, `aff_emi`, `unsecured_enquiries_12m`, `new_trades_6m_pl`, `cc_balance_utilization_pct`, `interpurchase_time_*` |
| `KeyFindings` | Severity-tagged findings: `high_risk`, `moderate_risk`, `concern`, `positive` |
| `Scorecard` | `verdict` (LOW RISK/CAUTION/HIGH RISK), per-signal RAG, strengths/concerns |

### What's Missing

1. **Policy representation** — No structured way to define and load policy rules
2. **Offer schema** — No schema for the loan offer being evaluated
3. **Evaluation engine** — No logic to compare customer data against policy rules
4. **Judgment output** — No schema or renderer for the judgment result
5. **Batch orchestration** — No batch processing pipeline for multiple customers

---

## 3. Implementation Tiers

### Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│  TIER 1 — Deterministic Policy Engine (POC)              ~ 2-3 days  │
│                                                                        │
│  • Policy rules as Python config (like thresholds.py)                  │
│  • Offer schema + judgment schema                                      │
│  • Rule-by-rule evaluation → pass/fail per rule                        │
│  • Aggregate verdict (JUSTIFIED / UNJUSTIFIED)                         │
│  • LLM narrative over structured judgment                              │
│  • Single customer + basic batch (loop)                                │
│                                                                        │
│  VALUE: Immediate usable POC. Works today. Fully auditable.            │
├────────────────────────────────────────────────────────────────────────┤
│  TIER 2 — LLM-Assisted Policy Interpretation             ~ 3-4 days  │
│                                                                        │
│  • Policy documents as markdown/PDF → LLM extracts rules              │
│  • Policy rule cache (extract once, reuse)                             │
│  • Richer judgment with nuanced reasoning                              │
│  • Handle ambiguous/qualitative policy clauses                         │
│  • Policy version management                                           │
│                                                                        │
│  VALUE: Non-engineers can update policies without code changes.        │
├────────────────────────────────────────────────────────────────────────┤
│  TIER 3 — RAG Policy Engine + Production Batch           ~ 5-7 days  │
│                                                                        │
│  • RAG retrieval of relevant policy sections per customer profile      │
│  • Async batch pipeline with progress tracking                         │
│  • Batch judgment report (PDF/HTML) across portfolio                   │
│  • Policy deviation analytics (which rules fail most)                  │
│  • Fine-tuned judgment model (long-term)                               │
│                                                                        │
│  VALUE: Production-grade, scalable, handles 1000s of customers.       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tier 1 — Deterministic Policy Engine (POC)

### 4.1 Policy Rule Representation

Policy rules are structured exactly like `thresholds.py` — pure Python config, one file, fully auditable.

```python
# config/policy_rules.py

"""Loan offer policy rules — deterministic evaluation criteria.

Each rule maps a customer data field to an acceptable range/condition
for a given loan product. Rules are grouped by product type.

Adding a new rule: add one entry to the relevant POLICY_RULES dict.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, List
from enum import Enum


class PolicyRuleType(Enum):
    MIN_THRESHOLD = "min"          # customer_value >= threshold
    MAX_THRESHOLD = "max"          # customer_value <= threshold
    RANGE = "range"                # min <= customer_value <= max
    MUST_NOT_EXIST = "must_not"    # flag must be absent
    MUST_EXIST = "must"            # flag must be present
    CATEGORICAL = "categorical"    # value must be in allowed set


@dataclass
class PolicyRule:
    rule_id: str                          # Unique ID (e.g., "PL_001")
    description: str                      # Human-readable rule text
    data_source: str                      # "banking" | "bureau" | "tradeline" | "scorecard"
    data_field: str                       # Dot-path to field (e.g., "salary.avg_amount")
    rule_type: PolicyRuleType
    threshold: Any = None                 # For min/max
    range_min: Any = None                 # For range
    range_max: Any = None                 # For range
    allowed_values: List[Any] = field(default_factory=list)  # For categorical
    severity: str = "hard"                # "hard" (must pass) | "soft" (warning only)
    product_types: List[str] = field(default_factory=lambda: ["ALL"])
    rationale: str = ""                   # Why this rule exists


# ─── Personal Loan Policy Rules ─────────────────────────────────────

PL_POLICY_RULES = [
    PolicyRule(
        rule_id="PL_001",
        description="Minimum monthly income required for PL eligibility",
        data_source="banking",
        data_field="salary.avg_amount",
        rule_type=PolicyRuleType.MIN_THRESHOLD,
        threshold=25000,
        severity="hard",
        rationale="Below 25k monthly income, PL repayment capacity is insufficient",
    ),
    PolicyRule(
        rule_id="PL_002",
        description="FOIR must not exceed 65% including proposed EMI",
        data_source="tradeline",
        data_field="foir",
        rule_type=PolicyRuleType.MAX_THRESHOLD,
        threshold=65.0,
        severity="hard",
        rationale="FOIR above 65% indicates over-leveraging",
    ),
    PolicyRule(
        rule_id="PL_003",
        description="No active delinquency (max DPD must be 0 in last 6 months)",
        data_source="bureau",
        data_field="max_dpd",
        rule_type=PolicyRuleType.MAX_THRESHOLD,
        threshold=0,
        severity="hard",
        rationale="Active delinquency disqualifies PL offers",
    ),
    PolicyRule(
        rule_id="PL_004",
        description="CIBIL score minimum 650",
        data_source="bureau",
        data_field="tu_score",
        rule_type=PolicyRuleType.MIN_THRESHOLD,
        threshold=650,
        severity="hard",
        rationale="Below 650 CIBIL indicates poor credit behaviour",
    ),
    PolicyRule(
        rule_id="PL_005",
        description="No betting/gambling transactions detected",
        data_source="banking",
        data_field="events",
        rule_type=PolicyRuleType.MUST_NOT_EXIST,
        threshold="betting",
        severity="hard",
        rationale="Betting/gambling activity is a disqualifying risk factor",
    ),
    PolicyRule(
        rule_id="PL_006",
        description="Account must not be classified as conduit",
        data_source="banking",
        data_field="account_quality.account_type",
        rule_type=PolicyRuleType.MUST_NOT_EXIST,
        threshold="conduit",
        severity="hard",
        rationale="Conduit accounts indicate salary routing, not genuine banking",
    ),
    PolicyRule(
        rule_id="PL_007",
        description="CC utilization should be below 75%",
        data_source="tradeline",
        data_field="cc_balance_utilization_pct",
        rule_type=PolicyRuleType.MAX_THRESHOLD,
        threshold=75.0,
        severity="soft",
        rationale="High CC utilization suggests revolving debt dependency",
    ),
    PolicyRule(
        rule_id="PL_008",
        description="No more than 2 new PLs in last 6 months",
        data_source="tradeline",
        data_field="new_trades_6m_pl",
        rule_type=PolicyRuleType.MAX_THRESHOLD,
        threshold=2,
        severity="soft",
        rationale="Rapid PL stacking is a loan-on-loan risk signal",
    ),
    PolicyRule(
        rule_id="PL_009",
        description="Unsecured enquiries in 12M should not exceed 10",
        data_source="tradeline",
        data_field="unsecured_enquiries_12m",
        rule_type=PolicyRuleType.MAX_THRESHOLD,
        threshold=10,
        severity="soft",
        rationale="High enquiry pressure suggests credit hunger",
    ),
    PolicyRule(
        rule_id="PL_010",
        description="Income stability score must be at least 50",
        data_source="banking",
        data_field="risk_indicators.income_stability_score",
        rule_type=PolicyRuleType.MIN_THRESHOLD,
        threshold=50,
        severity="soft",
        rationale="Unstable income pattern increases repayment risk",
    ),
    PolicyRule(
        rule_id="PL_011",
        description="Loan amount must not exceed 10x monthly income",
        data_source="offer",
        data_field="amount_to_income_ratio",
        rule_type=PolicyRuleType.MAX_THRESHOLD,
        threshold=10.0,
        severity="hard",
        rationale="Excessive loan-to-income ratio",
    ),
    PolicyRule(
        rule_id="PL_012",
        description="Missed payment % in last 18M should be below 10%",
        data_source="tradeline",
        data_field="pct_missed_payments_18m",
        rule_type=PolicyRuleType.MAX_THRESHOLD,
        threshold=10.0,
        severity="hard",
        rationale="High missed payment rate indicates repayment distress",
    ),
]

# ─── Home Loan Policy Rules ─────────────────────────────────────────

HL_POLICY_RULES = [
    # ... similar structure, different thresholds
]

# ─── Credit Card Policy Rules ────────────────────────────────────────

CC_POLICY_RULES = [
    # ...
]

# ─── Master Registry ─────────────────────────────────────────────────

POLICY_REGISTRY = {
    "PL": PL_POLICY_RULES,
    "HL": HL_POLICY_RULES,
    "CC": CC_POLICY_RULES,
    # "AL", "BL", "LAP", etc.
}

def get_policy_rules(product_type: str) -> List[PolicyRule]:
    """Get all applicable rules for a loan product type."""
    return POLICY_REGISTRY.get(product_type.upper(), [])
```

### 4.2 Offer Schema

```python
# schemas/loan_offer.py

"""Schema for loan offers to be evaluated against policy."""

from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class LoanOffer(BaseModel):
    """Represents a loan offer to be evaluated."""
    offer_id: str                            # Unique offer identifier
    customer_id: int                         # Maps to existing customer data
    product_type: str                        # "PL" | "HL" | "CC" | "AL" | etc.
    sanctioned_amount: float                 # Offered loan amount
    interest_rate: float                     # Annual rate %
    tenure_months: int                       # Loan duration
    emi_amount: Optional[float] = None       # Monthly EMI (can be computed)
    offer_date: Optional[date] = None
    conditions: List[str] = []               # Special conditions attached
    offered_by: Optional[str] = None         # Originator / branch
    channel: Optional[str] = None            # "branch" | "digital" | "dsa"


class BatchOfferInput(BaseModel):
    """Batch of offers for evaluation."""
    offers: List[LoanOffer]
    policy_version: str = "v1"               # Which policy version to apply
    evaluate_date: Optional[date] = None     # Point-in-time evaluation
```

### 4.3 Policy Evaluation Engine

The core engine — **no LLM, pure Python, fully deterministic**.

```python
# pipeline/policy/policy_engine.py

"""Deterministic policy evaluation engine.

Takes a customer's structured data (CustomerReport + BureauReport + TradelineFeatures)
and a LoanOffer, evaluates every applicable policy rule, and produces a PolicyJudgment.

Architecture:
    CustomerReport + BureauReport + Offer → PolicyEngine.evaluate() → PolicyJudgment
                                                   ↓
                                            (deterministic, no LLM)
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
from config.policy_rules import (
    PolicyRule, PolicyRuleType, get_policy_rules, POLICY_REGISTRY
)
from schemas.loan_offer import LoanOffer
from schemas.policy_judgment import PolicyJudgment, RuleResult

logger = logging.getLogger(__name__)


class PolicyEngine:
    """Evaluates loan offers against policy rules using pre-computed customer data."""

    def evaluate(
        self,
        offer: LoanOffer,
        customer_report: "CustomerReport",
        bureau_report: "BureauReport",
        tradeline_features: "TradelineFeatures",
        scorecard: Dict,
    ) -> PolicyJudgment:
        """Evaluate a single offer against all applicable policy rules.

        Returns PolicyJudgment with per-rule results and aggregate verdict.
        """
        rules = get_policy_rules(offer.product_type)
        if not rules:
            return PolicyJudgment(
                offer_id=offer.offer_id,
                customer_id=offer.customer_id,
                verdict="INSUFFICIENT_DATA",
                reason="No policy rules defined for product type: " + offer.product_type,
            )

        # Build unified data context for rule evaluation
        context = self._build_evaluation_context(
            offer, customer_report, bureau_report, tradeline_features, scorecard
        )

        # Evaluate each rule
        rule_results = []
        for rule in rules:
            result = self._evaluate_rule(rule, context)
            rule_results.append(result)

        # Aggregate verdict
        verdict, confidence = self._compute_verdict(rule_results)

        # Identify missed risk flags and addressed flags
        risk_flags_missed = self._find_missed_flags(
            rule_results, customer_report, bureau_report
        )
        risk_flags_addressed = self._find_addressed_flags(rule_results)

        # Compute recommended adjustments
        adjustments = self._compute_adjustments(
            offer, rule_results, context
        )

        return PolicyJudgment(
            offer_id=offer.offer_id,
            customer_id=offer.customer_id,
            product_type=offer.product_type,
            verdict=verdict,
            confidence=confidence,
            rule_results=rule_results,
            hard_fails=sum(1 for r in rule_results if not r.passed and r.severity == "hard"),
            soft_fails=sum(1 for r in rule_results if not r.passed and r.severity == "soft"),
            total_rules=len(rule_results),
            risk_flags_missed=risk_flags_missed,
            risk_flags_addressed=risk_flags_addressed,
            recommended_adjustments=adjustments,
        )

    def _build_evaluation_context(self, offer, customer_report, bureau_report,
                                   tradeline_features, scorecard) -> Dict[str, Any]:
        """Flatten all data sources into a single dot-path-accessible context."""
        ctx = {}

        # Banking data
        if customer_report:
            ctx["salary.avg_amount"] = getattr(
                customer_report.salary, "avg_amount", None
            ) if customer_report.salary else None
            ctx["savings.savings_rate"] = getattr(
                customer_report.savings, "savings_rate", None
            ) if customer_report.savings else None
            ctx["savings.net_savings"] = getattr(
                customer_report.savings, "net_savings", None
            ) if customer_report.savings else None
            ctx["risk_indicators.income_stability_score"] = getattr(
                customer_report.risk_indicators, "income_stability_score", None
            ) if customer_report.risk_indicators else None
            ctx["risk_indicators.risk_level"] = getattr(
                customer_report.risk_indicators, "risk_level", None
            ) if customer_report.risk_indicators else None
            ctx["account_quality.account_type"] = (
                customer_report.account_quality.get("account_type")
                if customer_report.account_quality else None
            )
            ctx["events"] = customer_report.events or []
            # EMI burden
            emi_total = sum(
                e.amount for e in (customer_report.emis or []) if e.amount
            )
            rent_amount = (
                customer_report.rent.amount if customer_report.rent else 0
            )
            ctx["existing_emi_total"] = emi_total
            ctx["existing_rent"] = rent_amount

        # Bureau data
        if bureau_report and bureau_report.executive_inputs:
            ei = bureau_report.executive_inputs
            ctx["max_dpd"] = ei.max_dpd
            ctx["has_delinquency"] = ei.has_delinquency
            ctx["total_tradelines"] = ei.total_tradelines
            ctx["total_outstanding"] = ei.total_outstanding
            ctx["tu_score"] = ei.tu_score

        # Tradeline features
        if tradeline_features:
            for field_name in [
                "foir", "foir_unsec", "aff_emi", "unsecured_emi",
                "cc_balance_utilization_pct", "new_trades_6m_pl",
                "unsecured_enquiries_12m", "pct_missed_payments_18m",
                "interpurchase_time_6m_plbl", "ratio_good_closed_pl",
                "pct_0plus_24m_all",
            ]:
                ctx[field_name] = getattr(tradeline_features, field_name, None)

        # Scorecard
        if scorecard:
            ctx["scorecard_verdict"] = scorecard.get("verdict")
            ctx["scorecard_rag"] = scorecard.get("verdict_rag")

        # Offer-derived fields
        if offer and ctx.get("salary.avg_amount"):
            salary = ctx["salary.avg_amount"]
            if salary and salary > 0:
                ctx["amount_to_income_ratio"] = offer.sanctioned_amount / salary
                # Proposed FOIR including new EMI
                proposed_emi = offer.emi_amount or (
                    offer.sanctioned_amount / offer.tenure_months  # rough estimate
                )
                existing_obligations = ctx.get("existing_emi_total", 0) + ctx.get("existing_rent", 0)
                ctx["proposed_foir"] = (
                    (existing_obligations + proposed_emi) / salary * 100
                )

        return ctx

    def _evaluate_rule(self, rule: PolicyRule, context: Dict) -> RuleResult:
        """Evaluate a single rule against the context."""
        value = context.get(rule.data_field)

        # Handle special rule types
        if rule.rule_type == PolicyRuleType.MUST_NOT_EXIST:
            return self._eval_must_not_exist(rule, context)
        if rule.rule_type == PolicyRuleType.MUST_EXIST:
            return self._eval_must_exist(rule, context)

        # Value not available
        if value is None:
            return RuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                passed=True,  # Can't fail what we can't check
                severity=rule.severity,
                customer_value=None,
                threshold_value=str(rule.threshold or rule.range_min),
                reason="Data not available — rule skipped",
                data_available=False,
            )

        # Threshold evaluations
        if rule.rule_type == PolicyRuleType.MIN_THRESHOLD:
            passed = value >= rule.threshold
            return RuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                passed=passed,
                severity=rule.severity,
                customer_value=value,
                threshold_value=rule.threshold,
                reason=f"{'Meets' if passed else 'Below'} minimum: {value} vs {rule.threshold}",
            )

        if rule.rule_type == PolicyRuleType.MAX_THRESHOLD:
            passed = value <= rule.threshold
            return RuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                passed=passed,
                severity=rule.severity,
                customer_value=value,
                threshold_value=rule.threshold,
                reason=f"{'Within' if passed else 'Exceeds'} maximum: {value} vs {rule.threshold}",
            )

        if rule.rule_type == PolicyRuleType.RANGE:
            passed = rule.range_min <= value <= rule.range_max
            return RuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                passed=passed,
                severity=rule.severity,
                customer_value=value,
                threshold_value=f"{rule.range_min}–{rule.range_max}",
                reason=f"{'Within' if passed else 'Outside'} range: {value}",
            )

        if rule.rule_type == PolicyRuleType.CATEGORICAL:
            passed = value in rule.allowed_values
            return RuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                passed=passed,
                severity=rule.severity,
                customer_value=value,
                threshold_value=str(rule.allowed_values),
                reason=f"Value '{value}' {'in' if passed else 'not in'} allowed set",
            )

        return RuleResult(
            rule_id=rule.rule_id,
            description=rule.description,
            passed=True,
            severity=rule.severity,
            reason="Unknown rule type — skipped",
        )

    def _eval_must_not_exist(self, rule: PolicyRule, context: Dict) -> RuleResult:
        """Check that a flag/event/classification is NOT present."""
        if rule.data_field == "events":
            events = context.get("events", [])
            flag_keyword = str(rule.threshold).lower()
            found = any(
                flag_keyword in str(e.get("type", "")).lower() or
                flag_keyword in str(e.get("label", "")).lower()
                for e in events
            )
            return RuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                passed=not found,
                severity=rule.severity,
                customer_value="detected" if found else "not detected",
                threshold_value=f"must not have: {rule.threshold}",
                reason=f"{'Found' if found else 'Not found'}: {rule.threshold}",
            )
        else:
            value = context.get(rule.data_field)
            found = value == rule.threshold
            return RuleResult(
                rule_id=rule.rule_id,
                description=rule.description,
                passed=not found,
                severity=rule.severity,
                customer_value=value,
                threshold_value=f"must not be: {rule.threshold}",
                reason=f"Value is '{value}'",
            )

    def _eval_must_exist(self, rule: PolicyRule, context: Dict) -> RuleResult:
        """Check that a flag/field IS present."""
        value = context.get(rule.data_field)
        found = value is not None and value != "" and value != 0
        return RuleResult(
            rule_id=rule.rule_id,
            description=rule.description,
            passed=found,
            severity=rule.severity,
            customer_value=value,
            threshold_value="must exist",
            reason=f"{'Present' if found else 'Missing'}: {rule.data_field}",
        )

    def _compute_verdict(self, results: List[RuleResult]) -> Tuple[str, float]:
        """Aggregate rule results into a verdict."""
        hard_fails = [r for r in results if not r.passed and r.severity == "hard"]
        soft_fails = [r for r in results if not r.passed and r.severity == "soft"]
        total_evaluated = [r for r in results if r.data_available]

        if not total_evaluated:
            return "INSUFFICIENT_DATA", 0.0

        if hard_fails:
            return "UNJUSTIFIED", 0.9

        if len(soft_fails) >= 3:
            return "UNJUSTIFIED", 0.7

        if soft_fails:
            return "PARTIALLY_JUSTIFIED", 0.6 + (0.1 * (1 - len(soft_fails) / len(total_evaluated)))

        return "JUSTIFIED", 0.85 + (0.15 * len(total_evaluated) / len(results))

    def _find_missed_flags(self, results, customer_report, bureau_report) -> List[str]:
        """Identify risk flags in the customer data that no policy rule checked."""
        missed = []
        if customer_report and customer_report.events:
            high_events = [e for e in customer_report.events if e.get("significance") == "high"]
            checked_event_types = {
                r.description.lower() for r in results
                if "event" in r.description.lower() or "betting" in r.description.lower()
            }
            for event in high_events:
                event_type = event.get("type", "")
                if not any(event_type in chk for chk in checked_event_types):
                    missed.append(f"HIGH event not checked by policy: {event_type} — {event.get('label', '')}")
        return missed

    def _find_addressed_flags(self, results) -> List[str]:
        """Identify which risk dimensions the policy rules covered."""
        addressed = []
        for r in results:
            if r.passed:
                addressed.append(f"[PASS] {r.rule_id}: {r.description}")
            else:
                addressed.append(f"[FAIL] {r.rule_id}: {r.description}")
        return addressed

    def _compute_adjustments(self, offer, results, context) -> List[Dict]:
        """Suggest parameter adjustments if offer is partially/un-justified."""
        adjustments = []
        for r in results:
            if r.passed:
                continue
            if "amount" in r.description.lower() or "loan-to-income" in r.description.lower():
                max_salary = context.get("salary.avg_amount", 0)
                if max_salary:
                    suggested = max_salary * (r.threshold_value if isinstance(r.threshold_value, (int, float)) else 10)
                    adjustments.append({
                        "parameter": "sanctioned_amount",
                        "current": offer.sanctioned_amount,
                        "suggested": suggested,
                        "reason": r.description,
                    })
            if "foir" in r.description.lower():
                adjustments.append({
                    "parameter": "emi_amount",
                    "current": offer.emi_amount,
                    "suggested": "Reduce loan amount or extend tenure to bring FOIR within policy",
                    "reason": r.description,
                })
        return adjustments
```

### 4.4 Judgment Narrative (LLM Layer)

```python
# pipeline/policy/judgment_narrator.py

"""LLM narrative generation for policy judgments.

Takes a structured PolicyJudgment and generates a human-readable
justification summary. Same pattern as report_summary_chain.py.
"""

from langchain_ollama import ChatOllama
from config.settings import SUMMARY_MODEL, LLM_TEMPERATURE
from config.prompts import POLICY_JUDGMENT_PROMPT
from utils.llm_utils import strip_think


def generate_judgment_narrative(judgment: "PolicyJudgment") -> str:
    """Generate LLM narrative for a policy judgment."""
    data_summary = _build_judgment_summary(judgment)

    llm = ChatOllama(model=SUMMARY_MODEL, temperature=LLM_TEMPERATURE)
    prompt = POLICY_JUDGMENT_PROMPT.format(
        customer_id=judgment.customer_id,
        product_type=judgment.product_type,
        verdict=judgment.verdict,
        data_summary=data_summary,
    )

    response = llm.invoke(prompt)
    return strip_think(response.content, label="policy_judgment")


def _build_judgment_summary(judgment) -> str:
    """Build structured input for the LLM prompt."""
    lines = []
    lines.append(f"VERDICT: {judgment.verdict}")
    lines.append(f"Hard rule failures: {judgment.hard_fails} / Soft warnings: {judgment.soft_fails}")
    lines.append("")

    lines.append("RULE-BY-RULE RESULTS:")
    for r in judgment.rule_results:
        status = "PASS" if r.passed else "FAIL"
        sev = f" [{r.severity.upper()}]" if not r.passed else ""
        lines.append(f"  [{status}]{sev} {r.rule_id} — {r.description}")
        lines.append(f"         Customer: {r.customer_value} | Policy: {r.threshold_value}")
        lines.append(f"         {r.reason}")

    if judgment.risk_flags_missed:
        lines.append("")
        lines.append("RISK FLAGS NOT COVERED BY POLICY:")
        for flag in judgment.risk_flags_missed:
            lines.append(f"  - {flag}")

    if judgment.recommended_adjustments:
        lines.append("")
        lines.append("RECOMMENDED ADJUSTMENTS:")
        for adj in judgment.recommended_adjustments:
            lines.append(f"  - {adj['parameter']}: {adj['current']} → {adj['suggested']} ({adj['reason']})")

    return "\n".join(lines)
```

### 4.5 New Prompt

```python
# Addition to config/prompts.py

POLICY_JUDGMENT_PROMPT = """You are a senior credit policy auditor reviewing a loan offer decision.

CUSTOMER: {customer_id}
PRODUCT: {product_type}
OVERALL VERDICT: {verdict}

DETAILED EVALUATION:
{data_summary}

Write a 2-paragraph professional assessment:

PARAGRAPH 1 — POLICY COMPLIANCE:
State the verdict clearly. List which hard rules passed/failed with specific numbers.
If any hard rules failed, explain WHY the offer should not have been extended.
If all hard rules passed, state which soft warnings deserve attention.

PARAGRAPH 2 — RISK ASSESSMENT & RECOMMENDATION:
Highlight any risk flags that the policy rules did not cover but are present in the data.
If adjustments are recommended, state them concisely with rationale.
End with a clear recommendation: approve as-is / approve with conditions / reject / needs review.

RULES:
- Use exact numbers from the data — never round or approximate
- Do not invent information not present in the evaluation
- Maintain formal third-person audit tone
- Keep each paragraph to 4-6 lines maximum"""
```

### 4.6 Integration Point — Chat Query

Add a new intent and tool so users can ask: *"Was the PL offer for customer 5004898 justified?"*

```python
# Addition to config/intents.py
IntentType.POLICY_JUDGMENT = "policy_judgment"

# Addition to INTENT_TOOL_MAP
"policy_judgment": ["evaluate_offer_policy"]

# New tool in executor
"evaluate_offer_policy": policy_tools.evaluate_offer
```

---

## 5. Tier 2 — LLM-Assisted Policy Interpretation

### 5.1 The Problem Tier 1 Doesn't Solve

Tier 1 requires policy rules as Python code. Real-world policy documents are:
- PDF/Word documents with natural language clauses
- Contain qualitative rules: *"Customer must demonstrate financial discipline"*
- Have exceptions: *"DPD waiver if customer has 3+ years relationship"*
- Are version-controlled by the business, not engineers

### 5.2 Policy Document Loader

```python
# pipeline/policy/policy_loader.py

"""Load and parse policy documents into structured rules.

Supports:
- Markdown files (internal policy docs)
- YAML files (structured rule definitions)
- PDF files (via text extraction) — future

Architecture:
    policy.md → PolicyLoader → List[ExtractedRule] → PolicyRuleCache
                     ↓
              LLM (one-time extraction)
"""

class PolicyLoader:
    """Extracts structured rules from policy documents using LLM."""

    def __init__(self, cache_dir: str = "data/policy_cache"):
        self.cache_dir = cache_dir

    def load_and_extract(self, policy_path: str, product_type: str) -> List[PolicyRule]:
        """Load policy document and extract rules.

        Uses LLM to interpret natural language clauses into structured rules.
        Results are cached — extraction happens once per document version.
        """
        # Check cache first
        cache_key = self._cache_key(policy_path, product_type)
        cached = self._load_cache(cache_key)
        if cached:
            return cached

        # Read document
        policy_text = self._read_document(policy_path)

        # LLM extraction
        rules = self._extract_rules_llm(policy_text, product_type)

        # Validate extracted rules
        validated = self._validate_extracted_rules(rules)

        # Cache
        self._save_cache(cache_key, validated)
        return validated

    def _extract_rules_llm(self, policy_text: str, product_type: str) -> List[Dict]:
        """Use LLM to convert policy text into structured rules."""
        prompt = POLICY_EXTRACTION_PROMPT.format(
            policy_text=policy_text,
            product_type=product_type,
            available_data_fields=self._list_available_fields(),
        )
        llm = ChatOllama(model=PARSER_MODEL, format="json", temperature=0)
        response = llm.invoke(prompt)
        return json.loads(response.content)["rules"]
```

### 5.3 Qualitative Rule Evaluation

For rules that can't be purely numeric (e.g., *"Customer must demonstrate financial discipline"*), use an LLM judgment call with structured evidence:

```python
# pipeline/policy/qualitative_evaluator.py

class QualitativeEvaluator:
    """Evaluates soft/qualitative policy rules using LLM with evidence."""

    def evaluate(self, rule_text: str, evidence: Dict) -> RuleResult:
        """
        Given a qualitative rule and structured evidence,
        produce a pass/fail judgment with reasoning.
        """
        prompt = QUALITATIVE_RULE_PROMPT.format(
            rule=rule_text,
            evidence=json.dumps(evidence, indent=2),
        )
        llm = ChatOllama(model=SUMMARY_MODEL, temperature=0)
        response = llm.invoke(prompt)
        # Parse structured judgment from LLM
        result = json.loads(strip_think(response.content))
        return RuleResult(
            passed=result["passed"],
            reason=result["reasoning"],
            confidence=result.get("confidence", 0.5),
        )
```

### 5.4 Policy Version Management

```python
# config/policy_versions.py

POLICY_VERSIONS = {
    "v1.0": {
        "effective_date": "2025-01-01",
        "document": "data/policies/pl_policy_v1.md",
        "product_types": ["PL", "BL"],
    },
    "v1.1": {
        "effective_date": "2025-07-01",
        "document": "data/policies/pl_policy_v1.1.md",
        "product_types": ["PL", "BL"],
        "changelog": "Added betting/gambling exclusion, lowered FOIR threshold to 60%",
    },
}

def get_active_policy(product_type: str, as_of_date: date = None) -> Dict:
    """Return the most recent policy version effective on the given date."""
    ...
```

---

## 6. Tier 3 — RAG Policy Engine + Batch Pipeline

### 6.1 RAG Policy Retrieval

For large, complex policy documents (50+ pages), retrieve only the relevant sections per customer profile rather than feeding the entire document.

```python
# pipeline/policy/policy_rag.py

"""RAG-based policy retrieval for large policy documents.

Chunks policy documents, embeds them, and retrieves the most relevant
sections based on the customer's profile characteristics.
"""

class PolicyRAG:
    """Retrieves relevant policy sections for a specific customer context."""

    def __init__(self, policy_path: str):
        self.chunks = self._chunk_document(policy_path)
        self.embeddings = self._embed_chunks(self.chunks)

    def retrieve_relevant_rules(
        self, customer_context: Dict, top_k: int = 10
    ) -> List[str]:
        """Retrieve policy sections most relevant to this customer's profile.

        Uses the customer's risk profile as the query:
        - High DPD → retrieves delinquency policy sections
        - High FOIR → retrieves leverage policy sections
        - Betting detected → retrieves lifestyle risk sections
        """
        query = self._build_profile_query(customer_context)
        relevant = self._similarity_search(query, top_k)
        return relevant
```

### 6.2 Batch Deviation Analytics

After running batch evaluations, aggregate patterns:

```python
# pipeline/policy/batch_analytics.py

class PolicyDeviationAnalytics:
    """Analyzes patterns across batch policy judgments."""

    def analyze(self, judgments: List[PolicyJudgment]) -> Dict:
        return {
            "total_evaluated": len(judgments),
            "justified": sum(1 for j in judgments if j.verdict == "JUSTIFIED"),
            "unjustified": sum(1 for j in judgments if j.verdict == "UNJUSTIFIED"),
            "partially_justified": sum(1 for j in judgments if j.verdict == "PARTIALLY_JUSTIFIED"),

            # Which rules fail most often?
            "most_failed_rules": self._top_failed_rules(judgments),

            # Which risk flags are most commonly missed?
            "most_missed_flags": self._top_missed_flags(judgments),

            # Distribution by product type
            "by_product": self._group_by_product(judgments),

            # Distribution by branch/channel
            "by_channel": self._group_by_channel(judgments),

            # Average offer deviation from policy-compliant parameters
            "avg_deviation": self._compute_avg_deviation(judgments),
        }
```

---

## 7. Batch Processing Architecture

### 7.1 The Scale Problem

Single-customer judgment (Tier 1): ~2-5s (data retrieval + rule evaluation + LLM narrative).
For 1000 customers: 2000-5000s sequentially = **33-83 minutes**. Unacceptable.

### 7.2 Batch Architecture

```
BatchOfferInput (CSV / JSON)
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  BATCH ORCHESTRATOR                                               │
│                                                                    │
│  Phase 1: Data Pre-Loading (BULK, ~10s for 1000 customers)        │
│  ├── Load all customer reports from cache/build                    │
│  ├── Load all bureau reports from cache/build                      │
│  └── Load all tradeline features (single CSV read)                 │
│                                                                    │
│  Phase 2: Deterministic Evaluation (PARALLEL, ~5s for 1000)       │
│  ├── PolicyEngine.evaluate() per customer                          │
│  ├── Pure Python, no I/O → trivially parallelisable                │
│  └── concurrent.futures.ProcessPoolExecutor(max_workers=8)         │
│                                                                    │
│  Phase 3: LLM Narrative (BATCHED, optional)                       │
│  ├── Skip for batch mode (narrative only for flagged cases)        │
│  ├── OR batch LLM calls with asyncio.gather()                     │
│  └── Only generate narratives for UNJUSTIFIED verdicts             │
│                                                                    │
│  Phase 4: Aggregation & Output                                     │
│  ├── PolicyDeviationAnalytics.analyze()                            │
│  ├── Generate batch report (PDF/HTML/CSV)                          │
│  └── Audit log (JSONL)                                             │
└──────────────────────────────────────────────────────────────────┘
```

### 7.3 Batch Optimization Strategies

| Strategy | Impact | Effort |
|---|---|---|
| **Skip LLM narrative for JUSTIFIED verdicts** | -80% LLM calls | Low |
| **Pre-load all customer data in bulk** | -90% I/O time | Low |
| **Parallel rule evaluation** (ProcessPoolExecutor) | -75% eval time | Low |
| **Async LLM calls** (asyncio.gather for narratives) | -60% LLM time | Medium |
| **Pre-compute & cache reports** (run report batch first) | -95% report time | Medium |
| **Batch LLM prompts** (multiple customers in one prompt) | -70% LLM calls | Medium |

### 7.4 Estimated Batch Timing (1000 Customers)

| Phase | Sequential | Optimized (Tier 1) | Optimized (Tier 3) |
|---|---|---|---|
| Data loading | 300s | 10s (bulk load) | 10s (bulk load) |
| Rule evaluation | 500s | 5s (parallel) | 5s (parallel) |
| LLM narrative | 4000s | 400s (only unjustified) | 200s (async + batched) |
| Aggregation | 10s | 2s | 5s (with analytics) |
| **Total** | **~80 min** | **~7 min** | **~4 min** |

### 7.5 Batch Orchestrator Implementation

```python
# pipeline/policy/batch_evaluator.py

"""Batch policy evaluation pipeline.

Evaluates 100s-1000s of loan offers against policy rules.
Optimized for throughput: bulk data loading, parallel evaluation,
selective LLM narrative generation.
"""

import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Optional

from schemas.loan_offer import LoanOffer, BatchOfferInput
from schemas.policy_judgment import PolicyJudgment, BatchJudgmentResult
from pipeline.policy.policy_engine import PolicyEngine
from pipeline.policy.judgment_narrator import generate_judgment_narrative

logger = logging.getLogger(__name__)


class BatchPolicyEvaluator:
    """Evaluates loan offers in batch with progress tracking."""

    def __init__(
        self,
        max_workers: int = 8,
        generate_narratives: bool = False,
        narrative_only_for: List[str] = None,
    ):
        self.max_workers = max_workers
        self.generate_narratives = generate_narratives
        # Only generate LLM narratives for these verdicts (saves time)
        self.narrative_verdicts = narrative_only_for or ["UNJUSTIFIED", "PARTIALLY_JUSTIFIED"]

    def evaluate_batch(
        self,
        offers: List[LoanOffer],
        progress_callback=None,
    ) -> BatchJudgmentResult:
        """Evaluate a batch of offers against policy.

        Args:
            offers: List of LoanOffer to evaluate
            progress_callback: Optional fn(completed, total) for UI progress

        Returns:
            BatchJudgmentResult with all judgments + analytics
        """
        start = time.time()
        total = len(offers)
        logger.info("Starting batch evaluation: %d offers", total)

        # Phase 1: Bulk data pre-load
        customer_ids = list(set(o.customer_id for o in offers))
        data_cache = self._bulk_load_customer_data(customer_ids)
        logger.info("Phase 1 complete: loaded data for %d customers (%.1fs)",
                     len(data_cache), time.time() - start)

        # Phase 2: Parallel rule evaluation
        engine = PolicyEngine()
        judgments = []

        with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {}
            for offer in offers:
                cd = data_cache.get(offer.customer_id, {})
                future = pool.submit(
                    engine.evaluate,
                    offer=offer,
                    customer_report=cd.get("customer_report"),
                    bureau_report=cd.get("bureau_report"),
                    tradeline_features=cd.get("tradeline_features"),
                    scorecard=cd.get("scorecard"),
                )
                futures[future] = offer

            completed = 0
            for future in as_completed(futures):
                judgment = future.result()
                judgments.append(judgment)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        logger.info("Phase 2 complete: evaluated %d offers (%.1fs)",
                     len(judgments), time.time() - start)

        # Phase 3: Selective LLM narratives
        if self.generate_narratives:
            needs_narrative = [
                j for j in judgments if j.verdict in self.narrative_verdicts
            ]
            logger.info("Phase 3: generating narratives for %d/%d judgments",
                         len(needs_narrative), total)
            for j in needs_narrative:
                try:
                    j.narrative = generate_judgment_narrative(j)
                except Exception as e:
                    logger.warning("Narrative failed for %s: %s", j.offer_id, e)
                    j.narrative = f"[Narrative generation failed: {e}]"

        # Phase 4: Analytics
        from pipeline.policy.batch_analytics import PolicyDeviationAnalytics
        analytics = PolicyDeviationAnalytics().analyze(judgments)

        elapsed = time.time() - start
        logger.info("Batch complete: %d offers in %.1fs (%.1f offers/sec)",
                     total, elapsed, total / elapsed if elapsed > 0 else 0)

        return BatchJudgmentResult(
            judgments=judgments,
            analytics=analytics,
            total_evaluated=total,
            elapsed_seconds=elapsed,
        )

    def _bulk_load_customer_data(self, customer_ids: List[int]) -> Dict:
        """Pre-load all required data for batch evaluation.

        Loads once, reuses for all offers per customer.
        """
        from data.loader import get_transactions_df, get_bureau_df
        from pipeline.reports.customer_report_builder import build_customer_report
        from pipeline.reports.bureau_report_builder import build_bureau_report
        from pipeline.extractors.tradeline_feature_extractor import extract_tradeline_features

        cache = {}
        for cid in customer_ids:
            try:
                cache[cid] = {
                    "customer_report": build_customer_report(cid),
                    "bureau_report": build_bureau_report(cid),
                    "tradeline_features": extract_tradeline_features(cid),
                    "scorecard": None,  # Optional — compute if needed
                }
            except Exception as e:
                logger.warning("Failed to load data for customer %s: %s", cid, e)
                cache[cid] = {}

        return cache
```

---

## 8. Schema Design

### 8.1 PolicyJudgment Schema

```python
# schemas/policy_judgment.py

"""Schemas for policy evaluation results."""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class RuleResult(BaseModel):
    """Result of evaluating a single policy rule."""
    rule_id: str
    description: str
    passed: bool
    severity: str = "hard"                    # "hard" | "soft"
    customer_value: Any = None                # What the customer's data showed
    threshold_value: Any = None               # What the policy requires
    reason: str = ""                          # Human-readable explanation
    data_available: bool = True               # Was the data present to evaluate?


class PolicyJudgment(BaseModel):
    """Complete judgment of a loan offer against policy."""
    offer_id: str
    customer_id: int
    product_type: str = ""
    verdict: str                              # JUSTIFIED | UNJUSTIFIED | PARTIALLY_JUSTIFIED | INSUFFICIENT_DATA
    confidence: float = 0.0                   # 0–1
    rule_results: List[RuleResult] = []       # Per-rule breakdown
    hard_fails: int = 0
    soft_fails: int = 0
    total_rules: int = 0
    risk_flags_missed: List[str] = []         # Flags in data but not in policy
    risk_flags_addressed: List[str] = []      # What the policy covered
    recommended_adjustments: List[Dict] = []  # {parameter, current, suggested, reason}
    narrative: Optional[str] = None           # LLM-generated summary (optional)
    evaluated_at: datetime = datetime.now()
    policy_version: str = "v1"


class BatchJudgmentResult(BaseModel):
    """Result of batch policy evaluation."""
    judgments: List[PolicyJudgment]
    analytics: Dict[str, Any] = {}
    total_evaluated: int = 0
    elapsed_seconds: float = 0.0
```

---

## 9. File Structure & Module Placement

Follows the existing project structure exactly:

```
langchain_agentic_v7_hs/
│
├── config/
│   ├── policy_rules.py          # NEW — PolicyRule definitions (like thresholds.py)
│   ├── policy_versions.py       # NEW — Policy version registry (Tier 2)
│   ├── prompts.py               # UPDATED — add POLICY_JUDGMENT_PROMPT
│   ├── intents.py               # UPDATED — add POLICY_JUDGMENT intent
│   └── settings.py              # UPDATED — add ENABLE_POLICY_ENGINE flag
│
├── schemas/
│   ├── loan_offer.py            # NEW — LoanOffer, BatchOfferInput
│   └── policy_judgment.py       # NEW — RuleResult, PolicyJudgment, BatchJudgmentResult
│
├── pipeline/
│   └── policy/                  # NEW MODULE
│       ├── __init__.py
│       ├── policy_engine.py     # Core deterministic evaluation engine
│       ├── judgment_narrator.py # LLM narrative for judgments
│       ├── batch_evaluator.py   # Batch processing pipeline
│       ├── batch_analytics.py   # Deviation analytics
│       ├── policy_loader.py     # Tier 2 — document → rules extraction
│       └── policy_rag.py        # Tier 3 — RAG retrieval
│
├── tools/
│   └── policy_tools.py          # NEW — evaluate_offer tool for chat integration
│
├── data/
│   └── policies/                # NEW — Policy document storage
│       ├── pl_policy_v1.md      # PL policy document
│       └── sample_offers.csv    # Sample offer data for testing
│
└── templates/
    └── policy_judgment.html     # NEW — HTML template for judgment reports
```

**No existing files are modified** in Tier 1 except:
- `config/prompts.py` — add 1 prompt
- `config/intents.py` — add 1 intent + tool mapping
- `pipeline/core/executor.py` — register 1 tool
- `config/settings.py` — add 1 feature flag

---

## 10. Implementation Steps

### Phase 1 — POC Foundation (Day 1-2)

| Step | File | What | Depends On |
|---|---|---|---|
| 1 | `schemas/loan_offer.py` | Define LoanOffer + BatchOfferInput | Nothing |
| 2 | `schemas/policy_judgment.py` | Define RuleResult + PolicyJudgment + BatchJudgmentResult | Nothing |
| 3 | `config/policy_rules.py` | Define PolicyRule dataclass + PL rules + registry | Nothing |
| 4 | `pipeline/policy/policy_engine.py` | Core evaluation engine | Steps 1-3 |
| 5 | `config/prompts.py` | Add POLICY_JUDGMENT_PROMPT | Nothing |
| 6 | `pipeline/policy/judgment_narrator.py` | LLM narrative generation | Steps 4-5 |

**Deliverable:** Can evaluate a single offer against PL policy and get a structured judgment with narrative.

### Phase 2 — Integration + Batch (Day 3-4)

| Step | File | What | Depends On |
|---|---|---|---|
| 7 | `tools/policy_tools.py` | Chat-queryable tool | Phase 1 |
| 8 | `config/intents.py` | Add POLICY_JUDGMENT intent | Step 7 |
| 9 | `pipeline/core/executor.py` | Register policy tool | Step 7 |
| 10 | `pipeline/policy/batch_evaluator.py` | Batch pipeline | Phase 1 |
| 11 | `pipeline/policy/batch_analytics.py` | Deviation analytics | Step 10 |

**Deliverable:** Users can ask "Was the PL offer for customer X justified?" in chat. Batch evaluation works for CSV input.

### Phase 3 — Rendering + UI (Day 5)

| Step | File | What | Depends On |
|---|---|---|---|
| 12 | `templates/policy_judgment.html` | HTML judgment template | Phase 1 |
| 13 | `pipeline/renderers/policy_renderer.py` | PDF + HTML renderer | Step 12 |
| 14 | `app.py` | Streamlit batch upload UI | Phase 2 |

**Deliverable:** Full UI flow — upload CSV of offers, get batch judgment report as PDF.

### Phase 4 — Policy Document Loader (Day 6-7, Tier 2)

| Step | File | What | Depends On |
|---|---|---|---|
| 15 | `pipeline/policy/policy_loader.py` | LLM-based policy extraction | Phase 1 |
| 16 | `config/policy_versions.py` | Version management | Step 15 |
| 17 | `pipeline/policy/qualitative_evaluator.py` | Soft rule LLM evaluation | Step 15 |

### Phase 5 — RAG + Scale (Day 8-10, Tier 3)

| Step | File | What | Depends On |
|---|---|---|---|
| 18 | `pipeline/policy/policy_rag.py` | RAG retrieval | Phase 4 |
| 19 | Optimize batch_evaluator.py | Async LLM, smarter caching | Phase 2 |

---

## 11. Examples — Before and After

### Example 1: Single Offer Evaluation (Chat)

```
User: "Was the 5 lakh PL offer for customer 5004898 justified?"

IntentParser → POLICY_JUDGMENT, customer_id=5004898
    ↓
PolicyEngine.evaluate(
    offer=LoanOffer(customer_id=5004898, product_type="PL", sanctioned_amount=500000),
    customer_report=<cached>,
    bureau_report=<cached>,
    tradeline_features=<cached>,
)
    ↓
PolicyJudgment:
    verdict: "PARTIALLY_JUSTIFIED"
    hard_fails: 0
    soft_fails: 2
    rule_results: [
        {PL_001: PASS — salary 45000 >= 25000},
        {PL_002: PASS — FOIR 52% <= 65%},
        {PL_003: PASS — max DPD 0},
        {PL_004: PASS — CIBIL 720 >= 650},
        {PL_005: PASS — no betting detected},
        {PL_007: FAIL [SOFT] — CC utilization 78% > 75%},
        {PL_008: FAIL [SOFT] — new PLs in 6M: 3 > 2},
        ...
    ]
    ↓
LLM Narrative:
    "The ₹5,00,000 personal loan offer for Customer ###4898 passes all hard policy
     requirements — CIBIL score of 720 exceeds the 650 minimum, FOIR at 52% is within
     the 65% cap, and no delinquency or betting activity was detected.

     However, two soft policy warnings merit attention: credit card utilization at 78%
     exceeds the 75% guideline, and 3 new personal loans in the last 6 months exceeds
     the recommended maximum of 2. These signals suggest active credit stacking.
     Recommendation: Approve with condition — require CC paydown plan before disbursal."
```

### Example 2: Batch Evaluation

```
Input: offers.csv (500 rows)
    offer_id, customer_id, product_type, sanctioned_amount, interest_rate, tenure_months
    OFF001, 5004898, PL, 500000, 14.5, 36
    OFF002, 5004899, PL, 300000, 13.0, 24
    ...

Output: BatchJudgmentResult
    total_evaluated: 500
    elapsed_seconds: 180  (3 minutes)

    analytics:
        justified: 312 (62.4%)
        partially_justified: 108 (21.6%)
        unjustified: 68 (13.6%)
        insufficient_data: 12 (2.4%)

        most_failed_rules:
            PL_002 (FOIR > 65%): 45 failures
            PL_008 (new PLs > 2): 38 failures
            PL_003 (active DPD): 22 failures

        most_missed_flags:
            "HIGH event: self_transfer_post_salary": 34 customers
            "HIGH event: loan_redistribution": 12 customers
```

### Example 3: Unjustified Offer Flagged

```
Customer: 5004901
Offer: PL ₹8,00,000 @ 16% for 48 months

PolicyJudgment:
    verdict: "UNJUSTIFIED"
    hard_fails: 3
    rule_results: [
        {PL_001: FAIL [HARD] — salary 18000 < 25000 minimum},
        {PL_003: FAIL [HARD] — max DPD 45 > 0},
        {PL_011: FAIL [HARD] — amount/income ratio 44.4x > 10x max},
        {PL_005: FAIL [HARD] — betting transactions detected},
    ]
    risk_flags_missed: [
        "HIGH event: loan_redistribution — not checked by policy",
        "Account classified as CONDUIT — PL_006 triggered separately",
    ]
    recommended_adjustments: [
        {parameter: "sanctioned_amount", current: 800000, suggested: 180000,
         reason: "Max 10x monthly income of ₹18,000"},
    ]

Narrative:
    "The ₹8,00,000 personal loan offer for Customer ###4901 violates 3 hard policy
     rules and should not have been extended. Monthly salary of ₹18,000 is below the
     ₹25,000 minimum, the loan amount at 44.4x income far exceeds the 10x policy cap,
     and a max DPD of 45 days indicates active delinquency.

     Additionally, betting transactions were detected in the banking data — a disqualifying
     risk factor. The policy also did not check for loan redistribution activity, which
     was flagged as a HIGH significance event. Recommendation: Reject. If reconsideration
     is desired, the maximum eligible amount is ₹1,80,000 subject to DPD resolution."
```

---

## 12. Architecture Decision Records

### ADR-1: Why Deterministic Rules First (Not LLM Judgment)

The system's core principle is **deterministic core, LLM periphery**. Policy evaluation MUST be deterministic because:

1. **Auditability** — Regulators ask "why was this loan approved?" The answer must be traceable to specific rule evaluations, not "the LLM said so."
2. **Reproducibility** — Same customer data + same policy = same verdict. Always.
3. **Speed** — Pure Python rule evaluation: ~5ms per customer. LLM judgment: ~3s. For 1000 customers, that's 5s vs 50 minutes.
4. **Testability** — Every rule can be unit-tested with mock data.

The LLM generates narratives AFTER the deterministic verdict is computed. It never changes the verdict.

### ADR-2: Why Skip Narratives in Batch Mode

For a 1000-customer batch:
- With narratives for all: ~4000 LLM calls × 3s = 200 minutes
- With narratives for UNJUSTIFIED only (~15%): ~150 LLM calls × 3s = 7.5 minutes
- With no narratives: 0 LLM calls = 0 minutes

The structured `rule_results` array is self-explanatory for batch review. Narratives add value only for edge cases that need human review. Default: generate narratives only for UNJUSTIFIED verdicts.

### ADR-3: Why PolicyRule as Python Config (Not Database)

For POC, Python config (`config/policy_rules.py`) is correct because:
- Version controlled via git (same as thresholds.py)
- Type-checked at import time
- No database dependency
- Engineers can review rule changes in PR

Tier 2 adds document-based policy loading for non-engineer users. But the runtime representation is still the same `PolicyRule` dataclass — the loader converts documents into rules, it doesn't replace the engine.

### ADR-4: Why ProcessPoolExecutor (Not asyncio) for Batch

Policy evaluation is CPU-bound (Python dict lookups, comparisons). `asyncio` doesn't help with CPU work — it helps with I/O waits. `ProcessPoolExecutor` distributes CPU work across cores.

For LLM narrative generation (I/O-bound, waiting for Ollama), we DO use `asyncio.gather()` — that's where concurrency matters.

### ADR-5: Why Separate Module (`pipeline/policy/`) Not Inside Reports

Policy judgment is a different concern from report generation:
- Reports describe WHAT the customer's financial profile looks like
- Policy judgment evaluates WHETHER an offer is appropriate given that profile

They consume the same data but serve different audiences:
- Reports → credit analysts reviewing a customer
- Judgments → audit/compliance reviewing an offer decision

Keeping them separate means policy rules can change independently of report format, and batch judgment runs don't require report rendering.

### ADR-6: Proposed FOIR Calculation

The most critical policy rule is FOIR (Fixed Obligations to Income Ratio). The system computes it as:

```
proposed_foir = (existing_emi + rent + proposed_new_emi) / salary × 100
```

This uses the **existing** obligations from `CustomerReport` plus the **proposed** EMI from the `LoanOffer`. The `proposed_new_emi` is either:
1. `offer.emi_amount` if provided, or
2. `offer.sanctioned_amount / offer.tenure_months` as a rough estimate

This ensures the policy evaluation considers the INCREMENTAL impact of the new loan, not just the current state.

---

## Data Flow Summary

```
                    ┌──────────────┐
                    │  LoanOffer   │  (from CSV / API / chat query)
                    │  (amount,    │
                    │   rate,      │
                    │   tenure)    │
                    └──────┬───────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    POLICY ENGINE                              │
│                                                               │
│  ┌────────────────┐  ┌───────────────┐  ┌────────────────┐  │
│  │ CustomerReport │  │ BureauReport  │  │ Tradeline      │  │
│  │ (banking data) │  │ (bureau data) │  │ Features       │  │
│  └───────┬────────┘  └───────┬───────┘  └───────┬────────┘  │
│          │                   │                   │            │
│          └───────────────────┼───────────────────┘            │
│                              ▼                                │
│              ┌───────────────────────────┐                    │
│              │  Evaluation Context       │                    │
│              │  (flattened dot-path      │                    │
│              │   accessible dict)        │                    │
│              └────────────┬──────────────┘                    │
│                           │                                   │
│                           ▼                                   │
│              ┌───────────────────────────┐                    │
│              │  Policy Rules             │                    │
│              │  (config/policy_rules.py) │                    │
│              │  [PL_001, PL_002, ...]    │                    │
│              └────────────┬──────────────┘                    │
│                           │                                   │
│                           ▼                                   │
│              ┌───────────────────────────┐                    │
│              │  Rule-by-Rule Evaluation  │  ← DETERMINISTIC  │
│              │  (pass/fail per rule)     │                    │
│              └────────────┬──────────────┘                    │
│                           │                                   │
│                           ▼                                   │
│              ┌───────────────────────────┐                    │
│              │  Verdict Aggregation      │                    │
│              │  JUSTIFIED / UNJUSTIFIED  │                    │
│              │  / PARTIALLY_JUSTIFIED    │                    │
│              └────────────┬──────────────┘                    │
│                           │                                   │
└───────────────────────────┼───────────────────────────────── ┘
                            │
                            ▼
               ┌───────────────────────────┐
               │  PolicyJudgment           │  ← STRUCTURED OUTPUT
               │  (verdict, rule_results,  │
               │   flags, adjustments)     │
               └────────────┬──────────────┘
                            │
                     ┌──────┴──────┐
                     ▼             ▼
            ┌──────────────┐  ┌──────────────────┐
            │  LLM         │  │  Batch Analytics │
            │  Narrative   │  │  (aggregated     │
            │  (optional)  │  │   patterns)      │
            └──────────────┘  └──────────────────┘
```

---

*Plan generated from full codebase analysis — 2026-03*
*Follows existing architecture: deterministic core, LLM periphery, schema-first, fail-soft*
