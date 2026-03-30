# Agentic Migration Plan — From Fixed Pipeline to Adaptive Agent

> **Status:** Architecture Plan
> **Goal:** Let the LLM reason about *which tools to call* and *what analysis to run*, not just narrate pre-computed results
> **Core Example:** User asks "Generate combined report for 698167220, also check if they're eligible for a 10L BL loan" — system should generate the report AND autonomously invoke eligibility tools without a hardcoded intent for this combo

---

## 1. Honest Critique of Current Architecture

### What It Actually Is

The system is a **lookup-table dispatcher with LLM narration**. Not agentic.

```
User query → Enum classification → Dict lookup → Fixed tool list → Execute → LLM narrates
```

The LLM is a **narrator**, not a **planner**. Every decision about what to compute is made by Python dicts (`INTENT_TOOL_MAP`, `tool_map`, `SECTION_TOOL_MAP`). The LLM never decides "I should also check X because Y looks risky."

### Specific Rigidity Points

| Component | What It Does | Why It's Not Agentic |
|---|---|---|
| `IntentType` enum (23 values) | Classifies user query into 1 of 23 buckets | Can't handle "generate report + check BL eligibility" — that's TWO intents, system only picks ONE |
| `INTENT_TOOL_MAP` dict | Maps each intent to a fixed tool list | `COMBINED_REPORT → ["generate_combined_report"]` always. No "also run FOIR check if user asked about a loan" |
| `QueryPlanner.create_plan()` | `tools = INTENT_TOOL_MAP.get(intent)` — that's it | Zero reasoning. Doesn't look at query context, customer data, or user's specific ask |
| `ToolExecutor.execute()` | Loops through plan, calls `tool_map[name](**args)` | No re-planning if tool reveals something interesting. No "tool A failed, try tool B" |
| `compute_checklist()` | 20 hardcoded yes/no flags | Same checklist for every customer regardless of context |
| `key_findings.py` | 40+ threshold comparisons | No composite reasoning ("high enquiries + new PLs = refinancing OR desperation?") |

### The Real Problem

**The user's example exposes the fundamental gap:**

```
"Generate combined report for 698167220, also check eligibility for 10L BL loan"
```

Current system:
1. Intent parser sees "combined report" → `IntentType.COMBINED_REPORT`
2. Planner looks up → `["generate_combined_report"]`
3. The "check eligibility for 10L BL" part is **silently dropped** — no intent handles it
4. Report generates with zero awareness of the user's BL question

What should happen:
1. LLM parses: primary_intent=COMBINED_REPORT, secondary_ask={product: BL, amount: 10L, action: eligibility_check}
2. Agent reasons: "To check BL eligibility I need: FOIR, income, existing exposure, DPD, scorecard verdict"
3. Agent plans: [generate_combined_report, compute_foir_with_proposed_emi, check_policy_rules(BL, 10L)]
4. Report includes a dedicated "BL Eligibility Assessment" section with pass/fail per policy rule

---

## 2. The Hybrid Approach: Why Pure Agentic Won't Work Here

### Why NOT go fully agentic

| Concern | Why Full Agentic Fails |
|---|---|
| **Compliance** | Banking risk decisions must be auditable. "The LLM decided this was high risk" is not acceptable. Thresholds and policy rules MUST remain deterministic |
| **Reproducibility** | Same customer data must produce same scorecard, same checklist, same key findings. LLM temperature=0 still has variance across model versions |
| **Cost of wrong answers** | A missed DPD finding or incorrect FOIR calculation could lead to bad lending decisions. Deterministic code catches 100% of threshold breaches; LLMs might miss one |
| **Local model quality** | Ollama models (mistral, llama3.2) are not as capable as GPT-4/Claude at complex multi-step reasoning. Asking them to plan 5-tool chains reliably is risky |

### The Hybrid Model

```
┌──────────────────────────────────────────────────────────┐
│                    AGENTIC LAYER                         │
│  LLM decides: WHAT tools to call, in WHAT order,        │
│  with WHAT parameters, and WHETHER to call more          │
│  based on intermediate results                           │
├──────────────────────────────────────────────────────────┤
│                 DETERMINISTIC LAYER                      │
│  Tools compute: numbers, thresholds, scores, verdicts    │
│  Policy engine: pass/fail per rule                       │
│  Scorecard: RAG signals                                  │
│  Key findings: threshold-based                           │
│  Checklist: boolean flags                                │
└──────────────────────────────────────────────────────────┘
```

**LLM reasons about strategy. Python computes the numbers.**

This is the correct split because:
- Tool selection can tolerate some variance (calling an extra tool is fine, missing one can be caught)
- Number computation cannot tolerate ANY variance (FOIR must be exact)
- The LLM adds value in reasoning about WHICH analyses matter for THIS customer
- The LLM adds NO value in computing those analyses

---

## 3. Plan Options

### Option A: Minimal — Multi-Intent Parser + Sidecar Tools (Difficulty: Low, Impact: Medium)

Keep the current pipeline mostly intact. Extend the intent parser to extract **multiple intents + extra parameters** from a single query. Add "sidecar" tool execution for secondary asks.

#### What Changes

```
BEFORE:
  ParsedIntent { intent: COMBINED_REPORT, customer_id: 698167220 }
  → Planner: ["generate_combined_report"]
  → Done

AFTER:
  ParsedIntent {
    intent: COMBINED_REPORT,
    customer_id: 698167220,
    secondary_asks: [
      { action: "eligibility_check", product: "BL", amount: 1000000 }
    ]
  }
  → Planner: ["generate_combined_report"]
  → Sidecar: [check_eligibility(customer_id=698167220, product=BL, amount=10L)]
  → Both results merged into report
```

#### Files to Change

| File | Change | Effort |
|---|---|---|
| `schemas/intent.py` | Add `secondary_asks: List[SecondaryAsk]` to `ParsedIntent` | Small |
| `config/prompts.py` | Update `PARSER_PROMPT` to extract secondary asks as JSON array | Small |
| `pipeline/core/intent_parser.py` | Parse `secondary_asks` from LLM response | Small |
| `pipeline/core/planner.py` | After primary plan, append sidecar tools for each secondary ask | Medium |
| `pipeline/core/executor.py` | No change — already loops through plan steps | None |
| `tools/eligibility.py` | **New file** — `check_eligibility(customer_id, product, amount)` | Medium |
| `config/policy_rules.py` | Reuse from existing `policy_judgment_plan.md` | Already planned |
| `pipeline/renderers/combined_report_renderer.py` | Add "Eligibility Assessment" section if sidecar results exist | Medium |

#### Sidecar Tool Registry

```python
# config/sidecar_tools.py
SIDECAR_TOOL_MAP = {
    "eligibility_check": {
        "tool": "check_eligibility",
        "required_args": ["customer_id", "product", "amount"],
        "description": "Check if customer is eligible for a specific loan product and amount",
    },
    "compare_with_peer": {
        "tool": "peer_comparison",
        "required_args": ["customer_id", "segment"],
        "description": "Compare customer metrics against peer segment averages",
    },
    "stress_test": {
        "tool": "stress_test_emi",
        "required_args": ["customer_id", "proposed_emi"],
        "description": "Test if customer can handle additional EMI load",
    },
}
```

#### Pros & Cons

| Pros | Cons |
|---|---|
| Minimal disruption — existing pipeline untouched | Still enum-driven for primary intent |
| Easy to test — sidecar tools are independent | Can't handle 3+ intents or complex chains |
| Deterministic tools stay deterministic | LLM doesn't reason about tool dependencies |
| Works with current local models | Secondary asks limited to pre-registered sidecars |

#### Effort: ~3-4 days

---

### Option B: Moderate — LLM Tool Planner with Schema Registry (Difficulty: Medium, Impact: High)

Replace `INTENT_TOOL_MAP` lookup with an **LLM planner** that receives tool schemas and reasons about which tools to call. Keep all tools deterministic. The LLM only decides the plan; Python executes it.

#### Architecture

