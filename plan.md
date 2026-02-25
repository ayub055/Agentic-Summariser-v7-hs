# Architecture Advancement Plan
## From Slot-Filling Pipeline → True Agentic Analyst

---

## Current State — What Exists Today

The system today is a **5-stage deterministic pipeline**:

```
Query → IntentParser → INTENT_TOOL_MAP lookup → ToolExecutor → Explainer → Response
```

The "intelligence" lives only in two narrow places:
- `intent_parser.py`: Mistral LLM classifies query into one of 25 predefined enums
- `transaction_flow.py`: Llama3.2 extracts behavioural patterns (only for 3 intents)

**Everything else is deterministic routing.** The planner is not a planner — it is a dictionary lookup. The agent has no ability to reason about what tools to use, chain results together, or handle queries that don't match a predefined enum.

**What this means in practice:**
- "What is the customer's total income?" → works perfectly
- "Is this customer a good lending candidate given their cashflow and bureau history?" → fragile (matched to LENDER_PROFILE or FINANCIAL_OVERVIEW, misses the bureau half)
- "Was the underwriting policy appropriate at the time of loan disbursement?" → fails entirely (no intent exists for this)

---

## Improvement 1 — True Agentic Planning (Replace the Tool Map)

### Problem

The `INTENT_TOOL_MAP` is a static lookup table. The "planner" has no ability to:
- Reason about which tools to call
- Chain tool calls based on intermediate results
- Handle queries that don't match a known enum
- Call tools iteratively (e.g., "check income, then if stable, check bureau")
- Decide on its own when it has enough information

### Proposed Architecture: LangGraph ReAct Agent

Replace the static Phase 1→2→3 (Intent → Plan → Execute) with a **LangGraph agent loop** where an LLM reasons about tools at each step.

#### Core Concept: ReAct Loop

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Analyst Agent (LangGraph StateGraph)                       │
│                                                             │
│  State = { messages, customer_id, tool_results,            │
│            iteration_count, session_context }              │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Node: think                                         │  │
│  │  LLM + all tool schemas → decides which tool to     │  │
│  │  call next (or outputs Final Answer)                 │  │
│  └───────────────────┬──────────────────────────────────┘  │
│                       │                                     │
│           ┌───────────┴──────────────┐                     │
│           │ tool calls found?        │ no tool calls        │
│           ▼                          ▼                      │
│  ┌────────────────┐        ┌───────────────────┐           │
│  │  Node: execute │        │  Node: synthesize │           │
│  │  Run tools,    │        │  Final streamed   │           │
│  │  append results│        │  answer           │           │
│  └────────┬───────┘        └─────────┬─────────┘           │
│           │ loop back                │ → END                │
│           └──────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

#### Agent State Schema

```python
# pipeline/analyst_state.py
class AnalystState(TypedDict):
    messages: List[BaseMessage]       # Full conversation history
    customer_id: Optional[int]        # Active customer context
    tool_results: List[ToolResult]    # Accumulated results this turn
    iteration_count: int              # Guard against infinite loops
    session_context: Dict             # Cross-turn memory
```

#### Key Design Decisions

**1. Tools become proper structured tools**

Every function in `tools/analytics.py`, `tools/bureau_chat.py` etc. gets a proper
LangChain `@tool` decorator with schema. The agent's LLM sees these tool definitions
and decides which to call based on the query — no enum matching required.

The existing `INTENT_TOOL_MAP` is **retired** (or kept as a hint layer, see below).

**2. LLM with function calling**

Use `llama3.1` or `llama3.2` (Ollama), which support native structured tool calls.
The LLM outputs a JSON tool call, the agent executes it and feeds the result back.
No regex parsing of `Thought/Action/Observation` — clean structured JSON calls.

**3. System prompt replaces PARSER_PROMPT + INTENT_TOOL_MAP**

```
You are a financial analyst with access to banking and bureau data tools.
When answering questions about customers:
1. First identify what data you need
2. Call the appropriate tools in sequence
3. Synthesize a complete answer from all tool results
4. Do not call tools you have already called with the same arguments

Available context: customer_id={customer_id}, session={session_summary}
```

The LLM infers the tool sequence from the query — it does not need to be told
"for this query use these 3 tools." It reasons this out itself.

