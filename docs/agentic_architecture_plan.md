# Hybrid Agentic Architecture Plan

> **Classification:** Architecture Transformation Plan
> **Scope:** Convert deterministic pipeline to hybrid agentic system
> **Principle:** Keep the deterministic core, add agentic planning on top

---

## Table of Contents

1. [Why Hybrid, Not Fully Agentic](#1-why-hybrid-not-fully-agentic)
2. [Current Architecture vs Target Architecture](#2-current-architecture-vs-target-architecture)
3. [What "Hybrid Agentic" Means for This System](#3-what-hybrid-agentic-means-for-this-system)
4. [Detailed Design — The Agentic Planner](#4-detailed-design--the-agentic-planner)
5. [Tool Descriptions for the Agent](#5-tool-descriptions-for-the-agent)
6. [Agentic Loop Design](#6-agentic-loop-design)
7. [Guardrails & Safety](#7-guardrails--safety)
8. [Orchestrator Transformation](#8-orchestrator-transformation)
9. [New Capabilities Unlocked](#9-new-capabilities-unlocked)
10. [Schema Changes](#10-schema-changes)
11. [Implementation Steps](#11-implementation-steps)
12. [Examples — Before and After](#12-examples--before-and-after)

---

## 1. Why Hybrid, Not Fully Agentic

### The Current System's Strength

The deterministic core (tools, extractors, thresholds, renderers) is the system's most valuable property. Every analytics function is pure Python, every risk rule is auditable, every report section is reproducible. A fully agentic system where the LLM decides WHAT to compute would destroy these guarantees.

### What's Actually Wrong with the Current Planning

The current system has a **rigid 1:1 intent→tool mapping**. Every query must fit exactly one of 28 IntentType enum values, and each intent maps to a fixed set of tools. This creates three problems:

**Problem 1 — Multi-Step Queries Are Impossible**
```
User: "Show me customer 5004898's salary and check if they have betting transactions,
       then compare their EMI to rent spending"
```
Current system: This maps to... nothing. It requires three different intents (INCOME_STABILITY + CATEGORY_PRESENCE_LOOKUP + COMPARE_CATEGORIES) but the parser can only extract ONE intent per query.

**Problem 2 — Context-Dependent Tool Selection Is Missing**
```
User: "Is this customer risky?"
```
Current system: Maps to FINANCIAL_OVERVIEW → runs `get_total_income`, `debit_total`, `top_spending_categories`. But a knowledgeable analyst would also check bureau delinquency, event detection, category presence for betting/gambling, and income stability. The fixed map can't reason about WHAT tools are appropriate for open-ended questions.

**Problem 3 — Follow-Up Reasoning Is Absent**
```
User: "Check if customer 5004898 has any credit cards"
Agent: "Yes, 2 credit cards with 85% utilization"
User: "That's high. What about their personal loan situation?"
```
Current system: The follow-up works (session customer ID), but the agent can't reason about the previous answer to inform the next query. It treats each query in isolation.

### The Hybrid Approach

Keep all deterministic tools and validations. Replace ONLY the planner with an LLM-based agentic planner that:
1. Understands the available tools and their capabilities
2. Can compose multi-tool plans for complex queries
3. Can reason about which tools are relevant for open-ended questions
4. Falls back to the deterministic INTENT_TOOL_MAP when confident
5. Respects the same safety limits (MAX_TOOLS_PER_QUERY, validation checks)

```
BEFORE:  Query → IntentParser → INTENT_TOOL_MAP[intent] → fixed tools → execute
AFTER:   Query → IntentParser → AgenticPlanner(intent, tools, context) → reasoned plan → execute
                                      ↓ fallback
                                INTENT_TOOL_MAP[intent] (for high-confidence single-intent queries)
```

---

## 2. Current Architecture vs Target Architecture

### Current (Fully Deterministic Planning)

```
User Query
    │
    ▼
IntentParser (LLM → JSON)
    │ produces: ParsedIntent (single intent, single customer, single category)
    ▼
QueryPlanner (PURE PYTHON)
    │ validates fields
    │ looks up: INTENT_TOOL_MAP[intent] → ["tool_a", "tool_b"]
    │ builds: [{"tool": "tool_a", "args": {...}}, {"tool": "tool_b", "args": {...}}]
    ▼
ToolExecutor
    │ runs tools sequentially
    ▼
ResponseExplainer (LLM → streaming text)
```

**Limitation:** One intent → one fixed tool set. No reasoning about what tools to use.

### Target (Hybrid Agentic Planning)

```
User Query
    │
    ▼
IntentParser (LLM → JSON)   ──────── unchanged
    │ produces: ParsedIntent
    ▼
┌─────────────────────────────────────────────────────┐
│              AGENTIC PLANNER (NEW)                    │
│                                                       │
│  Input: ParsedIntent + tool_descriptions + context    │
│                                                       │
│  ┌─────────────────────┐                              │
│  │ Decision Gate        │                              │
│  │                     │                              │
│  │ IF high-confidence  │──→ INTENT_TOOL_MAP[intent]   │
│  │    single intent    │    (deterministic fast path)  │
│  │                     │                              │
│  │ ELSE                │──→ LLM Agentic Planning      │
│  │    (multi-step,     │    (reason about tools)       │
│  │     ambiguous,      │                              │
│  │     open-ended)     │                              │
│  └─────────────────────┘                              │
│                                                       │
│  Output: ExecutionPlan (ordered tool list + reasoning) │
└──────────────────────────┬──────────────────────────── ┘
                           │
                           ▼
         ToolExecutor   ──────── unchanged (mostly)
                           │
                           ▼ (NEW: optional)
         ┌─────────────────────────────────┐
         │  Observation → Re-Plan Loop      │
         │  If tool result suggests more    │
         │  tools needed, agent can extend  │
         │  the plan (max 2 re-plans)       │
         └─────────────────────────────────┘
                           │
                           ▼
         ResponseExplainer  ──────── unchanged
```

---

## 3. What "Hybrid Agentic" Means for This System

### Three Modes of Operation

**Mode 1 — Deterministic Fast Path (80% of queries)**

For high-confidence, single-intent queries like "Total spending for customer 5004898", the system uses the existing INTENT_TOOL_MAP. No LLM planning call, no latency overhead. This is the current behavior, preserved exactly.

**Trigger:** `intent.confidence >= 0.8 AND intent.intent != UNKNOWN AND intent.intent in SIMPLE_INTENTS`

Where `SIMPLE_INTENTS` = all intents that map to 1-2 tools and don't benefit from reasoning.

**Mode 2 — Agentic Single-Pass Planning (15% of queries)**

For medium-confidence, open-ended, or multi-step queries, the agentic planner reasons about which tools to call. It produces a plan in one LLM call, then the executor runs it.

**Trigger:** `intent.confidence < 0.8 OR intent.intent in COMPLEX_INTENTS OR multi-step detected`

Example queries:
- "Is this customer risky?" → Agent reasons: need income_stability + category_presence(betting) + bureau_delinquency + anomaly_detection
- "Give me a complete picture of customer 5004898" → Agent reasons: need financial_overview tools + category_presence(betting) + bureau_overview + event detection
- "Compare this customer's banking and bureau profile" → Agent reasons: need customer_report + bureau_overview

**Mode 3 — Agentic Re-Planning Loop (5% of queries)**

For queries where the first tool's result changes what should happen next. The agent observes the first result and decides whether to call more tools.

**Trigger:** Agent explicitly requests re-planning in its output, or a tool result contains a flag suggesting follow-up.

Example:
```
User: "Check if customer 5004898 has any red flags"

Plan 1: [bureau_delinquency_check, category_presence("betting"), anomaly_detection]
         ↓ execute
Result:  delinquency_check → {has_dpd: true, max_dpd: 45}
         ↓ agent observes
Re-Plan: "DPD detected. Adding bureau_overview for full tradeline context"
Plan 2:  [bureau_overview]
         ↓ execute
Result:  bureau_overview → {total_tradelines: 8, ...}
         ↓ all results combined
Explainer: generates comprehensive answer from all tool results
```

Maximum re-plan iterations: **2** (safety cap).

---

## 4. Detailed Design — The Agentic Planner

### 4.1 New Module: `pipeline/core/agentic_planner.py`

This module replaces the planning logic in `planner.py` while keeping the validation logic intact.

```python
"""Agentic query planner — LLM-based tool selection with deterministic fallback.

The agentic planner receives a ParsedIntent and a registry of available tools,
then decides which tools to call and in what order. For simple, high-confidence
queries it falls back to the deterministic INTENT_TOOL_MAP.

Architecture:
    IntentParser → AgenticPlanner → ExecutionPlan → ToolExecutor
                        ↓ (fallback)
                   INTENT_TOOL_MAP (deterministic)
"""
```

### 4.2 Tool Registry Schema

Each tool needs a structured description the agent can reason about. This is NOT the tool function itself — it's metadata the LLM reads to understand what each tool does.

```python
@dataclass
class ToolDescription:
    """Metadata describing a tool's capabilities for the agentic planner."""
    name: str                    # Tool function name (matches executor tool_map key)
    description: str             # What this tool does (1-2 sentences)
    data_source: str             # "banking" | "bureau" | "both"
    input_args: List[str]        # Required argument names
    output_fields: List[str]     # Key fields in the return dict
    use_when: str                # When this tool is appropriate (1 sentence)
    cost: str                    # "low" (fast) | "medium" | "high" (slow, LLM-heavy)
```

### 4.3 Decision Gate Logic

```python
# Simple intents that should ALWAYS use deterministic path
DETERMINISTIC_INTENTS = {
    IntentType.TOTAL_SPENDING,
    IntentType.TOTAL_INCOME,
    IntentType.SPENDING_BY_CATEGORY,
    IntentType.ALL_CATEGORIES_SPENDING,
    IntentType.TOP_CATEGORIES,
    IntentType.SPENDING_IN_PERIOD,
    IntentType.LIST_CUSTOMERS,
    IntentType.LIST_CATEGORIES,
    IntentType.CUSTOMER_REPORT,       # Fixed pipeline, no reasoning needed
    IntentType.BUREAU_REPORT,         # Fixed pipeline, no reasoning needed
    IntentType.COMBINED_REPORT,       # Fixed pipeline, no reasoning needed
    IntentType.COMPARE_CATEGORIES,
    IntentType.CATEGORY_PRESENCE_LOOKUP,
    IntentType.BUREAU_CREDIT_CARDS,
    IntentType.BUREAU_LOAN_COUNT,
    IntentType.BUREAU_DELINQUENCY,
}

# Intents that benefit from agentic reasoning
AGENTIC_INTENTS = {
    IntentType.FINANCIAL_OVERVIEW,     # Could benefit from more tools
    IntentType.LENDER_PROFILE,         # Open-ended assessment
    IntentType.CREDIT_ANALYSIS,        # Could add context tools
    IntentType.DEBIT_ANALYSIS,         # Could add context tools
    IntentType.ANOMALY_DETECTION,      # Follow-up reasoning
    IntentType.INCOME_STABILITY,       # Could add salary context
    IntentType.BUREAU_OVERVIEW,        # Could add banking context
    IntentType.UNKNOWN,                # Must reason about what to do
}

def should_use_agentic_planning(intent: ParsedIntent) -> bool:
    """Decide whether to use LLM-based planning or deterministic mapping."""

    # 1. Unknown intent → must reason
    if intent.intent == IntentType.UNKNOWN:
        return True

    # 2. Low confidence → parser wasn't sure, let agent reason
    if intent.confidence < 0.7:
        return True

    # 3. Multi-step query detected (heuristic: multiple question marks, "and", "then")
    query_lower = intent.raw_query.lower()
    multi_step_signals = ["and also", "then ", "additionally", "plus ", " and check",
                          "as well as", "along with", "followed by"]
    if any(signal in query_lower for signal in multi_step_signals):
        return True

    # 4. Open-ended queries (heuristic: risk-related, assessment-related)
    open_ended_signals = ["risky", "risk", "red flag", "safe", "creditworth",
                          "overall", "complete picture", "summary of everything",
                          "assess", "evaluate", "how does this customer look"]
    if any(signal in query_lower for signal in open_ended_signals):
        return True

    # 5. Intent is in the agentic set
    if intent.intent in AGENTIC_INTENTS:
        return True

    # 6. Default: use deterministic path
    return False
```

### 4.4 Agentic Planner Prompt

The core of the agentic planner — the prompt that tells the LLM how to select tools.

```python
AGENTIC_PLANNER_PROMPT = """You are a financial analysis planning agent. Your job is to select
which tools to call (and in what order) to answer the user's question.

USER QUERY: {query}

PARSED CONTEXT:
- Detected intent: {intent}
- Customer ID: {customer_id}
- Category: {category}
- Confidence: {confidence}

AVAILABLE TOOLS:
{tool_descriptions}

CUSTOMER DATA AVAILABILITY:
- Banking data available: {has_banking}
- Bureau data available: {has_bureau}

RULES:
1. Select 1-5 tools that together answer the user's question completely
2. Order matters — put foundational data tools first, follow-up tools after
3. Do NOT select tools for data sources the customer doesn't exist in
4. If the query is simple and maps to a single tool, select just that one tool
5. If the query is open-ended ("is this customer risky?"), select tools that cover
   different risk dimensions: income, spending patterns, bureau status, anomalies
6. NEVER select report generation tools (generate_customer_report, generate_bureau_report,
   generate_combined_report) unless the user explicitly asks for a report/PDF
7. Prefer low-cost tools over high-cost tools when both give the needed information
8. If a category is mentioned, include category_presence_lookup for that category

RESPOND WITH ONLY THIS JSON (no markdown, no explanation):
{{"plan": [{{"tool": "<tool_name>", "args": {{"<arg>": "<value>"}}, "reason": "<why this tool>"}}, ...], "reasoning": "<1 sentence overall strategy>"}}"""
```

### 4.5 Plan Parsing and Validation

After the LLM produces a plan, validate it against the same rules the deterministic planner uses:

```python
def _validate_agentic_plan(
    plan: List[Dict],
    intent: ParsedIntent,
    valid_tools: set,
    valid_customers: set,
    valid_bureau_customers: set,
) -> Tuple[List[Dict], List[str]]:
    """Validate and sanitize the LLM-generated plan.

    Returns:
        (validated_plan, warnings)
    """
    validated = []
    warnings = []

    for step in plan:
        tool_name = step.get("tool", "")
        args = step.get("args", {})

        # Check tool exists
        if tool_name not in valid_tools:
            warnings.append(f"Unknown tool '{tool_name}' — skipped")
            continue

        # Check customer_id is valid for the tool's data source
        cid = args.get("customer_id", intent.customer_id)
        if cid is not None:
            tool_desc = TOOL_REGISTRY.get(tool_name)
            if tool_desc and tool_desc.data_source == "bureau":
                if cid not in valid_bureau_customers:
                    warnings.append(f"Customer {cid} not in bureau data — skipping {tool_name}")
                    continue
            elif tool_desc and tool_desc.data_source == "banking":
                if cid not in valid_customers:
                    warnings.append(f"Customer {cid} not in banking data — skipping {tool_name}")
                    continue

        # Ensure customer_id is set
        if "customer_id" not in args and intent.customer_id is not None:
            args["customer_id"] = intent.customer_id

        validated.append({"tool": tool_name, "args": args})

    # Safety cap
    if len(validated) > MAX_TOOLS_PER_QUERY:
        warnings.append(f"Plan truncated from {len(validated)} to {MAX_TOOLS_PER_QUERY} tools")
        validated = validated[:MAX_TOOLS_PER_QUERY]

    return validated, warnings
```

### 4.6 Fallback Chain

If the agentic planner fails (LLM timeout, invalid JSON, empty plan), fall back gracefully:

```
Agentic LLM Plan
    │ fails?
    ▼
INTENT_TOOL_MAP[intent]     ← deterministic fallback (current system)
    │ intent is UNKNOWN?
    ▼
Default safe plan: [get_total_income, debit_total, top_spending_categories]
```

```python
def create_plan(self, intent: ParsedIntent) -> Tuple[List[Dict], str]:
    """Create execution plan — agentic or deterministic."""

    # Validation (unchanged — same checks as current planner)
    error = self._validate_intent(intent)
    if error:
        return [], error

    # Decision gate
    if should_use_agentic_planning(intent):
        try:
            plan, reasoning = self._agentic_plan(intent)
            if plan:
                logger.info("Agentic plan: %s (reason: %s)",
                           [p["tool"] for p in plan], reasoning)
                return plan, ""
        except Exception as e:
            logger.warning("Agentic planning failed, falling back: %s", e)

    # Deterministic fallback (current behavior)
    tools = INTENT_TOOL_MAP.get(intent.intent, [])
    if not tools and intent.intent == IntentType.UNKNOWN:
        return [], "Could not understand the query"
    plan = self._build_plan(intent, tools)
    return plan, ""
```

---

## 5. Tool Descriptions for the Agent

Every tool in the executor's `tool_map` needs a description the agent can read. These are stored in a new config file.

### New File: `config/tool_registry.py`

```python
"""Tool descriptions for the agentic planner.

Each tool has metadata describing what it does, when to use it,
and what arguments it needs. The agent reads these descriptions
to decide which tools to call.
"""

from dataclasses import dataclass, field
from typing import List

@dataclass
class ToolDescription:
    name: str
    description: str
    data_source: str              # "banking" | "bureau" | "both"
    input_args: List[str]
    optional_args: List[str] = field(default_factory=list)
    output_summary: str = ""      # What the output contains
    use_when: str = ""            # When this tool is appropriate
    cost: str = "low"             # "low" | "medium" | "high"


TOOL_REGISTRY = {
    # ─── Banking Analytics (low cost, fast) ───────────────────────────
    "debit_total": ToolDescription(
        name="debit_total",
        description="Returns total spending amount and month-wise spending breakdown for a customer.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="total_spending, transaction_count, month_wise_spending",
        use_when="User asks about total spending, expenses, or outflow",
        cost="low",
    ),
    "get_total_income": ToolDescription(
        name="get_total_income",
        description="Returns total income (credits) amount and transaction count for a customer.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="total_income, transaction_count",
        use_when="User asks about income, earnings, credits, or inflow",
        cost="low",
    ),
    "get_spending_by_category": ToolDescription(
        name="get_spending_by_category",
        description="Returns spending amount for a specific category, or all categories if no category specified.",
        data_source="banking",
        input_args=["customer_id"],
        optional_args=["category"],
        output_summary="category_spending or all_categories_spending, transaction_count",
        use_when="User asks about spending in a specific category or wants category breakdown",
        cost="low",
    ),
    "top_spending_categories": ToolDescription(
        name="top_spending_categories",
        description="Returns the top N spending categories by amount for a customer.",
        data_source="banking",
        input_args=["customer_id"],
        optional_args=["top_n"],
        output_summary="top_categories (dict of category→amount)",
        use_when="User asks about top spending areas, biggest expense categories",
        cost="low",
    ),
    "spending_in_date_range": ToolDescription(
        name="spending_in_date_range",
        description="Returns spending within a specific date range for a customer.",
        data_source="banking",
        input_args=["customer_id", "start_date", "end_date"],
        output_summary="total_spending, transaction_count, category_breakdown",
        use_when="User asks about spending in a specific time period",
        cost="low",
    ),
    "get_cash_flow": ToolDescription(
        name="get_cash_flow",
        description="Returns monthly cashflow breakdown: inflow, outflow, and net for each month.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="monthly_cashflow [{month, inflow, outflow, net}], averages",
        use_when="User asks about cashflow, inflow vs outflow, monthly financial health",
        cost="low",
    ),
    "get_income_stability": ToolDescription(
        name="get_income_stability",
        description="Analyzes income consistency: coefficient of variation, gap analysis, regularity score.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="stability_score, cv, avg_income, income_gaps, is_regular",
        use_when="User asks about income stability, salary consistency, income regularity, or risk assessment",
        cost="low",
    ),
    "get_credit_statistics": ToolDescription(
        name="get_credit_statistics",
        description="Returns detailed credit/income statistics: max, min, avg, median, percentiles, sources.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="max_credit, avg_credit, median_credit, top_sources",
        use_when="User asks about credit patterns, income analysis, largest credits",
        cost="low",
    ),
    "get_debit_statistics": ToolDescription(
        name="get_debit_statistics",
        description="Returns detailed debit/spending statistics: max, min, avg, median, percentiles.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="max_debit, avg_debit, median_debit, percentiles",
        use_when="User asks about spending patterns, largest debits",
        cost="low",
    ),
    "get_transaction_counts": ToolDescription(
        name="get_transaction_counts",
        description="Returns transaction count breakdowns by direction, category, and month.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="total_count, debit_count, credit_count, by_category, by_month",
        use_when="User asks about transaction volumes, activity levels",
        cost="low",
    ),
    "get_balance_trend": ToolDescription(
        name="get_balance_trend",
        description="Returns balance progression over time (running balance by month).",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="monthly_balance_trend, overall_trend_direction",
        use_when="User asks about balance trends, account growth/decline",
        cost="low",
    ),
    "detect_anomalies": ToolDescription(
        name="detect_anomalies",
        description="Finds unusual/spike transactions that deviate significantly from normal patterns.",
        data_source="banking",
        input_args=["customer_id"],
        optional_args=["threshold_std"],
        output_summary="anomalies [{date, amount, category, z_score}]",
        use_when="User asks about unusual transactions, spikes, anomalies, red flags in spending",
        cost="low",
    ),
    "generate_lender_profile": ToolDescription(
        name="generate_lender_profile",
        description="Generates a creditworthiness assessment with income stability, spending discipline, and risk indicators.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="creditworthiness_score, income_stability, spending_discipline, risk_indicators",
        use_when="User asks about creditworthiness, lending risk, loan eligibility assessment",
        cost="medium",
    ),
    "category_presence_lookup": ToolDescription(
        name="category_presence_lookup",
        description="Checks whether a customer has transactions in a specific category (e.g., betting, gambling, rent, salary). Returns presence flag, total amount, and up to 10 supporting transactions.",
        data_source="banking",
        input_args=["customer_id", "category"],
        output_summary="present (bool), total_amount, transaction_count, supporting_transactions",
        use_when="User asks if customer has specific type of transactions: betting, gambling, rent, insurance, salary. Also useful for risk assessment — check betting/gambling presence.",
        cost="low",
    ),
    "list_customers": ToolDescription(
        name="list_customers",
        description="Returns list of all customer IDs in the banking dataset.",
        data_source="banking",
        input_args=[],
        output_summary="customers (list of IDs)",
        use_when="User asks to list or see all customers",
        cost="low",
    ),
    "list_categories": ToolDescription(
        name="list_categories",
        description="Returns list of all transaction categories in the dataset.",
        data_source="banking",
        input_args=[],
        output_summary="categories (list of category names)",
        use_when="User asks to list or see all categories",
        cost="low",
    ),

    # ─── Report Generation (high cost, slow) ──────────────────────────
    "generate_customer_report": ToolDescription(
        name="generate_customer_report",
        description="Generates a full customer banking report PDF with salary, EMI, rent, cashflow, categories, events, and LLM executive summary.",
        data_source="banking",
        input_args=["customer_id"],
        output_summary="pdf_path, html_path, full report data",
        use_when="User explicitly asks to generate a report, PDF, or comprehensive banking document",
        cost="high",
    ),
    "generate_bureau_report": ToolDescription(
        name="generate_bureau_report",
        description="Generates a full bureau/CIBIL tradeline report PDF with per-loan-type analysis, key findings, and LLM narrative.",
        data_source="bureau",
        input_args=["customer_id"],
        output_summary="pdf_path, html_path, bureau report data",
        use_when="User explicitly asks to generate a bureau report, CIBIL report, or tradeline report",
        cost="high",
    ),
    "generate_combined_report": ToolDescription(
        name="generate_combined_report",
        description="Generates a combined banking + bureau report PDF with synthesized executive summary.",
        data_source="both",
        input_args=["customer_id"],
        output_summary="pdf_path, html_path, combined report data",
        use_when="User explicitly asks for a combined/merged report covering both banking and bureau",
        cost="high",
    ),

    # ─── Bureau Chat Tools (low cost, fast) ────────────────────────────
    "bureau_credit_card_info": ToolDescription(
        name="bureau_credit_card_info",
        description="Returns credit card count, utilization percentage, and outstanding amounts from bureau data.",
        data_source="bureau",
        input_args=["customer_id"],
        output_summary="has_cc, cc_count, utilization_pct, outstanding",
        use_when="User asks about credit cards, CC utilization, or CC count",
        cost="low",
    ),
    "bureau_loan_type_info": ToolDescription(
        name="bureau_loan_type_info",
        description="Returns count and details of a specific loan type (personal loan, home loan, etc.) from bureau data.",
        data_source="bureau",
        input_args=["customer_id"],
        optional_args=["loan_type"],
        output_summary="loan_count, active_count, total_sanctioned, total_outstanding",
        use_when="User asks how many loans of a type, loan details, or specific product info",
        cost="low",
    ),
    "bureau_delinquency_check": ToolDescription(
        name="bureau_delinquency_check",
        description="Checks if any loan is delinquent (has DPD > 0) and returns delinquency details.",
        data_source="bureau",
        input_args=["customer_id"],
        optional_args=["loan_type"],
        output_summary="has_delinquency, max_dpd, delinquent_loans",
        use_when="User asks about delinquency, DPD, overdue payments, or loan repayment issues",
        cost="low",
    ),
    "bureau_overview": ToolDescription(
        name="bureau_overview",
        description="Returns a high-level bureau portfolio summary: total tradelines, exposure, outstanding, product mix.",
        data_source="bureau",
        input_args=["customer_id"],
        output_summary="total_tradelines, live, closed, sanctioned, outstanding, product_types",
        use_when="User asks for bureau summary, tradeline overview, or general credit portfolio status",
        cost="low",
    ),
}


def format_tool_descriptions_for_prompt(
    available_tools: List[str] = None,
    has_banking: bool = True,
    has_bureau: bool = True,
) -> str:
    """Format tool descriptions as a block for the agentic planner prompt.

    Filters by data source availability — if customer has no bureau data,
    bureau tools are excluded from the prompt.
    """
    lines = []
    for name, desc in TOOL_REGISTRY.items():
        if available_tools and name not in available_tools:
            continue
        if desc.data_source == "bureau" and not has_bureau:
            continue
        if desc.data_source == "banking" and not has_banking:
            continue

        args_str = ", ".join(desc.input_args)
        opt_str = f" (optional: {', '.join(desc.optional_args)})" if desc.optional_args else ""
        lines.append(
            f"- {name}({args_str}{opt_str}): {desc.description}\n"
            f"  Use when: {desc.use_when} | Cost: {desc.cost}"
        )
    return "\n".join(lines)
```

---

## 6. Agentic Loop Design

### 6.1 Single-Pass Agentic Planning (Mode 2)

For most agentic queries, one planning LLM call is sufficient:

```
IntentParser
    ↓
AgenticPlanner._agentic_plan(intent)
    ├── Build prompt with tool_descriptions + intent + context
    ├── LLM call (mistral, format=json, temperature=0)
    ├── Parse JSON response → plan list
    ├── Validate plan (tools exist, customer valid, args correct)
    ├── Fallback to INTENT_TOOL_MAP if validation fails
    ↓
ToolExecutor.execute(plan)
    ↓
ResponseExplainer.stream_explain(intent, results)
```

### 6.2 Re-Planning Loop (Mode 3)

For queries that need follow-up reasoning based on initial results:

```
AgenticPlanner._agentic_plan(intent)
    ↓
ToolExecutor.execute(initial_plan)
    ↓
AgenticPlanner._should_replan(intent, results)
    ├── Check: any tool failed? → maybe retry with different args
    ├── Check: results contain flags suggesting follow-up?
    │   e.g., delinquency_check returns has_dpd=True → add bureau_overview
    │   e.g., category_presence(betting) returns present=True → add anomaly_detection
    ├── Check: agent's original plan included "needs_followup" flag?
    ↓
IF re-plan needed:
    AgenticPlanner._replan(intent, results, original_plan)
        ├── New prompt with: original query + results so far + "what else is needed?"
        ├── LLM call → additional tools
        ├── Validate (no duplicates, max total tools)
        ↓
    ToolExecutor.execute(additional_plan)
    ↓
    Merge all results
    ↓
ResponseExplainer.stream_explain(intent, all_results)
```

### 6.3 Re-Planning Prompt

```python
REPLAN_PROMPT = """You previously planned and executed these tools for the user's query.

USER QUERY: {query}

TOOLS ALREADY EXECUTED:
{executed_summary}

RESULTS OBTAINED:
{results_summary}

Based on these results, do you need any ADDITIONAL tools to fully answer the user's question?

RULES:
1. Do NOT re-run tools already executed
2. Only add tools if the results clearly indicate a gap
3. Maximum 2 additional tools
4. If the results are sufficient, return an empty plan

RESPOND WITH ONLY THIS JSON:
{{"additional_plan": [{{"tool": "<tool_name>", "args": {{...}}, "reason": "<why>"}}], "sufficient": true/false}}"""
```

### 6.4 Re-Planning Triggers (Deterministic)

Instead of always calling the LLM to decide if re-planning is needed, use deterministic triggers:

```python
REPLAN_TRIGGERS = {
    # If delinquency found and bureau_overview not in original plan
    "bureau_delinquency_check": lambda result: (
        result.get("has_delinquency", False) and
        "bureau_overview" not in _executed_tools
    ),
    # If betting/gambling found and anomaly_detection not in original plan
    "category_presence_lookup": lambda result: (
        result.get("present", False) and
        result.get("category", "").lower() in ("betting", "gambling", "betting_gaming") and
        "detect_anomalies" not in _executed_tools
    ),
    # If income instability detected
    "get_income_stability": lambda result: (
        result.get("stability_score", 1.0) < 0.5 and
        "get_cash_flow" not in _executed_tools
    ),
}
```

This avoids an extra LLM call for the re-plan decision. The LLM is only called if deterministic triggers fire AND additional tools need argument resolution.

---

## 7. Guardrails & Safety

### 7.1 Tool Execution Limits

```python
MAX_TOOLS_PER_QUERY = 7          # Raised from 5 to allow agent flexibility
MAX_REPLAN_ITERATIONS = 2         # Maximum re-plan loops
MAX_TOTAL_TOOLS = 10              # Absolute cap across all plans
AGENTIC_PLANNING_TIMEOUT = 10     # Seconds before falling back to deterministic
```

### 7.2 Prevent Report Generation Unless Explicitly Asked

The agent should NEVER generate a full PDF report (expensive, 15-30s) unless the user explicitly asked for it. This is enforced at two levels:

**Level 1 — Prompt instruction** (in AGENTIC_PLANNER_PROMPT):
```
"NEVER select report generation tools (generate_customer_report, generate_bureau_report,
 generate_combined_report) unless the user explicitly asks for a report/PDF"
```

**Level 2 — Code guard** (in plan validation):
```python
REPORT_TOOLS = {"generate_customer_report", "generate_bureau_report", "generate_combined_report"}
REPORT_KEYWORDS = ["report", "pdf", "generate report", "create report", "full report"]

for step in plan:
    if step["tool"] in REPORT_TOOLS:
        if not any(kw in intent.raw_query.lower() for kw in REPORT_KEYWORDS):
            warnings.append(f"Agent tried to generate report without user request — blocked")
            plan.remove(step)
```

### 7.3 Cost Awareness

The agent prompt includes tool cost labels. Add a total cost check:

```python
COST_MAP = {"low": 1, "medium": 3, "high": 10}
MAX_PLAN_COST = 15

def _check_plan_cost(plan: List[Dict]) -> bool:
    total = sum(COST_MAP.get(TOOL_REGISTRY[p["tool"]].cost, 1) for p in plan)
    return total <= MAX_PLAN_COST
```

### 7.4 Deterministic Validation Unchanged

All existing validation in `QueryPlanner._validate_intent()` remains intact:
- Customer ID exists in dataset
- Category is valid
- Date range is logical
- Required fields are present

The agentic planner runs AFTER validation, not instead of it.

### 7.5 Audit Trail for Agentic Decisions

Log the agent's reasoning alongside the plan:

```python
# In AuditLog schema, add:
planning_mode: str = "deterministic"       # "deterministic" | "agentic" | "agentic_replan"
agent_reasoning: Optional[str] = None      # The agent's 1-sentence strategy
agent_plan_raw: Optional[str] = None       # Raw JSON from agent LLM
```

---

## 8. Orchestrator Transformation

### 8.1 Updated TransactionPipeline

The orchestrator changes minimally — the agentic planning is encapsulated in the planner:

```python
class TransactionPipeline:
    def __init__(self, ...):
        self.parser = IntentParser(model_name=parser_model)
        self.planner = HybridPlanner()          # NEW — replaces QueryPlanner
        self.executor = ToolExecutor()
        self.explainer = ResponseExplainer(...)
        self.audit = AuditLogger()
        ...

    def query_stream(self, user_query: str) -> Iterator[str]:
        # Phase 1: Parse intent — UNCHANGED
        intent = self.parser.parse(user_query)
        self.resolve_customer_id(intent)

        # Phase 2: Create plan — NOW HYBRID
        plan, error, planning_meta = self.planner.create_plan(intent)
        if error:
            yield error
            return

        # Phase 3: Execute initial plan — UNCHANGED
        results = self.executor.execute(plan)

        # Phase 3.5: Re-plan if needed — NEW
        if planning_meta.get("mode") == "agentic":
            additional_plan = self.planner.check_replan(intent, results, plan)
            if additional_plan:
                additional_results = self.executor.execute(additional_plan)
                results.extend(additional_results)

        # Phase 4: Transaction insights — UNCHANGED
        transaction_insights = None
        if self._should_get_insights(intent):
            transaction_insights = get_transaction_insights_if_needed(intent.customer_id)

        # Phase 5: Stream explanation — UNCHANGED
        yield from self.explainer.stream_explain(intent, results, transaction_insights)

        # Phase 6: Audit — UPDATED with planning_meta
        ...
```

### 8.2 Session Context for Multi-Turn Agentic Reasoning

Add a lightweight conversation context that the agent can reference:

```python
class SessionContext:
    """Tracks recent tool results for multi-turn reasoning."""

    def __init__(self, max_history: int = 5):
        self.history: List[Dict] = []    # [{query, intent, tools_used, key_findings}]
        self.max_history = max_history

    def add(self, query: str, intent: ParsedIntent, results: List[ToolResult]):
        entry = {
            "query": query,
            "intent": intent.intent.value,
            "customer_id": intent.customer_id,
            "tools_used": [r.tool_name for r in results],
            "key_findings": self._extract_key_findings(results),
        }
        self.history.append(entry)
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def _extract_key_findings(self, results: List[ToolResult]) -> List[str]:
        """Extract 1-line summaries from tool results for context."""
        findings = []
        for r in results:
            if not r.success:
                continue
            d = r.result
            if "has_delinquency" in d:
                findings.append(f"Bureau: DPD={'yes' if d['has_delinquency'] else 'no'}")
            if "present" in d and "category" in d:
                findings.append(f"{d['category']}: {'found' if d['present'] else 'not found'}")
            if "stability_score" in d:
                findings.append(f"Income stability: {d['stability_score']:.2f}")
        return findings

    def format_for_prompt(self) -> str:
        if not self.history:
            return "No previous queries in this session."
        lines = ["RECENT SESSION CONTEXT:"]
        for h in self.history[-3:]:
            lines.append(f"  Q: {h['query'][:80]}")
            lines.append(f"  Tools: {h['tools_used']}")
            if h['key_findings']:
                lines.append(f"  Findings: {', '.join(h['key_findings'])}")
        return "\n".join(lines)
```

---

## 9. New Capabilities Unlocked

### 9.1 Multi-Step Queries (Currently Impossible)

```
User: "Check customer 5004898's income stability and if they have any betting transactions"
```

**Current:** Parser extracts ONE intent (probably INCOME_STABILITY), ignores the betting part.

**Agentic:** Agent plans: `[get_income_stability, category_presence_lookup(betting_gaming)]`

### 9.2 Open-Ended Risk Assessment

```
User: "How risky is customer 5004898?"
```

**Current:** Maps to FINANCIAL_OVERVIEW → `[get_total_income, debit_total, top_spending_categories]`. Misses bureau, anomalies, betting check.

**Agentic:** Agent reasons and plans:
```json
{
  "plan": [
    {"tool": "get_income_stability", "reason": "Check income regularity"},
    {"tool": "detect_anomalies", "reason": "Find unusual transactions"},
    {"tool": "category_presence_lookup", "args": {"category": "betting_gaming"}, "reason": "Check for high-risk spending"},
    {"tool": "bureau_delinquency_check", "reason": "Check repayment history"},
    {"tool": "get_cash_flow", "reason": "Assess cashflow health"}
  ],
  "reasoning": "Risk assessment requires multi-dimensional analysis across banking behavior, anomalies, high-risk categories, and bureau repayment history."
}
```

### 9.3 Follow-Up Context Awareness

```
Turn 1: "Bureau overview for customer 5004898"
Turn 2: "Any red flags in their banking?"
```

**Current:** Turn 2 gets customer ID from session, but agent doesn't know the bureau showed high DPD.

**Agentic:** Agent sees session context showing "Bureau: DPD=yes" from turn 1, and prioritizes:
```json
{
  "plan": [
    {"tool": "detect_anomalies", "reason": "Bureau shows DPD — check for banking anomalies"},
    {"tool": "category_presence_lookup", "args": {"category": "betting_gaming"}, "reason": "Check high-risk category"},
    {"tool": "get_income_stability", "reason": "Verify income consistency given DPD history"}
  ]
}
```

### 9.4 Intelligent Fallback for Unclear Queries

```
User: "Tell me about customer 5004898"
```

**Current:** Maps to UNKNOWN → error "Could not understand the query".

**Agentic:** Agent treats this as an overview request:
```json
{
  "plan": [
    {"tool": "get_cash_flow", "reason": "Basic financial profile"},
    {"tool": "top_spending_categories", "reason": "Spending pattern overview"},
    {"tool": "bureau_overview", "reason": "Credit portfolio summary"}
  ]
}
```

### 9.5 Cross-Data-Source Queries

```
User: "Compare this customer's banking behavior with their bureau profile"
```

**Current:** No intent matches this cross-data query.

**Agentic:** Agent selects tools from both sources:
```json
{
  "plan": [
    {"tool": "get_cash_flow", "reason": "Banking behavior — income and spending"},
    {"tool": "get_income_stability", "reason": "Banking — income consistency"},
    {"tool": "bureau_overview", "reason": "Bureau — credit portfolio status"},
    {"tool": "bureau_delinquency_check", "reason": "Bureau — repayment behavior"}
  ]
}
```

---

## 10. Schema Changes

### 10.1 ExecutionPlan Schema (New)

```python
@dataclass
class ExecutionStep:
    tool: str
    args: Dict[str, Any]
    reason: str = ""                    # Agent's reasoning for this step

@dataclass
class ExecutionPlan:
    steps: List[ExecutionStep]
    mode: str = "deterministic"         # "deterministic" | "agentic" | "agentic_replan"
    reasoning: str = ""                 # Agent's overall strategy
    fallback_used: bool = False         # Whether deterministic fallback was used
```

### 10.2 PipelineResponse Updates

Add planning metadata to the response for UI display:

```python
class PipelineResponse(BaseModel):
    answer: str
    data: Dict[str, Any] = {}
    intent: ParsedIntent
    tools_used: List[str] = []
    success: bool = True
    error: Optional[str] = None
    # NEW fields
    planning_mode: str = "deterministic"
    agent_reasoning: Optional[str] = None
    replan_count: int = 0
```

### 10.3 AuditLog Updates

```python
class AuditLog(BaseModel):
    # ... existing fields ...
    # NEW
    planning_mode: str = "deterministic"
    agent_reasoning: Optional[str] = None
    replan_count: int = 0
    total_tools_executed: int = 0
```

---

## 11. Implementation Steps

### Phase 1 — Foundation (Day 1)

**Step 1: Create `config/tool_registry.py`**
- Define `ToolDescription` dataclass
- Write descriptions for all 24 tools
- Implement `format_tool_descriptions_for_prompt()`
- No existing code changes — purely additive

**Step 2: Create `pipeline/core/agentic_planner.py`**
- Implement `should_use_agentic_planning()` decision gate
- Implement `AgenticPlanner` class with `_agentic_plan()` method
- Implement plan validation (`_validate_agentic_plan()`)
- Add deterministic fallback chain
- No existing code changes yet

### Phase 2 — Hybrid Planner (Day 2)

**Step 3: Create `pipeline/core/hybrid_planner.py`**
- Wraps both `QueryPlanner` (existing) and `AgenticPlanner` (new)
- Implements `create_plan()` with decision gate
- Keeps ALL validation from `QueryPlanner._validate_intent()`
- Falls back to deterministic on any agentic failure

**Step 4: Add agentic planner prompt to `config/prompts.py`**
- `AGENTIC_PLANNER_PROMPT`
- `REPLAN_PROMPT`

**Step 5: Update `config/settings.py`**
- Add `PLANNER_MODEL` (use mistral — same as intent parser, JSON reliable)
- Add `AGENTIC_PLANNING_TIMEOUT`
- Add `ENABLE_AGENTIC_PLANNING` feature flag (default: True)

### Phase 3 — Integration (Day 3)

**Step 6: Update `pipeline/core/orchestrator.py`**
- Replace `QueryPlanner()` with `HybridPlanner()`
- Add re-planning step after initial execution
- Add `SessionContext` for multi-turn awareness
- Update audit logging with planning metadata

**Step 7: Update schemas**
- Add `ExecutionPlan`, `ExecutionStep` to schemas
- Update `PipelineResponse` with planning fields
- Update `AuditLog` with agentic fields

### Phase 4 — Re-Planning (Day 4)

**Step 8: Implement re-planning logic**
- Deterministic re-plan triggers (`REPLAN_TRIGGERS`)
- `AgenticPlanner._replan()` method
- Re-plan prompt and validation
- Total tool cap enforcement

**Step 9: Implement `SessionContext`**
- Multi-turn context tracking
- Key finding extraction from results
- Context formatting for agent prompt

### Phase 5 — Testing & Tuning (Day 5)

**Step 10: Test suite**
- Test decision gate (which queries go agentic vs deterministic)
- Test that all current deterministic queries still work unchanged
- Test multi-step query planning
- Test open-ended query planning
- Test fallback chain (agentic fails → deterministic)
- Test re-planning triggers
- Test cost/limit enforcement
- Test report generation guard

**Step 11: Feature flag**
- `ENABLE_AGENTIC_PLANNING = True/False` in settings
- When False, system behaves exactly as current (zero behavioral change)
- Allows gradual rollout and A/B testing

---

## 12. Examples — Before and After

### Example 1: Simple Query (No Change)

```
User: "Total spending for customer 5004898"

BEFORE: IntentParser → TOTAL_SPENDING → INTENT_TOOL_MAP → [debit_total] → execute
AFTER:  IntentParser → TOTAL_SPENDING (confidence 0.95) → DETERMINISTIC path → [debit_total] → execute

Result: Identical. Fast path. No LLM planning call.
```

### Example 2: Multi-Step Query (New Capability)

```
User: "Show me salary info and check for betting for customer 5004898"

BEFORE: IntentParser → probably INCOME_STABILITY → [get_income_stability] → misses betting
AFTER:  IntentParser → INCOME_STABILITY (confidence 0.6, "and check" detected)
        → AGENTIC path
        → Agent plans: [get_income_stability, category_presence_lookup(betting_gaming)]
        → execute both
        → Explainer narrates both results
```

### Example 3: Open-Ended Risk Query (New Capability)

```
User: "Is customer 5004898 a good candidate for a loan?"

BEFORE: IntentParser → LENDER_PROFILE → [generate_lender_profile] → single tool
AFTER:  IntentParser → LENDER_PROFILE (confidence 0.75, "good candidate" is open-ended)
        → AGENTIC path
        → Agent plans: [
            generate_lender_profile,
            get_income_stability,
            category_presence_lookup(betting_gaming),
            bureau_delinquency_check
          ]
        → execute all 4
        → Explainer narrates comprehensive assessment

        → Re-plan trigger: delinquency_check shows DPD
        → Agent adds: [bureau_overview]
        → execute 1 more
        → Explainer now has 5 tool results for thorough answer
```

### Example 4: Unknown Intent Recovery (New Capability)

```
User: "Tell me everything about customer 5004898"

BEFORE: IntentParser → UNKNOWN → error "Could not understand the query"
AFTER:  IntentParser → UNKNOWN (confidence 0.3)
        → AGENTIC path (UNKNOWN always routes to agent)
        → Agent plans: [
            get_cash_flow,
            top_spending_categories,
            get_income_stability,
            bureau_overview
          ]
        → execute all 4
        → Explainer narrates a comprehensive overview

        No error. User gets useful information.
```

### Example 5: Report Generation Guard

```
User: "Is customer 5004898 risky?"

Agent might try: [detect_anomalies, generate_customer_report, bureau_delinquency_check]

Guard catches: generate_customer_report blocked (user didn't ask for report)
Final plan:    [detect_anomalies, bureau_delinquency_check]

Report generation only happens when user says "report" or "PDF".
```

### Example 6: Cross-Data-Source (New Capability)

```
User: "How does customer 5004898's banking match their bureau profile?"

BEFORE: No intent matches → UNKNOWN → error
AFTER:  IntentParser → UNKNOWN or FINANCIAL_OVERVIEW
        → AGENTIC path
        → Agent reasons: "Cross-data comparison needs banking + bureau tools"
        → Plans: [
            get_cash_flow,           (banking)
            get_income_stability,    (banking)
            bureau_overview,         (bureau)
            bureau_delinquency_check (bureau)
          ]
        → Explainer compares banking health vs bureau health in narrative
```

---

## Architecture Decision Records

### ADR-1: Why Not a Full ReAct Loop?

A ReAct (Reason-Act-Observe) loop where the agent calls one tool at a time, observes the result, and decides the next tool would be the "fully agentic" approach. We rejected this because:

1. **Latency:** Each ReAct step requires an LLM call (1-3s). A 5-tool plan would take 5-15s just for planning, plus execution time. Current queries complete in 5-10s total.
2. **Determinism:** The current system's strength is reproducibility. A ReAct loop with temperature=0 is still less predictable than a deterministic map.
3. **Cost:** Each planning step is an LLM inference. For 80% of queries that are simple single-intent, this is wasted computation.

The hybrid approach gives agentic capability for the 20% of queries that need it, while preserving speed and determinism for the 80% that don't.

### ADR-2: Why Mistral for the Planner (Not DeepSeek-R1)?

The planner needs to output structured JSON quickly. Mistral is already proven for this role (intent parser uses it). DeepSeek-R1 is slower and its `<think>` block adds latency. The planning task is simpler than report narration — it's tool selection, not prose generation.

### ADR-3: Why Deterministic Re-Plan Triggers?

Using an LLM to decide "should I re-plan?" adds another LLM call to every query. Deterministic triggers (`if DPD detected and bureau_overview not in plan → add it`) are faster, more predictable, and cover the most common follow-up scenarios. The LLM is only called if a trigger fires AND the follow-up tools need complex argument resolution.

### ADR-4: Why Keep IntentParser Unchanged?

The IntentParser already works well for extracting customer_id, category, dates, and a primary intent. The agentic planner USES the parser's output as context — it doesn't replace it. The parser tells the agent "the user probably wants X", and the agent decides "X plus Y plus Z would fully answer this".

---

*Plan generated from full codebase analysis — 2026-03*