```
User query
    ↓
Intent Parser (keep existing — still useful for routing)
    ↓
┌──────────────────────────────────────────────────────┐
│  NEW: LLM Tool Planner                              │
│                                                      │
│  Input:                                              │
│    - parsed intent + secondary asks                  │
│    - customer data profile (has_bureau, has_banking,  │
│      income_band, dpd_status, etc.)                  │
│    - available tool schemas (name, description,       │
│      parameters, returns)                            │
│                                                      │
│  LLM reasons:                                        │
│    "User wants combined report + BL eligibility.     │
│     For eligibility I need FOIR, income, DPD.        │
│     Combined report already computes these.          │
│     Plan: generate_combined_report first,            │
│     then check_eligibility using report data."       │
│                                                      │
│  Output:                                             │
│    [                                                 │
│      { tool: "generate_combined_report",             │
│        args: { customer_id: 698167220 },             │
│        reason: "Primary ask" },                      │
│      { tool: "check_eligibility",                    │
│        args: { customer_id: 698167220,               │
│                product: "BL", amount: 1000000 },     │
│        reason: "Secondary ask: BL eligibility",      │
│        depends_on: "generate_combined_report" }      │
│    ]                                                 │
└──────────────────────────────────────────────────────┘
    ↓
Executor (enhanced — respects depends_on ordering)
    ↓
Report + Eligibility merged into output
```

#### Tool Schema Registry

```python
# config/tool_registry.py

from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: Dict[str, Any]     # JSON Schema for args
    returns: str                    # Description of return value
    category: str                  # "report", "analytics", "eligibility", "bureau"
    requires_data: List[str]       # ["banking", "bureau", "both"]
    side_effects: List[str]        # ["generates_pdf", "generates_excel"]

TOOL_REGISTRY: Dict[str, ToolSchema] = {
    "generate_combined_report": ToolSchema(
        name="generate_combined_report",
        description="Generate full combined banking + bureau report with PDF, HTML, Excel",
        parameters={
            "customer_id": {"type": "integer", "required": True},
        },
        returns="CustomerReport + BureauReport + PDF path",
        category="report",
        requires_data=["banking", "bureau"],
        side_effects=["generates_pdf", "generates_excel"],
    ),
    "check_eligibility": ToolSchema(
        name="check_eligibility",
        description="Check customer eligibility for a loan product at a specific amount. "
                    "Evaluates FOIR, income, DPD, exposure limits, and policy rules. "
                    "Returns pass/fail per rule with detailed reasoning.",
        parameters={
            "customer_id": {"type": "integer", "required": True},
            "product": {"type": "string", "enum": ["PL", "BL", "HL", "AL", "LAP", "CC"],
                       "required": True},
            "amount": {"type": "number", "required": True,
                      "description": "Proposed loan amount in INR"},
        },
        returns="EligibilityResult with per-rule pass/fail and verdict",
        category="eligibility",
        requires_data=["banking", "bureau"],
        side_effects=[],
    ),
    "bureau_delinquency_check": ToolSchema(
        name="bureau_delinquency_check",
        description="Quick check for any delinquency (DPD > 0) in bureau data",
        parameters={
            "customer_id": {"type": "integer", "required": True},
        },
        returns="Delinquency status with max DPD and affected products",
        category="bureau",
        requires_data=["bureau"],
        side_effects=[],
    ),
    # ... all 25+ tools registered with schemas
}

def get_tool_schemas_for_prompt() -> str:
    """Format all tool schemas as a string for the LLM planner prompt."""
    lines = []
    for name, schema in TOOL_REGISTRY.items():
        params = ", ".join(f"{k}: {v['type']}" for k, v in schema.parameters.items())
        lines.append(f"- {name}({params}): {schema.description}")
    return "\n".join(lines)
```

#### LLM Planner Prompt

```python
# config/prompts.py (addition)

TOOL_PLANNER_PROMPT = """You are a financial analysis planner. Given a user query and
available tools, decide which tools to call and in what order.

## Available Tools
{tool_schemas}

## User Query
{query}

## Parsed Intent
Primary: {primary_intent}
Customer ID: {customer_id}
Secondary asks: {secondary_asks}

## Customer Data Profile
Has banking data: {has_banking}
Has bureau data: {has_bureau}
Income band: {income_band}
DPD status: {dpd_status}

## Rules
1. Always include tools for the primary intent
2. For each secondary ask, select the most appropriate tool
3. If a tool depends on another's output, mark depends_on
4. Maximum {max_tools} tools per plan
5. Explain your reasoning for each tool selection

## Output (JSON array)
[
  {{
    "tool": "tool_name",
    "args": {{"param": "value"}},
    "reason": "why this tool",
    "depends_on": null or "tool_name"
  }}
]
"""
```

#### Files to Change

| File | Change | Effort |
|---|---|---|
| `config/tool_registry.py` | **New** — Schema for every tool | Medium (one-time) |
| `config/prompts.py` | Add `TOOL_PLANNER_PROMPT` | Small |
| `pipeline/core/planner.py` | Replace dict lookup with LLM planner call (keep dict lookup as fallback) | Medium |
| `pipeline/core/executor.py` | Add `depends_on` ordering logic | Small |
| `schemas/intent.py` | Add `secondary_asks` field | Small |
| `pipeline/core/intent_parser.py` | Extract secondary asks | Small |
| `tools/eligibility.py` | **New** — Eligibility checker | Medium |
| `config/policy_rules.py` | Policy rules (from existing plan) | Already planned |

#### The Critical Fallback

```python
class QueryPlanner:
    def create_plan(self, intent, tool_schemas):
        # TRY: LLM planner
        try:
            plan = self._llm_plan(intent, tool_schemas)
            if self._validate_plan(plan):  # all tools exist, args valid
                return plan
        except Exception:
            logger.warning("LLM planner failed, falling back to dict lookup")

        # FALLBACK: Current deterministic lookup (zero regression risk)
        tools = INTENT_TOOL_MAP.get(intent.intent, [])
        return self._build_plan(intent, tools)
```

**This is critical.** The existing `INTENT_TOOL_MAP` becomes the safety net. If the LLM planner hallucinates a tool that doesn't exist, the system falls back to the proven path. Zero regression risk.

#### Pros & Cons

| Pros | Cons |
|---|---|
| LLM can compose tools dynamically | Requires good local LLM reasoning ability |
| Tool registry is self-documenting | Schema registration is upfront work |
| Fallback to current pipeline = zero regression | LLM planner adds ~2-3s latency |
| New tools auto-discoverable by LLM | Tool schema must be kept in sync with implementation |
| Handles the BL eligibility example perfectly | Prompt engineering for local models is fiddly |

#### Effort: ~5-7 days

---

### Option C: Full — ReAct Agent Loop with Observation-Based Re-Planning (Difficulty: High, Impact: Very High)

Implement a **ReAct (Reasoning + Acting) loop** where the LLM iteratively: thinks → acts (calls a tool) → observes (reads tool output) → decides next action. This is true agentic behavior.

#### Architecture

```
User query
    ↓
┌──────────────────────────────────────────────────────────────────┐
│  ReAct Agent Loop                                                │
│                                                                  │
│  ITERATION 1:                                                    │
│  Thought: "User wants combined report + BL eligibility for 10L.  │
│            First I need the combined report to get baseline data."│
│  Action: generate_combined_report(customer_id=698167220)         │
│  Observation: {CustomerReport + BureauReport, FOIR=42%, DPD=0,   │
│                income=85K/mo, existing_exposure=15L}             │
│                                                                  │
│  ITERATION 2:                                                    │
│  Thought: "Now I have the data. FOIR is 42%, adding 10L BL at    │
│            12% for 5yr = ~22K/mo EMI. New FOIR would be ~68%.    │
│            That exceeds 65% policy limit. Let me run the full    │
│            eligibility check."                                    │
│  Action: check_eligibility(customer_id=698167220, product=BL,    │
│          amount=1000000)                                          │
│  Observation: {verdict: PARTIAL, failures: [FOIR > 65%],         │
│                passes: [DPD=0, income > 25K, no adverse events]} │
│                                                                  │
│  ITERATION 3:                                                    │
│  Thought: "FOIR fails at 10L. Let me check what amount WOULD     │
│            pass. User might want to know max eligible amount."    │
│  Action: max_eligible_amount(customer_id=698167220, product=BL)  │
│  Observation: {max_amount: 7.5L, max_emi: 16700,                │
│                resulting_foir: 61.6%}                             │
│                                                                  │
│  ITERATION 4:                                                    │
│  Thought: "I have everything. Combined report is ready,           │
│            eligibility checked, and I found the max amount.       │
│            Time to respond."                                      │
│  Action: FINISH                                                   │
│  Final answer: Report + "Customer is not eligible for 10L BL     │
│    (FOIR would reach 68%, limit is 65%). Max eligible: 7.5L."    │
└──────────────────────────────────────────────────────────────────┘
```