**4. Backward compatibility: Routing Hint Layer**

For queries that clearly match a known intent (e.g., "generate bureau report"),
a lightweight router can **suggest** the tool list to the agent rather than hard-wire it.
This keeps performance good for simple queries while freeing complex queries to plan freely.

```python
# Fast path: if intent confidence > 0.95 AND intent is in INTENT_TOOL_MAP → use map
# Slow path (new): otherwise → pass to full agent loop
```

**5. MAX_ITERATIONS guard**

Replace `MAX_TOOLS_PER_QUERY = 5` with `MAX_ITERATIONS = 8`.
The agent can call the same tool multiple times (e.g., category lookup for 3 categories)
but stops after 8 LLM reasoning rounds.

#### What Changes

| Component | Current | New |
|---|---|---|
| `pipeline/intent_parser.py` | LLM → 25-enum match | LLM → open-ended query understanding, feeds agent system prompt |
| `pipeline/planner.py` | Dict lookup | **Retired** — replaced by agent's internal reasoning |
| `pipeline/executor.py` | Sequential tool dispatch | Becomes `ToolNode` in LangGraph — same tool functions, new wrapper |
| `pipeline/orchestrator.py` | Linear 5-stage | New `AnalystAgent` class using `StateGraph`, keeps streaming API |
| `config/intents.py` | Hard-coded map | Becomes optional routing hint (not required for execution) |

#### What Stays Unchanged

- All tool functions in `tools/` — no changes needed
- All schemas in `schemas/` — no changes needed
- Report generators (`bureau`, `combined`, `customer`) — unchanged
- `app.py` Streamlit UI — same API (`pipeline.query()` / `pipeline.query_stream()`)

#### Example: Complex Query the Old System Couldn't Handle

**Query:** "Is customer 100101174 creditworthy? Consider both their banking behaviour and bureau history."

**Old system:** Maps to either `CUSTOMER_REPORT` or `BUREAU_REPORT` — never both.

**New agent:**
```
Thought: I need banking data and bureau data to assess creditworthiness.
Action: generate_customer_report(customer_id=100101174)
Observation: { salary: 85000/month, EMI: 24000, cashflow: positive ... }

Thought: Now get bureau data.
Action: bureau_overview(customer_id=100101174)
Observation: { max_dpd: 0, total_tradelines: 5, utilization: 42% ... }

Thought: I have both. I can synthesize a complete creditworthiness assessment.
Final Answer: [synthesized narrative combining both]
```

---

## Improvement 2 — Complex Analytical Queries with External Data

### Problem

The example query captures an entirely new class of questions:

> *"Look at the customer's data, and this new data of loan disbursement over which he defaulted
> and the policy parameters. Was the policy appropriate at the time of sourcing?"*

This query requires capabilities that don't exist in the current architecture:

| Requirement | Current State | Gap |
|---|---|---|
| Ingest ad-hoc data (loan disbursement CSV) | ❌ Not supported | Need dynamic data loader |
| Retrieve policy documents semantically | ❌ Not supported | Need RAG layer |
| Reconstruct customer profile "as of" a date | ❌ Not supported | Need temporal engine |
| Evaluate customer against policy thresholds | ❌ Not supported | Need policy evaluator |
| Multi-source synthesis (banking + bureau + policy + loan) | ❌ Partial | Need synthesis chain |
| Causal reasoning ("was it appropriate?") | ❌ Not supported | Need analyst reasoning |

### Proposed Architecture: Multi-Layer Analyst System