#### Key Implementation: Agent Loop

```python
# pipeline/core/agent.py

class FinancialAgent:
    """ReAct agent that reasons about tool selection and re-plans
    based on intermediate results.

    All tools remain deterministic. The agent only controls:
    - Which tool to call next
    - What arguments to pass
    - When to stop
    - How to narrate the combined results
    """

    MAX_ITERATIONS = 6       # Hard limit — prevents infinite loops
    STOP_TOKEN = "FINISH"

    def __init__(self, llm, tool_registry, tool_executor):
        self.llm = llm
        self.registry = tool_registry
        self.executor = tool_executor
        self.scratchpad = []   # (thought, action, observation) tuples

    def run(self, query: str, parsed_intent: ParsedIntent) -> AgentResult:
        """Execute the ReAct loop."""

        tool_descriptions = self.registry.get_schemas_for_prompt()

        for i in range(self.MAX_ITERATIONS):
            # Build prompt with full scratchpad history
            prompt = REACT_PROMPT.format(
                query=query,
                intent=parsed_intent,
                tools=tool_descriptions,
                scratchpad=self._format_scratchpad(),
                iteration=i + 1,
                max_iterations=self.MAX_ITERATIONS,
            )

            # LLM thinks + decides action
            response = self.llm.invoke(prompt)
            thought, action = self._parse_response(response)

            if action.tool == self.STOP_TOKEN:
                return AgentResult(
                    scratchpad=self.scratchpad,
                    final_answer=action.args.get("answer", ""),
                    tools_called=[s[1] for s in self.scratchpad],
                )

            # Validate tool exists and args are valid
            if not self._validate_action(action):
                self.scratchpad.append((
                    thought,
                    action,
                    f"ERROR: Tool '{action.tool}' not found or invalid args"
                ))
                continue

            # Execute tool (deterministic!)
            result = self.executor.execute_single(action.tool, action.args)

            # Truncate observation to fit context window
            observation = self._truncate_observation(result, max_tokens=2000)

            self.scratchpad.append((thought, action, observation))

        # Max iterations reached — return what we have
        return AgentResult(
            scratchpad=self.scratchpad,
            final_answer="Analysis complete (reached iteration limit)",
            tools_called=[s[1] for s in self.scratchpad],
            hit_limit=True,
        )
```

#### ReAct Prompt

```python
REACT_PROMPT = """You are a financial analysis agent. You have access to tools
that compute deterministic financial metrics. You decide which tools to use and
in what order, based on the user's query and intermediate results.

## Available Tools
{tools}

## User Query
{query}

## Work Done So Far
{scratchpad}

## Rules
1. THINK about what information you still need
2. Call ONE tool per iteration
3. After calling a tool, OBSERVE the result before deciding next steps
4. Call FINISH when you have enough information to answer the query
5. Never compute numbers yourself — always use a tool
6. Maximum {max_iterations} iterations. You are on iteration {iteration}.

## Response Format
Thought: <your reasoning about what to do next>
Action: <tool_name>
Args: {{"param": "value"}}

OR if done:
Thought: <why you're done>
Action: FINISH
Args: {{"answer": "<your final response>"}}
"""
```

#### Guard Rails for Local Models

Local models (mistral/llama3.2) are weaker at multi-step reasoning. Critical safeguards:

```python
# pipeline/core/agent.py — guard rails

class FinancialAgent:
    # 1. Tool whitelist — LLM can only call registered tools
    def _validate_action(self, action):
        return action.tool in self.registry

    # 2. Mandatory tools — some tools MUST be called for certain intents
    MANDATORY_TOOLS = {
        "COMBINED_REPORT": ["generate_combined_report"],
        "BUREAU_REPORT": ["generate_bureau_report"],
        "CUSTOMER_REPORT": ["generate_customer_report"],
    }

    def _check_mandatory(self, intent, tools_called):
        required = self.MANDATORY_TOOLS.get(intent, [])
        missing = [t for t in required if t not in tools_called]
        if missing:
            # Force-inject mandatory tools before FINISH
            return missing
        return []

    # 3. Argument validation — args must match schema
    def _validate_args(self, tool_name, args):
        schema = self.registry[tool_name]
        for param, spec in schema.parameters.items():
            if spec.get("required") and param not in args:
                return False, f"Missing required param: {param}"
        return True, ""

    # 4. Cost budget — prevent runaway tool calls
    MAX_TOOL_COST = {
        "generate_combined_report": 3,  # expensive (generates 2 sub-reports)
        "generate_customer_report": 2,
        "generate_bureau_report": 2,
        "check_eligibility": 1,
        "bureau_delinquency_check": 1,
        # default: 1
    }

    def _within_budget(self, tools_called):
        cost = sum(self.MAX_TOOL_COST.get(t, 1) for t in tools_called)
        return cost <= 10  # Budget limit
```

#### Integration with Current Pipeline

```python
# pipeline/orchestrator.py — modified

class TransactionPipeline:
    def query_stream(self, query, customer_id=None):
        intent = self.parser.parse(query)

        # NEW: Route to agent for complex queries, keep old path for simple ones
        if self._needs_agent(intent):
            agent = FinancialAgent(self.planner_llm, self.tool_registry, self.executor)
            result = agent.run(query, intent)
            yield from self._stream_agent_result(result)
        else:
            # EXISTING: Simple dict-lookup path (unchanged)
            plan, error = self.planner.create_plan(intent)
            results = self.executor.execute(plan)
            yield from self.explainer.stream_explain(intent, results)

    def _needs_agent(self, intent: ParsedIntent) -> bool:
        """Use agent for complex queries, simple path for basic ones."""
        return (
            bool(intent.secondary_asks) or           # Has secondary asks
            intent.intent == IntentType.UNKNOWN or    # Can't classify
            len(intent.raw_query.split()) > 15        # Long, complex query
        )
```

#### Files to Change

| File | Change | Effort |
|---|---|---|
| `pipeline/core/agent.py` | **New** — ReAct agent loop | Large |
| `config/tool_registry.py` | **New** — Tool schema registry | Medium |
| `config/prompts.py` | Add `REACT_PROMPT` | Medium |
| `schemas/agent.py` | **New** — `AgentResult`, `AgentAction` schemas | Small |
| `pipeline/orchestrator.py` | Route complex queries to agent, keep simple path | Medium |
| `pipeline/core/executor.py` | Add `execute_single()` method | Small |
| `pipeline/core/intent_parser.py` | Extract `secondary_asks` | Small |
| `schemas/intent.py` | Add `secondary_asks` field | Small |
| `tools/eligibility.py` | **New** — Eligibility tools | Medium |
| `tools/max_eligible.py` | **New** — Max eligible amount calculator | Medium |
| `pipeline/renderers/combined_report_renderer.py` | Render agent results as report sections | Medium |

#### Pros & Cons

| Pros | Cons |
|---|---|
| True agentic behavior — reasons about next steps | Local models may struggle with multi-step ReAct |
| Can discover insights ("FOIR too high, let me find max amount") | 4-6 LLM calls per query = 15-25s added latency |
| Handles arbitrary user asks without new intents | Harder to debug — non-deterministic tool paths |
| Graceful: simple queries still use fast dict-lookup path | Scratchpad can blow context window for small models |
| Future-proof — adding a tool = registering its schema | Requires robust parsing of ReAct format from local LLM |

#### Effort: ~10-14 days

---

## 4. Comparison Matrix

| Dimension | Option A: Multi-Intent | Option B: LLM Planner | Option C: ReAct Agent |
|---|---|---|---|
| **Difficulty** | Low | Medium | High |
| **Impact** | Medium | High | Very High |
| **Effort** | 3-4 days | 5-7 days | 10-14 days |
| **Handles BL eligibility example** | Yes (if sidecar registered) | Yes (LLM selects tools) | Yes (agent discovers tools) |
| **Handles "what's the max I can borrow?"** | No (not a registered sidecar) | Maybe (if LLM reasons about it) | Yes (agent iterates to find answer) |
| **Handles "compare this customer to peers"** | Only if pre-registered | Yes if tool exists | Yes, can compose multiple tools |
| **Regression risk** | Near zero | Low (fallback to dict) | Medium (new code path) |
| **Latency impact** | +0s (no extra LLM calls) | +2-3s (one LLM planning call) | +15-25s (4-6 LLM calls) |
| **Local model compatibility** | Excellent (no reasoning needed) | Good (single structured output) | Risky (multi-step reasoning) |
| **Debugging** | Easy (same pipeline + sidecar) | Medium (check LLM plan) | Hard (trace scratchpad) |
| **New tool onboarding** | Register in sidecar map | Register schema, LLM discovers | Register schema, agent discovers |

---

## 5. Recommendation: Phased Approach (A → B → C)

### Phase 1: Ship Option A (Week 1)

Get multi-intent parsing + eligibility sidecar working. Users immediately get the "combined report + BL eligibility" flow. Zero regression risk.

**Deliverables:**
- `secondary_asks` in ParsedIntent
- `check_eligibility` tool
- Sidecar execution in planner
- Eligibility section in combined report template

### Phase 2: Evolve to Option B (Week 2-3)

Build the tool schema registry and LLM planner. Option A's sidecar map becomes a subset of the full registry. The LLM planner replaces the sidecar lookup but falls back to `INTENT_TOOL_MAP` on failure.

**Deliverables:**
- `config/tool_registry.py` with schemas for all 25+ tools
- LLM planner with `TOOL_PLANNER_PROMPT`
- Fallback chain: LLM planner → INTENT_TOOL_MAP → error
- Observation: measure LLM planner accuracy on 50 test queries

### Phase 3: Add ReAct for Complex Queries (Week 4+, optional)

Only if Phase 2 shows the local LLM handles single-shot planning well, extend to multi-step ReAct for complex queries. Keep Phase 2's single-shot planner for simple queries.

**Gate criteria for Phase 3:**
- LLM planner selects correct tools >85% of the time
- Local model can produce valid ReAct format >90% of the time
- Latency budget of 30s total is acceptable for complex queries

---

## 6. Critical New Tools Needed (All Options)

### 6.1 `tools/eligibility.py` — Loan Eligibility Checker

```python
@dataclass
class EligibilityResult:
    verdict: str                      # "ELIGIBLE" | "NOT_ELIGIBLE" | "CONDITIONAL"
    product: str                      # "BL", "PL", etc.
    requested_amount: float
    max_eligible_amount: Optional[float]
    proposed_emi: float
    resulting_foir: float
    rule_results: List[RuleResult]    # Per-rule pass/fail
    strengths: List[str]
    blockers: List[str]               # Hard rule failures
    warnings: List[str]               # Soft rule concerns

def check_eligibility(
    customer_id: int,
    product: str,
    amount: float,
    tenure_months: int = 60,
    rate_pct: float = 12.0,
) -> EligibilityResult:
    """
    Deterministic eligibility check against policy rules.

    1. Load customer data (reuses cached reports)
    2. Compute proposed EMI from amount/tenure/rate
    3. Compute new FOIR = (existing_EMIs + proposed_EMI) / income
    4. Evaluate each PolicyRule for the product
    5. Aggregate verdict: all hard rules pass → ELIGIBLE
    """
```

### 6.2 `tools/max_eligible.py` — Max Amount Calculator

```python
def max_eligible_amount(
    customer_id: int,
    product: str,
    tenure_months: int = 60,
    rate_pct: float = 12.0,
) -> dict:
    """Binary search for max amount that passes all hard policy rules."""
```

### 6.3 `tools/stress_test.py` — EMI Stress Test

```python
def stress_test(
    customer_id: int,
    proposed_emi: float,
    rate_increase_bps: int = 200,
) -> dict:
    """Test if customer can handle EMI at base rate + stress rate."""
```

---

## 7. Template & Rendering Changes

For any option, the combined report template needs a new **dynamic sections** capability:

```html
<!-- templates/combined_report_original.html -->

{# Existing fixed sections (unchanged) #}
{% include "sections/banking_summary.html" %}
{% include "sections/bureau_summary.html" %}
{% include "sections/key_findings.html" %}

{# NEW: Dynamic agent-generated sections #}
{% if agent_sections %}
<div class="agent-sections">
  {% for section in agent_sections %}
  <div class="section {{ section.severity_class }}">
    <h3>{{ section.title }}</h3>
    {{ section.html_content }}
  </div>
  {% endfor %}
</div>
{% endif %}
```

The renderer receives `agent_sections` — a list of `{title, html_content, severity_class}` dicts generated by the eligibility tool or any future sidecar/agent tool.

---

## 8. What Stays Deterministic (Non-Negotiable)

Regardless of which option is chosen, these MUST remain pure Python, no LLM:

| Component | Why |
|---|---|
| `compute_scorecard()` | Auditable risk verdict |
| `compute_checklist()` | Boolean compliance flags |
| `extract_key_findings()` | Threshold-based findings |
| `check_eligibility()` | Policy rule evaluation |
| `extract_bureau_features()` | Feature vector computation |
| `aggregate_bureau_features()` | Executive summary inputs |
| All `config/thresholds.py` | Business rule constants |
| All `config/policy_rules.py` | Policy rule definitions |

**The LLM decides WHAT to compute. Python decides HOW to compute it and WHAT the answer is.**

---

## 9. Migration Safety Checklist

- [ ] All existing `INTENT_TOOL_MAP` queries produce identical results (regression test)
- [ ] LLM planner fallback to dict lookup works when LLM fails
- [ ] ReAct agent has hard iteration limit (MAX_ITERATIONS=6)
- [ ] Tool cost budget prevents runaway execution
- [ ] Mandatory tool check ensures reports are always generated for report intents
- [ ] New tools (`eligibility`, `stress_test`) have independent unit tests
- [ ] Agent scratchpad is logged to `logs/agent_YYYYMMDD.jsonl` for debugging
- [ ] Latency budgets documented: simple query <10s, agent query <30s
- [ ] Local model compatibility validated before Phase 3 gate

---

## 10. Open Questions for Decision

1. **Model upgrade?** ReAct (Option C) may require a better local model than llama3.2. Consider `deepseek-r1` or `qwen2.5` for the planner role while keeping llama3.2 for narration.

2. **Streaming during agent loop?** Current system streams the explainer response. With ReAct, do we stream thoughts? Show a progress indicator per iteration? Or buffer until FINISH?

3. **Eligibility in combined report vs separate?** Should eligibility results be embedded in the combined report PDF, or returned as a separate section/response alongside the report?

4. **Policy rules source?** The existing `policy_judgment_plan.md` defines policy rules as Python config. Should we also support loading from a policy document (markdown/PDF) as in that plan's Tier 2?

5. **Batch compatibility?** `batch_reports.py` runs `generate_combined_report_pdf()` for multiple CRNs. Does the agent path need to work in batch mode, or only interactive?

---
---

# Part 2 — Technically Rigorous Options (D, E, F)

The options above (A/B/C) are custom-built. The options below leverage production frameworks that already solve tool orchestration, protocol interop, and multi-agent coordination. These are not academic — they build on libraries **already installed** in this project.