```
Complex User Query
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  LAYER 1: QUERY UNDERSTANDING                                     │
│  QueryDecomposer (LLM)                                            │
│  ├─ Identifies data sources needed                                │
│  ├─ Identifies time anchors ("at the time of sourcing")           │
│  ├─ Identifies analysis objectives                                │
│  └─ Outputs: AnalystQuery { sub_queries, time_anchor, sources }   │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│  LAYER 2: PARALLEL DATA GATHERING                                 │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│  │  Banking Agent   │  │  Bureau Agent   │  │  Document Agent  │  │
│  │  (existing tools)│  │  (existing tools│  │  RAG over policy │  │
│  │  filtered to T   │  │  filtered to T  │  │  docs, returns   │  │
│  │                 │  │                 │  │  relevant chunks │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬─────────┘  │
│           │                   │                     │             │
│  ┌────────┴───────────────────┴─────────────────────┘            │
│  │  Dynamic Data Agent                                            │
│  │  Processes uploaded CSV (loan disbursement data)               │
│  │  Auto-detects schema, computes relevant metrics                │
│  └────────────────────────────────────────────────────────────────┘
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│  LAYER 3: TEMPORAL RECONSTRUCTION                                 │
│  TemporalEngine                                                   │
│  ├─ For each data source: filter to state "as of T"               │
│  ├─ Banking: transactions before disbursement date                │
│  ├─ Bureau: tradelines open at T, features computed at T          │
│  └─ Produces: { banking_at_T, bureau_at_T, profile_at_T }        │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│  LAYER 4: POLICY EVALUATION                                       │
│  PolicyEvaluator (deterministic, NO LLM)                         │
│  ├─ Loads applicable policy (by product type + effective date)    │
│  ├─ Checks each policy rule against customer profile at T         │
│  ├─ Produces: PolicyAudit { passed, failed, borderline, flags }   │
│  └─ Example: "Income < threshold: customer earned 65k vs min 80k" │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│  LAYER 5: SYNTHESIS & VERDICT                                     │
│  SynthesisChain (LLM)                                             │
│  ├─ Inputs: banking_at_T + bureau_at_T + policy_audit + loan_data │
│  ├─ Generates: structured narrative with evidence citations        │
│  ├─ Produces verdict: { appropriate | borderline | inappropriate } │
│  └─ Supports streaming output                                     │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
                    Streamed Response to UI
```

### New Components

#### A. QueryDecomposer (`pipeline/query_decomposer.py`)

LLM that parses a complex open-ended query into a structured analytical task:

```python
class AnalystQuery:
    original_query: str
    sub_queries: List[str]         # Atomic questions to answer
    data_sources_needed: List[str] # ["banking", "bureau", "policy", "uploaded"]
    time_anchor: Optional[str]     # "2023-06-15" = "at time of sourcing"
    analysis_type: str             # "policy_audit" | "creditworthiness" | "forensic"
    output_format: str             # "verdict" | "report" | "narrative"
```

LLM takes the raw query and outputs this structured object. This replaces the current
narrow IntentType enum with open-ended query understanding.

#### B. RAG Layer — Document Store (`pipeline/document_store.py`)

Stores policy documents, underwriting guidelines, product manuals as searchable vector embeddings.

```
data/
├── policies/
│   ├── personal_loan_policy_v1.pdf    (effective 2020-01-01 to 2022-12-31)
│   ├── personal_loan_policy_v2.pdf    (effective 2023-01-01 onwards)
│   ├── credit_card_policy.pdf
│   └── home_loan_underwriting.yaml    (structured rules — machine-readable)
└── vector_store/                      (ChromaDB persisted index)
    └── chroma.sqlite3
```

**Key design — temporal policy retrieval:**

Every policy document carries metadata: `product`, `effective_from`, `effective_to`.
When the query asks "at the time of sourcing (2023-06-15)", the retriever filters to
policies valid on that date before doing semantic search.

```python
def retrieve_policy(product: str, date: str, query: str) -> List[PolicyChunk]:
    """Return policy chunks relevant to query, valid on the given date."""
```

**Technology:** ChromaDB (local, no API key, persists to disk) + `sentence-transformers`
for embeddings (runs on CPU, no external calls).

#### C. Dynamic Data Loader (`pipeline/dynamic_data_loader.py`)

Accepts ad-hoc CSV/Excel/JSON uploads and makes them queryable within a session.

```python
class DynamicDataset:
    name: str                         # "loan_disbursement_data"
    schema: Dict[str, str]            # Auto-detected column types
    df: pd.DataFrame                  # The actual data
    generated_tools: List[Callable]   # Auto-generated query tools
```

When user uploads "loan_disbursement.csv", the system:
1. Detects schema: `customer_id, loan_amount, disbursement_date, product, default_flag, ...`
2. Auto-generates tools: `get_loan_details(customer_id)`, `get_default_history(customer_id)`
3. Registers these tools in the agent's tool registry for this session
4. Cleans up after session ends

This is the key enabler for: *"this new data of loan disbursement over which he defaulted"*