## Verified Technical Foundation

Before designing these options, the following was validated against the actual environment:

| Component | Status | Evidence |
|---|---|---|
| `langgraph` 1.0.7 | Installed | `create_react_agent`, `StateGraph`, `ToolNode`, `MemorySaver` all importable |
| `langchain-ollama` 1.0.1 | Installed | `ChatOllama` supports `.bind_tools()` and `.with_structured_output()` |
| Ollama tool calling | Works | `mistral` correctly returns `tool_calls` with structured args — tested live |
| LangGraph ReAct | Works | `create_react_agent(ChatOllama("mistral"), [tools])` executes tool → observes → responds — tested live |
| `mcp` SDK | NOT installed | Would need `pip install mcp` (~lightweight, pure Python) |

**Critical discovery:** Ollama `mistral` natively supports tool calling via `bind_tools()`. This means we do NOT need custom ReAct prompt parsing (Option C's biggest risk). LangGraph's `ToolNode` handles the tool call → execution → observation loop automatically.

---

## Option D: LangGraph StateGraph Agent (Difficulty: Medium, Impact: Very High)

**Why this over Option C's hand-rolled ReAct:** LangGraph provides the agent loop, tool dispatch, state management, and checkpointing out of the box. We write zero agent loop code — just define the graph nodes and edges.

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     LangGraph StateGraph                             │
│                                                                      │
│   ┌─────────┐    ┌───────────────┐    ┌──────────┐                  │
│   │  START   │───▶│  agent_node   │───▶│ tool_node│──┐              │
│   └─────────┘    │ (ChatOllama   │    │(ToolNode) │  │              │
│                  │  + bind_tools) │◀───│           │──┘              │
│                  └───────┬───────┘    └──────────┘                  │
│                          │ no tool calls                             │
│                          ▼                                           │
│                  ┌───────────────┐                                   │
│                  │   END         │                                   │
│                  │ (final answer)│                                   │
│                  └───────────────┘                                   │
│                                                                      │
│   State: { messages: [...], customer_id: int, report_data: dict }   │
│   Checkpointer: MemorySaver (enables multi-turn conversations)      │
└──────────────────────────────────────────────────────────────────────┘
```

### How It Handles the BL Eligibility Example

```python
# The LLM receives tool schemas via bind_tools().
# It natively decides to call tools, without prompt engineering.

User: "Generate combined report for 698167220, also check BL eligibility for 10L"

# LangGraph loop iteration 1:
# LLM sees tool schemas → decides: call generate_combined_report
# AIMessage.tool_calls = [{"name": "generate_combined_report", "args": {"customer_id": 698167220}}]
# ToolNode executes → ToolMessage with report summary

# LangGraph loop iteration 2:
# LLM sees report data in context → decides: call check_eligibility
# AIMessage.tool_calls = [{"name": "check_eligibility", "args": {"customer_id": 698167220, "product": "BL", "amount": 1000000}}]
# ToolNode executes → ToolMessage with eligibility result

# LangGraph loop iteration 3:
# LLM sees both results → no more tool_calls → generates final answer
# AIMessage.content = "Report generated. BL eligibility: NOT ELIGIBLE (FOIR 68% > 65% limit). Max eligible: 7.5L."
```

### Implementation

```python
# pipeline/core/langgraph_agent.py

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver
import operator


# ── 1. State Schema ──────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    customer_id: int | None
    report_generated: bool
    tools_called: list[str]


# ── 2. Wrap Existing Tools as LangChain @tool ────────────────────

@tool
def generate_combined_report(customer_id: int) -> dict:
    """Generate a full combined banking + bureau credit report with PDF.
    Returns report summary including income, FOIR, DPD, exposure, scorecard verdict.
    Call this when the user asks for a report, credit analysis, or financial overview."""
    from tools.combined_report import generate_combined_report_pdf
    cust, bureau, pdf_path = generate_combined_report_pdf(customer_id)
    # Return a summarised dict (not the full report — too large for context)
    summary = {}
    if cust:
        summary["income"] = cust.salary.avg_amount if cust.salary else None
        summary["total_emis"] = cust.emis.total_emi if cust.emis else None
        summary["savings_rate"] = cust.savings.savings_rate if cust.savings else None
        summary["risk_level"] = cust.risk_indicators.risk_level if cust.risk_indicators else None
    if bureau:
        ei = bureau.executive_inputs
        summary["max_dpd"] = ei.max_dpd
        summary["total_exposure"] = ei.total_sanctioned_amount
        summary["outstanding"] = ei.total_outstanding
        summary["has_delinquency"] = ei.has_delinquency
        summary["foir"] = getattr(bureau.tradeline_features, "foir", None) if bureau.tradeline_features else None
    summary["pdf_path"] = pdf_path
    return summary


@tool
def check_eligibility(customer_id: int, product: str, amount: float,
                      tenure_months: int = 60, rate_pct: float = 12.0) -> dict:
    """Check if a customer is eligible for a specific loan product and amount.
    Evaluates FOIR, income, DPD, exposure limits, and credit policy rules.
    Products: PL, BL, HL, AL, LAP, CC.
    Returns per-rule pass/fail with verdict (ELIGIBLE / NOT_ELIGIBLE / CONDITIONAL)."""
    from tools.eligibility import check_eligibility as _check  # deterministic
    result = _check(customer_id, product, amount, tenure_months, rate_pct)
    return result  # EligibilityResult.__dict__


@tool
def bureau_delinquency_check(customer_id: int) -> dict:
    """Quick check for any delinquency (DPD > 0) in bureau/CIBIL data.
    Returns max DPD, affected loan types, and severity assessment.
    Use this for a fast risk check before deeper analysis."""
    from tools.bureau_chat import bureau_delinquency_check as _check
    return _check(customer_id)


@tool
def get_income_stability(customer_id: int) -> dict:
    """Analyse income stability from banking transactions.
    Returns salary frequency, coefficient of variation, trend direction,
    and months of stable income. Useful for assessing repayment capacity."""
    from tools.analytics import get_income_stability as _get
    return _get(customer_id)


@tool
def max_eligible_amount(customer_id: int, product: str,
                        tenure_months: int = 60, rate_pct: float = 12.0) -> dict:
    """Find the maximum loan amount a customer is eligible for on a given product.
    Uses binary search over policy rules. Returns max amount, resulting FOIR, and EMI."""
    from tools.max_eligible import max_eligible_amount as _max
    return _max(customer_id, product, tenure_months, rate_pct)


# All tools that the agent can use
AGENT_TOOLS = [
    generate_combined_report,
    check_eligibility,
    bureau_delinquency_check,
    get_income_stability,
    max_eligible_amount,
    # ... wrap remaining 20+ tools the same way
]


# ── 3. Build the Graph ───────────────────────────────────────────

def build_financial_agent():
    """Build LangGraph agent with Ollama + all financial tools."""

    llm = ChatOllama(model="mistral", temperature=0, seed=42)
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)

    def agent_node(state: AgentState):
        """LLM decides next action based on conversation history."""
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState):
        """Route: if LLM made tool calls → tool_node, else → END."""
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    # Build graph
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(AGENT_TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")  # After tool execution, go back to agent

    # Compile with memory (enables multi-turn)
    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)


# ── 4. Integration with Existing Pipeline ─────────────────────────

FINANCIAL_AGENT = None  # Lazy singleton

def get_financial_agent():
    global FINANCIAL_AGENT
    if FINANCIAL_AGENT is None:
        FINANCIAL_AGENT = build_financial_agent()
    return FINANCIAL_AGENT


def agent_query(query: str, customer_id: int | None = None,
                thread_id: str = "default") -> dict:
    """Run a query through the LangGraph agent.

    Returns:
        {"answer": str, "tool_calls": list, "pdf_path": str | None}
    """
    agent = get_financial_agent()

    # Inject system prompt with guardrails
    system_msg = (
        "You are a financial analysis agent at Kotak Bank. "
        "You have tools that compute deterministic financial metrics. "
        "RULES: "
        "1. NEVER compute numbers yourself — always use a tool. "
        "2. For any report request, call generate_combined_report first. "
        "3. For eligibility questions, call check_eligibility with the product and amount. "
        "4. If eligibility fails, proactively call max_eligible_amount to suggest alternatives. "
        "5. Keep responses concise and factual. "
        "6. Always mention the PDF path if a report was generated."
    )

    messages = [("system", system_msg), ("user", query)]

    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke({"messages": messages, "customer_id": customer_id,
                           "report_generated": False, "tools_called": []}, config)

    # Extract final answer and metadata
    final_msg = result["messages"][-1]
    tool_calls = [m.tool_calls for m in result["messages"] if hasattr(m, "tool_calls") and m.tool_calls]
    pdf_paths = [m.content for m in result["messages"]
                 if hasattr(m, "name") and "report" in (m.name or "") and "pdf_path" in str(m.content)]

    return {
        "answer": final_msg.content,
        "tool_calls": tool_calls,
        "all_messages": result["messages"],
    }
```

### Integration into `orchestrator.py`

```python
# pipeline/core/orchestrator.py — add alongside existing pipeline

class TransactionPipeline:
    def __init__(self, ..., use_agent: bool = False):
        # ... existing init ...
        self.use_agent = use_agent

    def query_stream(self, query, customer_id=None):
        intent = self.parser.parse(query)
        self.resolve_customer_id(intent)

        if self.use_agent or self._needs_agent(intent):
            # LangGraph agent path
            from .langgraph_agent import agent_query
            result = agent_query(query, intent.customer_id)
            yield result["answer"]
        else:
            # Existing deterministic path (unchanged)
            plan, error = self.planner.create_plan(intent)
            results = self.executor.execute(plan)
            yield from self.explainer.stream_explain(intent, results)

    def _needs_agent(self, intent):
        """Route to agent for complex/ambiguous queries."""
        query_lower = intent.raw_query.lower()
        has_eligibility_ask = any(kw in query_lower for kw in
            ["eligible", "eligibility", "can they get", "qualify", "approved for",
             "how much can", "max loan", "stress test"])
        has_compound_ask = ("also" in query_lower or "and check" in query_lower
                           or "additionally" in query_lower)
        return (
            has_eligibility_ask or
            has_compound_ask or
            intent.intent == IntentType.UNKNOWN
        )
```

### Why This Is Better Than Option C (Hand-Rolled ReAct)

| Aspect | Option C (Custom ReAct) | Option D (LangGraph) |
|---|---|---|
| **Tool call parsing** | Custom regex on LLM text output | Native `tool_calls` from Ollama — zero parsing |
| **Agent loop** | Hand-written for-loop with scratchpad | LangGraph graph traversal — battle-tested |
| **Multi-turn memory** | Not supported | `InMemorySaver` checkpointer — free |
| **Error handling** | Manual try/except per tool | `ToolNode` handles errors, returns error messages to LLM |
| **Parallel tool calls** | Not supported | Ollama can return multiple `tool_calls` in one response |
| **Streaming** | Custom generator | LangGraph `.stream()` and `.astream()` built-in |
| **Code to write** | ~200 lines (agent.py) | ~100 lines (wrapping existing tools) |
| **Debugging** | Print scratchpad | LangGraph Studio, `.get_state()`, message history |

### Files to Change

| File | Change | Effort |
|---|---|---|
| `pipeline/core/langgraph_agent.py` | **New** — LangGraph agent definition + tool wrappers | Medium |
| `pipeline/core/orchestrator.py` | Add agent routing (`_needs_agent`, `use_agent` flag) | Small |
| `app.py` | Toggle between pipeline and agent mode (checkbox in sidebar) | Small |
| `tools/eligibility.py` | **New** — Deterministic eligibility checker | Medium |
| `tools/max_eligible.py` | **New** — Max amount binary search | Small |

### Guard Rails

```python
# In the @tool wrappers — truncate large outputs to fit context
@tool
def generate_combined_report(customer_id: int) -> dict:
    """..."""
    # Return SUMMARY, not full report (CustomerReport can be 50KB as dict)
    # Full report is saved to PDF — LLM sees only key metrics
    ...

# In agent_node — enforce max iterations via LangGraph's recursion_limit
agent = graph.compile(checkpointer=checkpointer)
result = agent.invoke(state, config={"recursion_limit": 12})  # max 6 tool calls (agent→tool = 2 steps each)
```

### Effort: ~5-7 days (same as Option B, but more capable)

---

## Option E: MCP Server — Expose Tools as a Protocol (Difficulty: Medium-High, Impact: High)

### What Is MCP and Why It Matters Here

MCP (Model Context Protocol) is a standard protocol for exposing tools/resources to LLMs. Instead of hardcoding tools into the pipeline, you run a **server** that advertises tools, and any MCP-compatible client (Claude Desktop, custom LangChain client, other agents) can discover and call them.

**Why this fits this project specifically:**
- The system has 25+ deterministic tools that are currently locked inside `executor.tool_map`
- Credit officers, auditors, or downstream systems may want to call these tools independently
- Multiple UIs (Streamlit, CLI, batch, future mobile) all need the same tools — MCP gives one protocol

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  MCP Server (runs as local process)                     │
│                                                         │
│  Exposes tools via JSON-RPC over stdio/SSE:             │
│    • generate_combined_report(customer_id)               │
│    • check_eligibility(customer_id, product, amount)     │
│    • bureau_delinquency_check(customer_id)               │
│    • get_income_stability(customer_id)                   │
│    • max_eligible_amount(customer_id, product)           │
│    • compute_scorecard(customer_id)                      │
│    • ... all 25+ tools                                   │
│                                                         │
│  Also exposes resources:                                 │
│    • customer://{id}/report  → cached report data        │
│    • policy://rules/{product} → policy rules for product │
│    • thresholds://current     → current threshold values │
│                                                         │
│  Also exposes prompts:                                   │
│    • eligibility_analysis → pre-built prompt template    │
│    • risk_summary → template for risk narration          │
└──────────┬──────────────────────────────────────────────┘
           │ JSON-RPC (stdio or SSE)
           │
     ┌─────┴──────┐     ┌──────────────┐     ┌──────────────┐
     │ Streamlit  │     │ Claude       │     │ Batch        │
     │ app.py     │     │ Desktop      │     │ Pipeline     │
     │ (LangGraph │     │ (native MCP  │     │ (direct MCP  │
     │  client)   │     │  client)     │     │  calls)      │
     └────────────┘     └──────────────┘     └──────────────┘
```

### Implementation