#### D. Temporal Engine (`pipeline/temporal_engine.py`)

Reconstructs any customer's profile "as of" a specific date.

```python
def get_banking_as_of(customer_id: int, as_of_date: str) -> TemporalBankingContext:
    """Return banking metrics computed using only transactions before as_of_date."""
    # Filter transactions: tran_date <= as_of_date
    # Re-compute: income, spending, cashflow, EMI, stability score
    # Return: same structure as current tools but date-bounded

def get_bureau_as_of(customer_id: int, as_of_date: str) -> TemporalBureauContext:
    """Return bureau snapshot: only tradelines opened before as_of_date."""
    # Filter: date_opened <= as_of_date
    # Re-compute: utilization, DPD, delinquency, portfolio summary
```

This answers: *"Was the customer's profile acceptable at the time of sourcing (June 2023)?"*
even if the analysis is being done today (Feb 2026) with 3 years of additional data.

#### E. Policy Evaluator (`pipeline/policy_evaluator.py`)

Deterministic rule engine — no LLM — checks customer profile against policy thresholds.

Policy rules stored as structured YAML:

```yaml
# data/policies/personal_loan_policy_v2.yaml
product: personal_loan
effective_from: 2023-01-01
rules:
  - id: income_threshold
    field: banking.avg_monthly_income
    operator: ">="
    value: 25000
    severity: hard_reject
    message: "Minimum monthly income not met"

  - id: max_obligations
    field: banking.emi_to_income_ratio
    operator: "<="
    value: 0.50
    severity: hard_reject
    message: "EMI obligations exceed 50% of income"

  - id: bureau_dpd
    field: bureau.max_dpd_last_12m
    operator: "=="
    value: 0
    severity: hard_reject
    message: "Active delinquency in last 12 months"

  - id: cc_utilization
    field: bureau.cc_utilization_pct
    operator: "<="
    value: 70
    severity: soft_flag
    message: "Credit card utilization above 70%"
```

The evaluator:
1. Loads the applicable policy (by product + date)
2. Evaluates every rule against the temporal profile
3. Returns: `PolicyAudit { hard_rejects, soft_flags, passed_rules, overall_verdict }`
4. **Fully deterministic** — same principle as existing `key_findings.py`

#### F. Synthesis Chain (`pipeline/synthesis_chain.py`)

Final LLM call that synthesizes all structured inputs into a coherent narrative:

```
Input context to LLM:
  1. Customer banking profile at T (structured dict)
  2. Customer bureau snapshot at T (structured dict)
  3. Policy audit result (passed/failed rules with messages)
  4. Loan disbursement facts (from uploaded data)
  5. Original user question

Output:
  - Executive verdict: APPROPRIATE / BORDERLINE / INAPPROPRIATE
  - Evidence summary per finding
  - Risk factors the underwriter should have caught
  - Hindsight analysis (what happened after sourcing)
```

The LLM narrates from pre-computed structured data — same principle as existing
`generate_bureau_review()` and `generate_customer_persona()`. No raw data touches the LLM.

### New Schemas

```
schemas/
├── analyst_query.py       # AnalystQuery, SubQuery, AnalysisType
├── policy.py              # PolicyRule, PolicyAudit, PolicyVerdict
├── temporal_context.py    # TemporalBankingContext, TemporalBureauContext
├── analysis_result.py     # AnalysisResult, EvidenceItem, Verdict
└── dynamic_dataset.py     # DynamicDataset, GeneratedTool
```

### New Dependencies

| Package | Purpose | Local/Remote |
|---|---|---|
| `langgraph` | Agent state machine | Local |
| `chromadb` | Vector store for policies | Local (disk) |
| `sentence-transformers` | Text embeddings | Local (CPU) |
| `langchain-community` | Document loaders (PDF, YAML) | Local |
| `pydantic-settings` | Environment config | Local |

No external API calls. All inference runs on Ollama.

---

## Implementation Roadmap

### Phase 1 — Agentic Planner (Problem 1)
*Prerequisites: None. Can be built alongside existing system.*

1. Wrap all `tools/analytics.py` functions with proper `@tool` schemas
2. Create `pipeline/analyst_agent.py` as a LangGraph `StateGraph`
3. Add "agent mode" flag to `TransactionPipeline` — default OFF
4. Test: same queries, same results, but no tool_map dependency
5. Gradually retire `INTENT_TOOL_MAP` for simple queries