```python
# mcp_server/server.py

from mcp.server import Server
from mcp.types import Tool, TextContent
import json

server = Server("kotak-financial-tools")


# ── Tool Registration ─────────────────────────────────────────────

@server.tool()
async def generate_combined_report(customer_id: int) -> list[TextContent]:
    """Generate a full combined banking + bureau credit report.
    Returns report summary with income, FOIR, DPD, exposure, and PDF path."""
    from tools.combined_report import generate_combined_report_pdf
    cust, bureau, pdf_path = generate_combined_report_pdf(customer_id)
    summary = _build_report_summary(cust, bureau, pdf_path)
    return [TextContent(type="text", text=json.dumps(summary, indent=2))]


@server.tool()
async def check_eligibility(
    customer_id: int,
    product: str,
    amount: float,
    tenure_months: int = 60,
    rate_pct: float = 12.0,
) -> list[TextContent]:
    """Check loan eligibility against credit policy rules.
    Products: PL, BL, HL, AL, LAP, CC.
    Returns per-rule pass/fail, verdict, and max eligible amount if failed."""
    from tools.eligibility import check_eligibility as _check
    result = _check(customer_id, product, amount, tenure_months, rate_pct)
    return [TextContent(type="text", text=json.dumps(result.__dict__, indent=2))]


@server.tool()
async def bureau_delinquency_check(customer_id: int) -> list[TextContent]:
    """Quick DPD/delinquency check from bureau data.
    Returns max DPD, affected products, adverse events, severity."""
    from tools.bureau_chat import bureau_delinquency_check as _check
    result = _check(customer_id)
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


@server.tool()
async def compute_scorecard(customer_id: int) -> list[TextContent]:
    """Compute risk scorecard: verdict (LOW/CAUTION/HIGH RISK),
    per-signal RAG status, strengths, concerns, and verification items."""
    from tools.scorecard import compute_scorecard as _compute
    # Need report data first
    from tools.combined_report import generate_combined_report_pdf
    cust, bureau, _ = generate_combined_report_pdf(customer_id)
    result = _compute(cust, bureau)
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ── Resource Registration ─────────────────────────────────────────
# Resources expose data that LLMs can read without calling a tool

@server.resource("policy://rules/{product}")
async def get_policy_rules(product: str) -> str:
    """Return policy rules for a specific loan product as structured text."""
    from config.policy_rules import get_rules_for_product
    rules = get_rules_for_product(product)
    return json.dumps([r.__dict__ for r in rules], indent=2)


@server.resource("thresholds://current")
async def get_thresholds() -> str:
    """Return all current threshold values from config/thresholds.py."""
    import config.thresholds as T
    return json.dumps({k: v for k, v in vars(T).items() if not k.startswith("_")}, indent=2)


# ── Prompt Registration ───────────────────────────────────────────
# Pre-built prompt templates that clients can request

@server.prompt()
async def eligibility_analysis(customer_id: str, product: str, amount: str) -> list:
    """Structured prompt for running a full eligibility analysis."""
    return [
        {"role": "system", "content": (
            "You are a credit analyst. Use the available tools to: "
            "1. Generate the combined report for the customer. "
            "2. Check eligibility for the requested product and amount. "
            "3. If not eligible, find the maximum eligible amount. "
            "4. Summarise findings with specific numbers."
        )},
        {"role": "user", "content": (
            f"Analyse customer {customer_id} for a {product} loan of ₹{amount}. "
            "Generate the report, check eligibility, and recommend."
        )},
    ]


# ── Server Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream)

    asyncio.run(main())
```

### MCP + LangGraph Integration

The MCP server can be consumed by a LangGraph agent using `langchain-mcp-adapters`:

```python
# pipeline/core/mcp_agent.py

# Option 1: Direct MCP client in LangGraph
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama

async def build_mcp_agent():
    """Build LangGraph agent that discovers tools from MCP server."""
    async with MultiServerMCPClient({
        "financial-tools": {
            "command": "python",
            "args": ["mcp_server/server.py"],
            "transport": "stdio",
        }
    }) as client:
        tools = client.get_tools()  # Auto-discovers all tools from server
        llm = ChatOllama(model="mistral", temperature=0)
        agent = create_react_agent(llm, tools)
        return agent

# Option 2: Claude Desktop connects directly to MCP server
# User adds to claude_desktop_config.json:
# {
#   "mcpServers": {
#     "kotak-financial": {
#       "command": "python",
#       "args": ["/path/to/mcp_server/server.py"]
#     }
#   }
# }
# Now Claude Desktop can call generate_combined_report, check_eligibility etc.
```

### Why MCP Specifically Fits This Project

| Current Problem | How MCP Solves It |
|---|---|
| 25+ tools locked in `executor.tool_map`, only accessible via intent pipeline | MCP exposes all tools over standard protocol — any client can call them |
| Adding a tool = editing 4 files (intents, executor, planner, prompts) | Adding a tool = one `@server.tool()` decorator — auto-discovered by all clients |
| Streamlit is the only UI | MCP server works with Claude Desktop, any LangChain app, custom UIs, batch scripts |
| Policy rules hardcoded in Python | MCP resources expose rules as readable data — auditors can inspect without code access |
| No way for external systems to use the analytics | MCP server = an API for all financial tools |

### Files to Create/Change

| File | Change | Effort |
|---|---|---|
| `mcp_server/server.py` | **New** — MCP server with all tool/resource/prompt registrations | Large |
| `mcp_server/__init__.py` | **New** — Package init | Trivial |
| `pipeline/core/mcp_agent.py` | **New** — LangGraph agent consuming MCP tools (optional) | Small |
| `requirements.txt` | Add `mcp>=1.0`, `langchain-mcp-adapters` | Trivial |
| `tools/eligibility.py` | **New** — Same as other options | Medium |

### Pros & Cons

| Pros | Cons |
|---|---|
| Standard protocol — works with Claude Desktop, other agents | Additional process to manage (MCP server) |
| Tool discovery is automatic — no manual registration | `mcp` package not yet installed (easy to add) |
| Resources expose config/thresholds as readable data | Async requirement — existing tools are sync (needs wrapping) |
| Prompts as reusable templates — clients request by name | Overhead for simple single-user Streamlit use |
| Future-proof: any MCP-compatible agent can use these tools | Team must learn MCP concepts (tools, resources, prompts) |
| Separation of concerns: tools = server, agent = client | Extra latency from stdio/SSE transport (small, ~ms) |

### Effort: ~7-10 days

---

## Option F: LangGraph Multi-Agent with Supervisor (Difficulty: High, Impact: Very High)

### When You Need This

When the problem grows beyond "generate report + check eligibility" to:
- "Generate report, check eligibility, run stress test, compare with 3 peer customers, and produce a recommendation memo"
- "Batch-evaluate 50 customers and flag the top 10 riskiest for manual review"
- "Analyse this customer from both a credit risk and a compliance perspective"

A single agent with 25+ tools gets confused. Multiple specialised agents, coordinated by a supervisor, handle this better.

### Architecture

```
                        ┌──────────────────────────────┐
                        │       SUPERVISOR AGENT       │
                        │  (mistral or deepseek-r1)    │
                        │                              │
                        │  Decides which specialist    │
                        │  to delegate to next.        │
                        │  Sees summaries, not raw     │
                        │  tool outputs.               │
                        └─────────┬────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼──────┐  ┌────────▼───────┐  ┌───────▼────────┐
    │  REPORT AGENT  │  │ ELIGIBILITY    │  │ RISK AGENT     │
    │                │  │ AGENT          │  │                │
    │ Tools:         │  │ Tools:         │  │ Tools:         │
    │ • gen_combined │  │ • check_elig   │  │ • delinquency  │
    │ • gen_customer │  │ • max_eligible │  │ • scorecard    │
    │ • gen_bureau   │  │ • stress_test  │  │ • key_findings │
    │ • income_stab  │  │ • policy_rules │  │ • anomaly_det  │
    └────────────────┘  └────────────────┘  └────────────────┘
```

### Implementation with LangGraph