### Phase 2 — Document Store + RAG
*Prerequisites: Phase 1 (agent needs to call the retriever as a tool)*

1. Set up ChromaDB at `data/vector_store/`
2. Create `pipeline/document_store.py` with temporal metadata filtering
3. Add `retrieve_policy(product, date, query)` as a registered agent tool
4. Load initial policy documents

### Phase 3 — Temporal Engine
*Prerequisites: Phase 1*

1. Build `pipeline/temporal_engine.py` with date-bounded re-computation
2. Add `get_banking_as_of(customer_id, date)` and `get_bureau_as_of(customer_id, date)` as tools
3. Agent learns to call these when query contains temporal keywords ("at time of", "when sourced")

### Phase 4 — Dynamic Data Loader
*Prerequisites: Phase 1*

1. Build `pipeline/dynamic_data_loader.py`
2. Add file upload endpoint to `app.py` (Streamlit `st.file_uploader`)
3. Auto-schema detection and tool generation
4. Session-scoped tool registry

### Phase 5 — Policy Evaluator + Synthesis
*Prerequisites: Phases 2, 3, 4*

1. Define policy YAML schema and load initial policies
2. Build `pipeline/policy_evaluator.py` (deterministic rule engine)
3. Build `pipeline/synthesis_chain.py` for multi-source narrative
4. Build `pipeline/query_decomposer.py` for complex query parsing
5. Wire full pipeline: decompose → gather (parallel) → temporal → evaluate → synthesize

---

## Architecture Diagram — Target State

```
                        USER QUERY
                             │
                             ▼
                    ┌─────────────────┐
                    │ QueryDecomposer  │  LLM understands intent,
                    │                 │  data sources, time anchor
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────────┐
              ▼              ▼                  ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
    │  Analyst     │  │  Dynamic     │  │  Document        │
    │  Agent       │  │  Data Loader │  │  Store (RAG)     │
    │  (LangGraph) │  │  (uploaded   │  │  (ChromaDB)      │
    │              │  │   CSVs)      │  │                  │
    │  Calls:      │  └──────┬───────┘  └────────┬─────────┘
    │  ├ analytics  │         │                   │
    │  ├ bureau     │         │                   │
    │  ├ temporal   │◄────────┴───────────────────┘
    │  └ policy RAG │   All results flow into agent context
    └──────┬───────┘
           │
           ▼
  ┌────────────────────┐
  │  Temporal Engine   │  Reconstruct profile "as of T"
  └────────┬───────────┘
           │
           ▼
  ┌────────────────────┐
  │  Policy Evaluator  │  Deterministic rule check (no LLM)
  │  (YAML rules)      │
  └────────┬───────────┘
           │
           ▼
  ┌────────────────────┐
  │  Synthesis Chain   │  LLM narrates from structured inputs
  └────────┬───────────┘
           │
           ▼
      STREAMED RESPONSE
    (verdict + evidence + narrative)
```

---

## Guiding Principles (Extends Existing `instructions.md`)

1. **LLM plans, functions compute** — The agent's LLM decides *what* to do. Deterministic Python
   functions do the *actual computation*. Numbers never come from LLM inference.

2. **Temporal context is first-class** — Every tool that accesses data must support an
   `as_of_date` parameter. Historical analysis is not a special case.

3. **Uploaded data is ephemeral** — Dynamic datasets exist only for the session.
   Tools generated from uploaded data are never persisted.

4. **Policy rules are auditable** — Every rule check produces a traceable output linking
   the rule ID, threshold, actual value, and pass/fail. No black-box verdicts.

5. **Streaming remains the default** — Even for complex multi-agent flows, each layer
   yields partial results as they complete. The user sees progress, not a loading spinner.

6. **Fail-soft at every layer** — If the policy evaluator can't find the applicable policy,
   it returns "policy not available" rather than crashing. Same for RAG misses.

7. **Agent has an escape hatch** — If the Analyst Agent cannot decompose or answer a query
   after MAX_ITERATIONS, it returns a structured "I need more information" response with
   what data would be needed, rather than a hallucinated answer.