```python
# pipeline/core/multi_agent.py

from typing import Literal, TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import create_react_agent
import operator


# ── State shared across all agents ────────────────────────────────

class SupervisorState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    next_agent: str | None
    final_answer: str | None


# ── Specialist Agents ─────────────────────────────────────────────

def build_report_agent():
    """Agent specialised in generating financial reports."""
    llm = ChatOllama(model="mistral", temperature=0, seed=42)
    report_tools = [generate_combined_report, get_income_stability]  # @tool wrapped
    return create_react_agent(
        llm, report_tools,
        prompt="You generate financial reports. Call generate_combined_report first. "
               "Return a summary of key metrics: income, FOIR, DPD, exposure, verdict."
    )


def build_eligibility_agent():
    """Agent specialised in loan eligibility analysis."""
    llm = ChatOllama(model="mistral", temperature=0, seed=42)
    elig_tools = [check_eligibility, max_eligible_amount, stress_test]
    return create_react_agent(
        llm, elig_tools,
        prompt="You assess loan eligibility. Always state the verdict clearly. "
               "If not eligible, find the maximum eligible amount. "
               "If eligible, run a stress test at +200bps."
    )


def build_risk_agent():
    """Agent specialised in risk assessment."""
    llm = ChatOllama(model="mistral", temperature=0, seed=42)
    risk_tools = [bureau_delinquency_check, compute_scorecard, detect_anomalies]
    return create_react_agent(
        llm, risk_tools,
        prompt="You assess credit risk. Check delinquency first. "
               "Then compute scorecard. Flag any anomalies. "
               "Return a structured risk summary."
    )


# ── Supervisor ────────────────────────────────────────────────────

def build_supervisor():
    """Supervisor that routes tasks to specialist agents."""

    llm = ChatOllama(model="mistral", temperature=0, seed=42)

    # Supervisor doesn't call financial tools — it routes to agents
    def supervisor_node(state: SupervisorState):
        """Decide which agent to delegate to next, or finish."""
        routing_prompt = (
            "You are a supervisor coordinating financial analysis. "
            "Based on the conversation so far, decide the next step.\n\n"
            "Available agents:\n"
            "- report_agent: Generates combined banking + bureau reports\n"
            "- eligibility_agent: Checks loan eligibility, max amounts, stress tests\n"
            "- risk_agent: Delinquency checks, scorecards, anomaly detection\n"
            "- FINISH: All analysis is complete, ready to respond\n\n"
            "Respond with ONLY the agent name or FINISH."
        )
        messages = state["messages"] + [HumanMessage(content=routing_prompt)]
        response = llm.invoke(messages)
        next_agent = response.content.strip().lower()

        if "finish" in next_agent or "done" in next_agent:
            return {"next_agent": "FINISH"}
        elif "eligibility" in next_agent:
            return {"next_agent": "eligibility_agent"}
        elif "risk" in next_agent:
            return {"next_agent": "risk_agent"}
        else:
            return {"next_agent": "report_agent"}

    # Build the graph
    graph = StateGraph(SupervisorState)

    # Nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("report_agent", build_report_agent())
    graph.add_node("eligibility_agent", build_eligibility_agent())
    graph.add_node("risk_agent", build_risk_agent())

    # Edges
    graph.add_edge(START, "supervisor")

    def route_from_supervisor(state):
        next_agent = state.get("next_agent", "FINISH")
        if next_agent == "FINISH":
            return END
        return next_agent

    graph.add_conditional_edges("supervisor", route_from_supervisor, {
        "report_agent": "report_agent",
        "eligibility_agent": "eligibility_agent",
        "risk_agent": "risk_agent",
        END: END,
    })

    # After each agent finishes, go back to supervisor
    graph.add_edge("report_agent", "supervisor")
    graph.add_edge("eligibility_agent", "supervisor")
    graph.add_edge("risk_agent", "supervisor")

    return graph.compile()
```

### Example Execution Trace

```
User: "Full analysis of 698167220: report, BL eligibility for 10L, and risk assessment"

Supervisor → "report_agent" (need the report first)
  Report Agent:
    → generate_combined_report(698167220) → {income: 85K, FOIR: 42%, DPD: 0, ...}
    → "Report generated. Income 85K/mo, FOIR 42%, clean bureau."

Supervisor → "eligibility_agent" (now check eligibility)
  Eligibility Agent:
    → check_eligibility(698167220, BL, 1000000) → {verdict: NOT_ELIGIBLE, FOIR: 68%}
    → max_eligible_amount(698167220, BL) → {max: 750000, FOIR: 61.6%}
    → "Not eligible for 10L BL (FOIR 68%). Max eligible: 7.5L (FOIR 61.6%)."

Supervisor → "risk_agent" (risk assessment)
  Risk Agent:
    → bureau_delinquency_check(698167220) → {max_dpd: 0, clean: true}
    → compute_scorecard(698167220) → {verdict: LOW RISK}
    → "Low risk. Clean bureau, no delinquency, stable income."

Supervisor → "FINISH"
  Final: Combined report at reports/combined_698167220_report.pdf.
         BL 10L: NOT ELIGIBLE (FOIR 68% > 65%). Max eligible: 7.5L.
         Risk: LOW RISK — clean bureau, stable income.
```

### When to Use Multi-Agent vs Single Agent

| Scenario | Single Agent (D) | Multi-Agent (F) |
|---|---|---|
| "Generate combined report" | Yes — one tool call | Overkill |
| "Report + BL eligibility" | Yes — two tool calls | Works but unnecessary |
| "Report + eligibility + risk + stress test + peer comparison" | Struggles — too many tools, confused context | Each specialist handles its domain cleanly |
| Batch: 50 customers, full analysis | Sequential, slow | Specialists can be parallelised per customer |
| Different analysis depth per dimension | All-or-nothing | Supervisor decides depth per specialist |

### Pros & Cons

| Pros | Cons |
|---|---|
| Each agent has 3-5 tools (focused, reliable) | 3-4 LLM instances = higher memory usage |
| Supervisor provides clear audit trail | Supervisor routing adds latency (~2s per hop) |
| Specialists can use different models | Complex graph — harder to debug |
| Parallelisable: agents can run concurrently | Local Ollama is single-threaded per model |
| Natural mapping to org structure (credit, risk, compliance) | Significant architecture change |

### Effort: ~14-20 days

---

## Updated Comparison Matrix (All 6 Options)

| Dimension | A: Multi-Intent | B: LLM Planner | C: Hand ReAct | D: LangGraph | E: MCP Server | F: Multi-Agent |
|---|---|---|---|---|---|---|
| **Difficulty** | Low | Medium | High | Medium | Medium-High | High |
| **Effort** | 3-4d | 5-7d | 10-14d | 5-7d | 7-10d | 14-20d |
| **Framework** | None | None | None | LangGraph | MCP + LangGraph | LangGraph |
| **Already installed** | N/A | N/A | N/A | Yes | No (pip install) | Yes |
| **Tool calling** | Dict lookup | LLM JSON | Prompt parsing | Native bind_tools | MCP protocol | Native bind_tools |
| **Multi-turn** | No | No | No | Yes (checkpointer) | Yes (MCP session) | Yes |
| **External clients** | No | No | No | No | Yes (Claude Desktop, etc.) | No |
| **Composability** | Sidecar only | Single plan | Iterative | Iterative | Protocol-level | Agent-level |
| **Regression risk** | Near zero | Low | Medium | Low | Low | High |
| **Latency** | +0s | +2-3s | +15-25s | +5-15s | +5-15s | +20-40s |
| **Local model compat** | Excellent | Good | Risky | Good (tested) | Good | Moderate |
| **Debugging** | Easy | Medium | Hard | Medium (LangGraph Studio) | Medium | Hard |

---

## Updated Recommendation: Phased (A → D → E)

### Phase 1: Option A — Multi-Intent + Sidecar (Week 1)
Ship immediately. Zero risk. Handles the primary use case.

### Phase 2: Option D — LangGraph StateGraph Agent (Week 2-3)
Replace the sidecar mechanism with a proper LangGraph agent. **This is the sweet spot:**
- Already installed and verified working with Ollama mistral
- Native tool calling — no prompt engineering for tool selection
- Multi-turn via checkpointer — user can ask follow-up questions
- Same effort as Option B but strictly more capable
- Skip Option C entirely — LangGraph does it better

### Phase 3: Option E — MCP Server (Week 4-5, if needed)
Only if external tool access is required (Claude Desktop, other teams, batch systems). Wraps the same tools behind a protocol. LangGraph agent becomes an MCP client.

### Option F — Multi-Agent (Defer)
Only when single-agent (D) demonstrably fails on complex multi-dimensional analysis. Gate on: >10 tools needed per query, or supervisor routing accuracy tested on 50+ queries.

### Why D Before E (Not C, Not B)

| Reason | Detail |
|---|---|
| `langgraph` already installed (1.0.7) | Zero new dependencies |
| `create_react_agent` verified working with Ollama | Tested: mistral returns `tool_calls`, LangGraph executes them |
| Native tool calling > prompt-based ReAct | Ollama `bind_tools()` works — no custom parsing needed |
| Option B (LLM Planner) is a subset of D | D's agent loop IS an LLM planner — but with observation and re-planning |
| Option C (hand-rolled) reinvents LangGraph badly | Same concept, worse implementation, more bugs |
