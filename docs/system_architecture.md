# System Architecture Document
## Kotak Agentic Financial Intelligence Platform

> **Classification:** Internal Technical Reference
> **Audience:** Engineers, Technical Stakeholders, Investors
> **Last Updated:** 2026-03

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [High-Level System Architecture](#2-high-level-system-architecture)
3. [Core Modules and Components](#3-core-modules-and-components)
4. [Detailed Functionality Breakdown](#4-detailed-functionality-breakdown)
5. [Data Flow Explanation](#5-data-flow-explanation)
6. [Key Algorithms and Logic](#6-key-algorithms-and-logic)
7. [Design Principles Used](#7-design-principles-used)
8. [Change-Based Scenarios](#8-change-based-scenarios)
9. [Extensibility and Scalability](#9-extensibility-and-scalability)
10. [Deployment Architecture](#10-deployment-architecture)
11. [Complete Execution Walkthrough](#11-complete-execution-walkthrough)
12. [Folder Structure Explanation](#12-folder-structure-explanation)
13. [Key Technical Decisions](#13-key-technical-decisions)
14. [System Strengths](#14-system-strengths)
15. [Possible Improvements](#15-possible-improvements)

---

## 1. Project Overview

### Purpose

This platform is an **AI-powered financial intelligence system** designed to automate the analysis of banking transaction data and credit bureau data for lending decisions. It converts raw financial data into analyst-grade reports and answers natural language queries — work that would otherwise require a trained credit analyst to perform manually.

### Problem It Solves

Loan underwriting teams face three bottlenecks:

1. **Volume** — Reviewing raw transaction CSV data for hundreds of customers per day is not humanly scalable.
2. **Consistency** — Human analysts apply domain rules inconsistently across customers.
3. **Latency** — Generating a banking + bureau combined report takes hours when done manually.

This system reduces report generation to seconds and query answering to sub-10-second responses, while applying consistent deterministic rules for every customer.

### Target Users

- **Loan underwriters** — Ask natural language questions about a customer's financials and get instant structured answers.
- **Credit analysts** — Generate comprehensive PDF reports (banking + bureau) for file review.
- **Risk managers** — Query portfolio-level patterns and anomalies.

### High-Level Idea

The system combines three capabilities in one platform:

1. **Conversational Query Engine** — A user types a question like "What did customer 5004898 spend on betting in the last 6 months?" and gets an accurate, sourced answer within seconds.

2. **Automated Report Generation** — Full PDF reports combining banking transaction analysis with credit bureau tradeline analysis, including LLM-generated executive summaries.

3. **Semantic Event Detection** — Beyond raw numbers, the system identifies meaningful financial events: PF withdrawals, post-salary fund routing, NACH bounces, salary advances, FD premature closures — and explains their implications for lending.

---

## 2. High-Level System Architecture

### Architecture Style

The system follows a **Layered + Pipeline architecture** with an embedded **agentic loop** for query handling. It is not a microservices architecture — it is a single-process Python application with clearly separated layers that could be decomposed into services in a future version.

Key characteristics:
- **Separation of deterministic and LLM logic** — all data extraction and computation is pure Python; LLMs are used only for parsing, narration, and summarisation
- **Fail-soft everywhere** — LLM failures never block report generation
- **Schema-first** — every interface between modules is a typed Pydantic or dataclass schema
- **Local LLM deployment** — all models run via Ollama on-premises; no data leaves the machine

### Major Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                           │
│                                                                     │
│   ┌─────────────────────┐         ┌──────────────────────────┐     │
│   │   app.py            │         │   main.py                │     │
│   │   Streamlit Web UI  │         │   CLI Interface          │     │
│   │   (Branded, Kotak)  │         │   (Demo / Dev)           │     │
│   └──────────┬──────────┘         └────────────┬─────────────┘     │
└──────────────┼─────────────────────────────────┼───────────────────┘
               │                                 │
               ▼                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PIPELINE CORE LAYER                            │
│                                                                     │
│   TransactionPipeline (orchestrator.py)                             │
│                                                                     │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│   │  Intent    │  │  Query     │  │  Tool      │  │ Response   │  │
│   │  Parser    │→ │  Planner   │→ │  Executor  │→ │ Explainer  │  │
│   │  (LLM)     │  │ (Determ.)  │  │ (Determ.)  │  │  (LLM)     │  │
│   └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
│                                         │                           │
│                                   ┌─────▼──────┐                   │
│                                   │  Insight   │                   │
│                                   │  Extractor │                   │
│                                   │   (LLM)    │                   │
│                                   └────────────┘                   │
└──────────────────────────────────────┬──────────────────────────── ┘
                                       │
               ┌───────────────────────┼───────────────────────┐
               ▼                       ▼                       ▼
┌──────────────────────┐ ┌─────────────────────┐ ┌────────────────────┐
│   ANALYTICS TOOLS    │ │  REPORT GENERATION  │ │  BUREAU TOOLS      │
│                      │ │                     │ │                    │
│  analytics.py        │ │  report_orchestrator│ │  bureau.py         │
│  transaction_fetcher │ │  customer_report_   │ │  bureau_chat.py    │
│  category_resolver   │ │    builder          │ │  bureau_report_    │
│  account_quality     │ │  bureau_report_     │ │    builder         │
│  event_detector      │ │    builder          │ │  bureau_feature_   │
│  scorecard           │ │  report_summary_    │ │    extractor       │
│                      │ │    chain (LLM)      │ │  tradeline_feature_│
│                      │ │  key_findings       │ │    extractor       │
└──────────┬───────────┘ └──────────┬──────────┘ └──────────┬─────── ┘
           │                        │                        │
           └───────────────────────┬┘                        │
                                   ▼                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                  │
│                                                                     │
│   ┌────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│   │  data/loader   │  │  config/         │  │  features/        │  │
│   │  rgs.csv       │  │  categories.yaml │  │  BureauFeature    │  │
│   │  dpd_data.csv  │  │  settings.py     │  │  Vector           │  │
│   │  rg_sal*.csv   │  │  thresholds.py   │  │  Tradeline        │  │
│   │  tl_features   │  │  prompts.py      │  │  Features         │  │
│   └────────────────┘  └──────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
               │                       │
               ▼                       ▼
┌──────────────────────┐   ┌──────────────────────────────────────────┐
│  RENDERING LAYER     │   │  LOCAL LLM LAYER (Ollama)                │
│                      │   │                                          │
│  pdf_renderer        │   │  mistral        → Intent parsing (JSON)  │
│  bureau_pdf_renderer │   │  llama3.2       → Query explanation       │
│  combined_renderer   │   │  deepseek-r1:14b→ Report summaries        │
│  templates/*.html    │   │                  (with think stripping)   │
└──────────────────────┘   └──────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|---|---|
| **Streamlit UI** | User interaction, stage progress, PDF downloads, streaming display |
| **TransactionPipeline** | Coordinates all pipeline phases, manages session state |
| **IntentParser** | Converts natural language to structured ParsedIntent (44 intent types) |
| **QueryPlanner** | Validates intent, checks data availability, builds execution plan |
| **ToolExecutor** | Runs analytics/report tools, collects ToolResult objects |
| **ResponseExplainer** | Narrates tool results in natural language (streaming) |
| **Analytics Tools** | Pure-function data computations over transaction data |
| **Report Builders** | Deterministic data aggregation into typed report schemas |
| **LLM Summary Chain** | Generates 2-paragraph professional summaries from structured data |
| **Event Detector** | Identifies semantic events (PF withdrawal, salary routing, bounces) |
| **Bureau Extractors** | Processes credit bureau DPD data into feature vectors |
| **PDF/HTML Renderers** | Converts typed report schemas to PDF/HTML output |
| **Data Loader** | Cached CSV loading with column normalisation |

---

## 3. Core Modules and Components

### 3.1 Configuration Module (`config/`)

**Purpose:** Single source of truth for all system parameters — models, paths, thresholds, prompts, and category definitions.

| File | Responsibility |
|---|---|
| `settings.py` | Model names, file paths, LLM parameters, feature flags |
| `prompts.py` | All LLM prompt templates (8 prompts, never inline in code) |
| `thresholds.py` | All risk threshold constants (DPD, utilisation, IPT, enquiry) |
| `intents.py` | Intent → tool mapping (44 intents), required field validation |
| `categories.yaml` | Category definitions (keywords, direction, display name, aliases) |
| `category_loader.py` | YAML loader with `@lru_cache`, fuzzy alias resolution |
| `section_tools.py` | Maps report sections to builder functions |

**Key Design:** No threshold, prompt, or model name is hardcoded in business logic. All live in `config/`. Changing a threshold requires touching exactly one file.

**Dependencies:** Consumed by every module in the system. No outbound dependencies.

---

### 3.2 Schema Module (`schemas/`)

**Purpose:** Define all data contracts between modules using Pydantic and Python dataclasses.

| Schema | Fields | Used By |
|---|---|---|
| `ParsedIntent` | intent, customer_id, category, dates, confidence, raw_query | Parser → Planner → Executor → Explainer |
| `CustomerReport` | meta, salary, emis, rent, bills, cashflow, events, account_quality, customer_review | Builder → Renderer |
| `BureauReport` | meta, feature_vectors, executive_inputs, tradeline_features, narrative | Bureau Builder → Renderer |
| `ToolResult` | tool_name, args, result, success, error | Executor → Explainer |
| `PipelineResponse` | answer, data, intent, tools_used, success | Pipeline → UI |
| `TransactionInsights` | patterns, confidence, customer_id | Insight Extractor → Explainer |
| `CategoryPresenceResult` | present, total_amount, supporting_transactions | Category Tool → Explainer |
| `BureauLoanFeatureVector` | counts, amounts, vintage, DPD, utilisation, forced events | Extractor → Aggregator |
| `TradelineFeatures` | portfolio-level risk metrics | Extractor → Summary Chain |

**Key Design:** Schemas use `Optional` fields everywhere — reports are built incrementally. Pydantic's `model_copy(update={...})` is used for immutable updates (Pydantic v2 pattern).

---

### 3.3 Pipeline Core Module (`pipeline/core/`)

**Purpose:** The agentic query-answering loop — receives a natural language query and produces a sourced, explained answer.

#### `orchestrator.py` — TransactionPipeline

The main coordinator. Five sequential phases per query:

```
Phase 1: parse     → IntentParser.parse(query) → ParsedIntent
Phase 2: plan      → QueryPlanner.create_plan(intent) → List[Dict]
Phase 3: execute   → ToolExecutor.execute(plan) → List[ToolResult]
Phase 3.5: insights → get_transaction_insights_if_needed() → TransactionInsights
Phase 4: explain   → ResponseExplainer.stream_explain() → Iterator[str]
Phase 5: audit     → AuditLogger.log(entry)
```

**Session management:** Stores `active_customer_id` — if a query omits customer ID, the session ID is applied as fallback. Enables conversation context ("now show me their bureau report").

#### `intent_parser.py` — IntentParser

**Primary path (LLM):** Uses `ChatOllama` with `format="json"` constraint and `PARSER_PROMPT` to extract a structured `ParsedIntent`. Post-processing normalises category names and validates intent enum values.

**Fallback path (regex):** When the LLM returns malformed JSON or times out, a deterministic regex pattern set covers all 44 intents. Priority-ordered to handle ambiguous matches correctly (e.g., "category_presence_lookup" before "spending_by_category").

**Confidence scoring:** Dynamic 0–1 score based on field completeness:
- +0.2 for valid customer_id
- +0.1 for dates, category, known intent
- -0.3 for UNKNOWN intent
- Capped at 1.0

#### `planner.py` — QueryPlanner

Entirely deterministic. No LLM. Validates:
- Required fields for each intent type
- Customer ID exists in the relevant dataset
- Category is valid (or fuzzy-matched)
- Date range is logical

Outputs an execution plan: an ordered list of `{tool: str, args: Dict}` steps.

#### `executor.py` — ToolExecutor

Runs each step in the plan sequentially. Wraps every tool call in try/except — a failing tool produces a failed `ToolResult` but does not abort the remaining steps. The pipeline always reaches the explainer.

Tool registry is a flat `Dict[str, Callable]` defined in the executor — adding a new tool means registering one entry.

#### `explainer.py` — ResponseExplainer

Two modes:
- **`explain()`** — Synchronous, returns string. Used when streaming is disabled.
- **`stream_explain()`** — Yields string chunks. Used by Streamlit for real-time display.

Both modes apply `strip_think()` / `stream_strip_think()` transparently — the DeepSeek-R1 `<think>` block is extracted, logged at DEBUG level, and never shown to the user.

---

### 3.4 Report Generation Module (`pipeline/reports/`)

**Purpose:** Generate comprehensive, multi-section PDF reports from structured data.

#### `report_orchestrator.py`

Single public function: `generate_customer_report_pdf(customer_id, months, ...)`. Coordinates the entire report pipeline:

1. Validate customer
2. (Optional) Run `ReportPlanner` — LLM decides sections
3. Run `build_customer_report()` — deterministic data collection
4. Attach `account_quality` and `events` — from dedicated tools
5. (Optional) Generate LLM summaries — persona + review
6. Render PDF + HTML

Caches reports by `(customer_id, period)` — subsequent calls within a session are instant.

#### `customer_report_builder.py`

The largest deterministic module. Calls the data layer and analytics tools to populate each `CustomerReport` field:

| Section | Source | Logic |
|---|---|---|
| `category_overview` | rgs.csv | Group debits by category, sum amounts |
| `monthly_cashflow` | rgs.csv | Group by month, separate inflow/outflow |
| `top_merchants` | rgs.csv | Frequency count of `tran_partclr`, top-N |
| `salary` | rg_sal_strings.csv + rgs.csv | Salary algorithm output + transaction match |
| `emis` | rgs.csv | Narration keyword + amount pattern matching |
| `rent` | rgs.csv | Narration keyword + regularity matching |
| `bills` | rgs.csv | Utility keywords + category matching |
| `account_quality` | `account_quality.py` | Conduit/primary/secondary classification |
| `events` | `event_detector.py` | Two-layer semantic event detection |

#### `report_summary_chain.py`

Four LLM generation functions, all using `SUMMARY_MODEL` (`deepseek-r1:14b`):

| Function | Prompt | Output |
|---|---|---|
| `generate_customer_review()` | `CUSTOMER_REVIEW_PROMPT` | 2-paragraph banking review |
| `generate_customer_persona()` | `CUSTOMER_PERSONA_PROMPT` | 4–5 line customer profile |
| `generate_bureau_review()` | `BUREAU_REVIEW_PROMPT` | 2-paragraph bureau analysis |
| `generate_combined_executive_summary()` | `COMBINED_EXECUTIVE_PROMPT` | 6–8 line merged summary |

All four call `strip_think()` on the raw output before returning.

**`_build_data_summary()`** — constructs the LLM input from the typed `CustomerReport`. Produces:
- Top spending categories
- Monthly cashflow summary
- Salary data
- EMI and rent
- Account quality observations (as plain facts, no score labels)
- Event block from `format_events_for_prompt()`

**`_compute_interaction_signals()`** — deterministic cross-feature risk interpretations for the bureau prompt:
- Dual leverage (CC util + PL balance)
- Credit hungry + loan stacking
- Rapid PL stacking
- Clean repayment profile
- Payment timing nuance (0% missed but DPD > 0)
- Elevated leverage signal

---

### 3.5 Tools Module (`tools/`)

**Purpose:** Pure analytics functions that take structured arguments and return `Dict[str, Any]`. No side effects. No LLM calls (except in report-generating tools).

#### `event_detector.py` — Two-Layer Event Detection

**Layer 1 — Keyword Rules (`KEYWORD_RULES`):**
A configuration-driven table of event types with narration keyword patterns. Supports `min_months` for recurring events (SIP, insurance) and per-occurrence events (PF withdrawal, BNPL).

Currently defined rules:
- `pf_withdrawal` — EPFO, PF SETTL, PROVIDENT FUND
- `fd_closure` — FD CLOSURE, PREMATURE CLOSURE
- `salary_advance_bnpl` — LAZYPAY, SIMPL, KREDITBEE, MONEYVIEW
- `sip_investment` — SIP, MUTUAL FUND (min 2 months)
- `insurance_premium` — LIC, HDFC LIFE, BAJAJ ALLIANZ (min 2 months)
- `govt_benefit` — PM KISAN, MNREGA, DBT

**Layer 2 — Custom Multi-Step Detectors:**
- `_detect_self_transfer_post_salary()` — salary received → ≥40% self-transfer within 3 days (conduit pattern)
- `_detect_post_salary_routing()` — salary received → 2+ distinct recipients within 48h (distribution hub pattern)
- `_detect_loan_redistribution()` — large lender credit → multi-outflow within 48h
- `_detect_round_trips()` — same name, similar amount, debit then credit within 7 days

**Output:** Each event dict contains `type, date, month_label, amount, significance (high/medium/positive), description`. Sorted by significance then date.

#### `account_quality.py` — Account Classification

Deterministic scoring of the account's functional role:
- **Primary** — salary retained, positive net cashflow, spending distributed over time
- **Conduit** — salary in, large self-transfer out within 1–3 days
- **Distribution Hub** — salary in, multiple recipients within 72h, consistent across months
- **Secondary** — no salary, irregular credits, debit-heavy

#### `category_resolver.py` — Category Presence Lookup

Resolves ambiguous category names (fuzzy matching via `categories.yaml` aliases), then searches transactions using:
1. `category_of_txn` field exact match
2. Narration keyword scan
3. Direction filter (CR-only for salary, DR-only for spending)

Returns `CategoryPresenceResult` with up to 10 supporting transactions for audit.

---

### 3.6 Bureau Extraction Module (`pipeline/extractors/`)

**Purpose:** Transform raw `dpd_data.csv` rows into typed feature vectors for analysis.

**`bureau_feature_extractor.py`** — Per-loan-type computation:
1. Load all rows for customer CRN
2. Normalise 80+ raw loan type strings to `LoanType` enum (via `LOAN_TYPE_NORMALIZATION_MAP`)
3. Group rows by `LoanType`
4. For each group, compute `BureauLoanFeatureVector`:
   - Counts, amounts, vintage, DPD, utilisation
   - Forced event flags (WRF, SET, SMA, LSS, WOF)
   - On-us vs off-us split

**`bureau_feature_aggregator.py`** — Portfolio-level:
- Sum and average across all loan types
- Compute: unsecured %, outstanding %, CC utilisation, new PL count in 6M
- Build `BureauExecutiveSummaryInputs` — the structured input to the LLM prompt

**`tradeline_feature_extractor.py`** — Loads pre-computed features from `tl_features.csv` (DPD flags, interpurchase times, missed payment %). Returns `None` gracefully if file is missing.

---

### 3.7 Rendering Module (`pipeline/renderers/`)

**Purpose:** Convert typed report schemas to PDF and HTML output. No data manipulation. No LLM calls.

Three renderers, all using `fpdf2` (PDF) and `Jinja2` (HTML):

| Renderer | Input | Output |
|---|---|---|
| `pdf_renderer.py` | `CustomerReport` | Banking PDF + HTML |
| `bureau_pdf_renderer.py` | `BureauReport` | Bureau PDF + HTML |
| `combined_report_renderer.py` | `CustomerReport + BureauReport` | Merged PDF + HTML |

**`ReportPDF` (base class)** extends `FPDF` with helper methods:
- `section_title()` — grey filled header cell
- `section_text()` — `multi_cell` with Unicode sanitisation
- `key_value()` — bold key + value layout
- `table_header()` / `table_row()` — bordered table cells

**`_sanitize_text()`** — replaces `₹`, `—`, `"`, `…` etc. with ASCII equivalents before writing to PDF (fpdf2 limitation with standard fonts).

---

## 4. Detailed Functionality Breakdown

### Functionality 1 — Natural Language Query Answering

**Description:** User asks a financial question in plain English; system returns a sourced, narrated answer.

**Files:** `orchestrator.py`, `intent_parser.py`, `planner.py`, `executor.py`, `explainer.py`, `analytics.py`

**Flow:**
```
User: "What did customer 5004898 spend on betting in the last 3 months?"
    ↓
IntentParser → intent=CATEGORY_PRESENCE_LOOKUP, customer_id=5004898, category="betting"
    ↓
QueryPlanner → validates CID exists, maps to category_presence_lookup tool
    ↓
ToolExecutor → category_presence_lookup(5004898, "betting") → {present: true, total: 45000, txn_count: 12, ...}
    ↓
ResponseExplainer → "Customer 5004898 has ₹45,000 in betting transactions over 12 payments.
                      Top transactions include: [list]. This is a notable risk flag for lending."
```

---

### Functionality 2 — Customer Banking Report Generation

**Description:** Generates a multi-section PDF report with LLM-written executive summary.

**Files:** `report_orchestrator.py`, `customer_report_builder.py`, `report_summary_chain.py`, `event_detector.py`, `account_quality.py`, `pdf_renderer.py`

**Flow:**
```
generate_customer_report_pdf(customer_id=5004898, months=6)
    ↓
Validate customer exists in rgs.csv
    ↓
build_customer_report() → CustomerReport (12 sections populated)
    ↓
detect_events() → [self_transfer_post_salary HIGH, sip_investment POSITIVE]
compute_account_quality() → {classification: "CONDUIT", ...}
    ↓
model_copy(update={events: ..., account_quality: ...})
    ↓
generate_customer_persona() → "This customer appears to be a salaried professional..."
generate_customer_review() → "Financial Overview:\n...\nTransaction Events:\n..."
    ↓
render_report_pdf(report) → reports/customer_5004898_report.pdf
```

---

### Functionality 3 — Bureau / Credit Report Generation

**Description:** Processes DPD tradeline data into a structured risk report with per-loan-type breakdown.

**Files:** `bureau_report_builder.py`, `bureau_feature_extractor.py`, `bureau_feature_aggregator.py`, `tradeline_feature_extractor.py`, `key_findings.py`, `report_summary_chain.py`, `bureau_pdf_renderer.py`

**Flow:**
```
generate_bureau_report_pdf(customer_id=5004898)
    ↓
extract_bureau_features() → {PL: FeatureVector, CC: FeatureVector, HL: FeatureVector}
    ↓
aggregate_bureau_features() → BureauExecutiveSummaryInputs
extract_tradeline_features() → TradelineFeatures (or None)
    ↓
generate_key_findings() → [{finding: "CC utilization 90%", tag: "[HIGH RISK]"}, ...]
    ↓
_compute_interaction_signals() → ["DUAL LEVERAGE — CC 90% + PL 75%...", ...]
    ↓
generate_bureau_review() → "Portfolio Overview:\n...\nBehavioral Insights:\n..."
    ↓
render_bureau_report_pdf(report) → reports/bureau_5004898_report.pdf
```

---

### Functionality 4 — Combined Report Generation

**Description:** Merges banking and bureau reports into a single PDF with a synthesised executive summary.

**Files:** `combined_report.py`, `combined_report_renderer.py`, `report_summary_chain.py`

**Flow:**
```
generate_combined_report_pdf(customer_id)
    ↓
generate_customer_report_pdf() → CustomerReport (with customer_review cached)
generate_bureau_report_pdf() → BureauReport (with narrative cached)
    ↓
generate_combined_executive_summary(banking_summary, bureau_summary)
    ↓
_build_combined_pdf(customer_report, bureau_report, combined_summary)
    ↓
reports/combined_5004898_report.pdf
```

**Content:** Banking section → Bureau section → Combined Executive Summary. Banking "Executive Summary" section is `customer_report.customer_review` — same cached field as the standalone banking report. Content is guaranteed identical.

---

### Functionality 5 — Semantic Event Detection

**Description:** Identifies meaningful financial behaviour events from raw transaction narrations.

**Files:** `tools/event_detector.py`

**Two detection layers:**

**Layer 1 — Keyword rules:** Declarative config table. Each entry specifies direction, keyword list, significance, and optional `min_months` for recurring patterns.

**Layer 2 — Multi-step detectors:** Stateful logic for complex patterns:
- Self-transfer post-salary: window filter (salary date to +3 days, ≥40% of salary, `_is_self()` narration check)
- Post-salary routing: 2+ distinct non-self recipients within 48h, >8% salary each
- Loan redistribution: large lender credit → multiple outflows within 48h
- Round trips: same-name debit matched to near-identical credit within ±7 days

**Output format:**
```python
{
    "type": "self_transfer_post_salary",
    "date": "2025-06-15",
    "month_label": "Jun 2025",
    "amount": 72000.0,
    "significance": "high",
    "description": "Jun 2025: Self-transfer after salary — ₹72,000 (100% of ₹72,000 salary) transferred to own account 1 day(s) after credit (...)"
}
```

---

### Functionality 6 — Transaction Insight Pattern Extraction

**Description:** Identifies behavioural patterns (subscription-heavy, salary-consistent, etc.) using an LLM with results cached per customer.

**Files:** `pipeline/insights/transaction_flow.py`, `insight_store.py`

**Patterns detected:** subscription-heavy, salary-consistent, rent-recurring, discretionary-heavy, cash-heavy, utility-regular, emi-committed

**Caching:** Results cached in-memory by `(customer_id, scope)`. Subsequent queries for the same customer reuse the cached pattern analysis without an LLM call.

---

### Functionality 7 — Streaming Web Interface

**Description:** Kotak-branded Streamlit application with real-time pipeline progress and streaming LLM output.

**Files:** `app.py`

**Key UI elements:**
- Pipeline stage indicator: `Parsing → Planning → Executing → Analysing → Generating`
- Real-time streaming output (0.025s per chunk — ~40 chars/sec typing effect)
- PDF download buttons for banking, bureau, and combined reports
- Session-level chat history
- Customer ID masking in display

---

### Functionality 8 — Audit Logging

**Description:** Every pipeline execution logged to daily JSONL files for compliance and debugging.

**Files:** `pipeline/core/audit.py`

**Log entry fields:** `timestamp, query, parsed_intent, tools_executed, response, latency_ms, success, error`

**Format:** `logs/audit_YYYYMMDD.jsonl` — one JSON object per line, trivially parseable with pandas or any log aggregator.

---

## 5. Data Flow Explanation

### 5.1 Query Pipeline Data Flow

```
1. User types query in Streamlit / CLI
        │
        ▼
2. TransactionPipeline.query_stream(query)
        │
        ▼
3. IntentParser.parse(query)
   ┌── LLM (mistral) + PARSER_PROMPT
   └── Output: ParsedIntent {intent=..., customer_id=..., category=..., confidence=...}
        │
        ▼
4. QueryPlanner.create_plan(intent)
   ┌── Validate required fields
   ├── Validate customer_id in dataset
   ├── Validate category (fuzzy match)
   └── Output: [{"tool": "...", "args": {...}}, ...]
        │
        ▼
5. ToolExecutor.execute(plan)
   ┌── Call each tool function
   ├── Wrap results in ToolResult
   └── Output: [ToolResult(success=True, result={...}), ...]
        │
        ▼
6. get_transaction_insights_if_needed(customer_id)
   ┌── Check insight cache
   ├── If miss: LLM pattern extraction
   └── Output: TransactionInsights {patterns: [...]}
        │
        ▼
7. ResponseExplainer.stream_explain(intent, results, insights)
   ┌── Format tool results as prompt context
   ├── Append transaction patterns
   ├── LLM (llama3.2) generates streaming response
   ├── strip_think() removes <think> blocks
   └── Yield string chunks
        │
        ▼
8. Chunks displayed to user in real-time
        │
        ▼
9. AuditLogger.log(entry) → logs/audit_YYYYMMDD.jsonl
```

### 5.2 Report Generation Data Flow

```
1. generate_customer_report_pdf(customer_id)
        │
        ▼
2. Validate: customer_id in get_transactions_df()["cust_id"]
        │
        ▼
3. build_customer_report(customer_id, months)
   For each section:
   ├── Load cached DataFrame (get_transactions_df())
   ├── Filter: df[df["cust_id"] == customer_id]
   ├── Apply section logic (group/aggregate/filter)
   └── Populate CustomerReport field
        │
        ▼
4. compute_account_quality(customer_id, report)
   → {classification: "CONDUIT", observations: [...]}
        │
        ▼
5. detect_events(customer_id)
   → [{type: "self_transfer_post_salary", ...}, ...]
        │
        ▼
6. base_report.model_copy(update={account_quality: ..., events: ...})
        │
        ▼
7. generate_customer_persona(report)  [LLM — deepseek-r1:14b]
   → "This customer is a salaried professional..."
        │
        ▼
8. generate_customer_review(report)   [LLM — deepseek-r1:14b]
   → "Financial Overview:\n...\nTransaction Events:\n..."
        │
        ▼
9. report.model_copy(update={customer_persona: ..., customer_review: ...})
        │
        ▼
10. render_report_pdf(report, output_path)
    ├── _build_pdf(report) → FPDF object
    ├── pdf.output(path) → .pdf file
    ├── jinja2 render template → .html file
    └── Return (pdf_path, html_path)
```

### 5.3 Key Data Transformations

| Stage | Input | Transformation | Output |
|---|---|---|---|
| CSV load | Raw TSV bytes | `pd.read_csv(sep='\t', index_col=False)` | DataFrame |
| Intent parsing | Raw string | LLM JSON extraction + regex fallback | ParsedIntent |
| Category resolution | Alias string | Fuzzy match → YAML config | CategoryConfig |
| Bureau normalisation | 80+ raw strings | `LOAN_TYPE_NORMALIZATION_MAP` lookup | LoanType enum |
| Feature computation | Raw DPD rows | Groupby + aggregation | BureauLoanFeatureVector |
| Event detection | Transaction rows | Pattern matching + window filters | List[Dict] |
| LLM summary | Structured prompt | DeepSeek-R1 + think stripping | Narrated paragraph |
| PDF rendering | CustomerReport | fpdf2 cell rendering + sanitisation | .pdf file |

---

## 6. Key Algorithms and Logic

### 6.1 Intent Parsing with Fallback

**Primary:** LLM with constrained JSON format. Covers all 44 intents with context-aware field extraction (e.g., extracting "last 3 months" → `start_date`, `end_date`).

**Fallback:** Priority-ordered regex patterns. Category presence patterns checked first (highest specificity), general spending patterns last. `difflib.get_close_matches()` for category fuzzy matching.

**Why both:** LLMs can hallucinate or return invalid JSON under load or with ambiguous queries. The regex fallback ensures 100% parse success rate, trading accuracy for reliability.

### 6.2 Confidence Scoring

Dynamic confidence score assigned to every `ParsedIntent`:

```python
score = 0.5  # base
if valid_customer_id:  score += 0.2
if valid_category:     score += 0.1
if has_dates:          score += 0.1
if known_intent:       score += 0.1
if intent == UNKNOWN:  score -= 0.3
return min(score, 1.0)
```

Confidence is logged in the audit trail. Future enhancement: route low-confidence intents to a clarification flow.

### 6.3 Salary Detection

The system uses a multi-source salary algorithm:

1. **Primary:** `rg_sal_strings.csv` — output of a proprietary salary identification algorithm that analyses transaction patterns to identify consistent regular credits as salary
2. **Fallback:** Narration keyword matching (SALARY, NEFT/SALARY, etc.) + amount regularity check

Monthly salary transactions are extracted for use in event detection (post-salary routing, self-transfer).

### 6.4 Post-Salary Event Detection Windows

**Self-transfer post-salary:**
- Window: `sal_date` to `sal_date + 3 days`
- Amount threshold: ≥ 40% of salary
- Self-identification: `_SELF_KEYWORDS` in narration OR customer name prefix match
- Deduplication: one event per salary month (`flagged_months` set)

**Post-salary routing:**
- Window: 48 hours
- Per-recipient threshold: ≥ 8% of salary (filter micro-transactions)
- Distinct non-self recipients required: ≥ 2 (OR ≥ 1 non-self + >50% of salary)
- Result: identifies distribution hub behaviour

### 6.5 Bureau Feature Aggregation

Cross-loan-type aggregation logic for the executive summary:

- **Unsecured outstanding** — sum of PL + CC + BL outstanding
- **New PLs in 6M** — count PL trades with `latest_opened` within 6 months of report date
- **Missed payment %** — `months_with_dpd_0plus / total_months_tracked`
- **Good closure %** — `PL closed with no DPD / total PL closed`
- **CC utilisation** — `CC outstanding / CC sanctioned`

### 6.6 Interaction Signal Computation

`_compute_interaction_signals()` in `report_summary_chain.py` evaluates feature combinations to produce pre-interpreted signals. Key patterns:

| Combination | Signal |
|---|---|
| Enquiries > threshold AND new PLs ≥ 2 | CREDIT HUNGRY + LOAN STACKING |
| IPT < concern AND new PLs ≥ 2 | RAPID PL STACKING |
| All DPD = 0 AND missed = 0 AND 0+% = 0 | CLEAN REPAYMENT PROFILE |
| Missed = 0 AND any DPD > 0 | PAYMENT TIMING NUANCE (not clean) |
| CC util > composite AND PL bal > composite | ELEVATED LEVERAGE |
| Enquiries high AND trade ratio low | LOW CONVERSION (probable rejections) |

These signals are injected into the bureau prompt as `COMPOSITE RISK SIGNALS` — the LLM narrates pre-written interpretations rather than deriving them from raw numbers.

### 6.7 Think Block Stripping (DeepSeek-R1)

`strip_think(text, label)`:
- Regex search for `<think>.*?</think>` with `DOTALL`
- Extracted content logged at DEBUG with visual separator
- `re.sub()` removes the block entirely
- Returns clean answer text

`stream_strip_think(chunks, label)` — streaming variant:
- Buffers until `</think>` found (or 200 char threshold for no-think models)
- Logs think content once complete
- Yields remainder and all subsequent chunks transparently
- Zero impact on non-reasoning models

---

## 7. Design Principles Used

### 7.1 Separation of Concerns

Strictly enforced across all layers:

- **Config** — never contains business logic
- **Schemas** — never contain computation
- **Tools** — never contain rendering or LLM calls
- **Renderers** — never contain data manipulation or LLM calls
- **Prompts** — all in `config/prompts.py`, never inline in code
- **Thresholds** — all in `config/thresholds.py`, never magic numbers in logic

### 7.2 Fail-Soft Architecture

Every LLM call is wrapped in try/except with a graceful fallback:

```python
try:
    events = detect_events(customer_id) or None
except Exception as exc:
    logger.warning("detect_events failed: %s", exc)
    events = None
```

Reports are generated with whatever sections succeed. A single LLM timeout does not fail the entire report.

### 7.3 Deterministic Core, LLM Periphery

The most important principle in the architecture:

- **Deterministic:** Data loading, feature extraction, threshold annotation, interaction signal computation, category matching, event detection logic, PDF rendering
- **LLM:** Intent parsing, query answering, summary narration, persona generation

LLMs are used only where deterministic logic genuinely cannot do the job (natural language understanding, professional prose generation). Every other step is pure Python.

### 7.4 Single Source of Truth

- One file per concern: `thresholds.py`, `prompts.py`, `settings.py`
- No threshold or prompt appears in more than one place
- Changing a model name: one line in `settings.py`
- Changing a risk threshold: one constant in `thresholds.py`

### 7.5 Schema-First Design

Every module interface is a typed schema. No `Dict[str, Any]` crosses module boundaries (except tool results which must remain flexible). This provides:
- IDE autocomplete across the codebase
- Runtime validation via Pydantic
- Self-documenting interfaces
- Easy serialisation for caching and audit

### 7.6 Immutable Report Objects

`CustomerReport` uses Pydantic's `model_copy(update={...})` pattern:

```python
report = base_report.model_copy(update={
    "account_quality": aq,
    "events": events,
})
```

The base report is never mutated. Each enrichment step produces a new object. This prevents subtle bugs from shared state mutation across pipeline phases.

### 7.7 DRY Configuration

Categories, intent routing, and section tools are all data-driven (YAML, dicts) rather than code-driven. Adding a new spending category requires adding one YAML entry, not modifying any Python code.

---

## 8. Change-Based Scenarios

### Scenario 1 — Adding a New Analytics Tool (e.g., "average transaction size")

**Files to change:**
1. `tools/analytics.py` — add `get_avg_transaction_size(customer_id)` function
2. `config/intents.py` — add new `IntentType.AVG_TRANSACTION_SIZE`, add to `INTENT_TOOL_MAP`
3. `pipeline/core/executor.py` — add `"avg_transaction_size": analytics.get_avg_transaction_size` to tool registry
4. `config/prompts.py` — add intent to `PARSER_PROMPT` list of valid intents

**Files NOT changed:** schemas (ToolResult handles any dict), planner, orchestrator, renderers, explainer.

**Estimated effort:** ~30 minutes.

---

### Scenario 2 — Adding a New Report Section (e.g., "Insurance Portfolio")

**Files to change:**
1. `schemas/customer_report.py` — add `insurance: Optional[InsuranceBlock]` field
2. `tools/event_detector.py` — refine existing `insurance_premium` keyword rule with more data
3. `pipeline/reports/customer_report_builder.py` — add builder logic for `insurance` section
4. `pipeline/reports/report_summary_chain.py` — add insurance data to `_build_data_summary()`
5. `pipeline/renderers/pdf_renderer.py` — add rendering block for insurance section
6. `templates/customer_report.html` — add Jinja2 block for insurance section

**Files NOT changed:** orchestrator, intent parser, planner, executor, bureau modules.

**Estimated effort:** ~2–3 hours.

---

### Scenario 3 — Swapping the LLM Model

**Files to change:**
1. `config/settings.py` — change `SUMMARY_MODEL`, `EXPLAINER_MODEL`, or `PARSER_MODEL`

That is all. The `strip_think()` utility is a no-op for models without `<think>` tags. LangChain's `ChatOllama` accepts any Ollama model name.

**Estimated effort:** 1 line.

---

### Scenario 4 — Adding a New Event Type (e.g., "NACH bounce detection")

**Option A — Keyword rule:**
```python
{
    "type": "nach_bounce",
    "direction": "D",
    "keywords": ["MANDATE RETURN", "NACH RETURN", "ECS RETURN", "CHEQUE BOUNCE", "DISHONOUR"],
    "significance": "high",
    "label": "NACH/Cheque bounce",
},
```
Add this dict to `KEYWORD_RULES` in `event_detector.py`. No other changes needed.

**Option B — Custom detector:**
Write a `_detect_nach_bounces(df)` function and call it in `detect_events()`. Suitable for multi-step logic.

**Files NOT changed:** schemas (events is `List[Dict]`), builders, renderers, prompts (events block is dynamically formatted).

**Estimated effort:** 10–30 minutes.

---

### Scenario 5 — Scaling to Multiple Customers Concurrently

**Current limitation:** Single-process Python, CSV-based data loading, in-memory caching.

**Changes needed:**
1. Replace CSV with a database (PostgreSQL or BigQuery) — change `data/loader.py` only
2. Add async execution to `executor.py` — tools are pure functions, trivially made async
3. Replace module-level report cache with Redis — change `report_orchestrator.py` cache calls
4. Deploy multiple Streamlit workers behind a load balancer
5. Use SageMaker or dedicated GPU server for Ollama instead of local

**Files NOT changed:** All business logic, schemas, prompts, renderers remain identical.

---

### Scenario 6 — Adding a New Risk Threshold

**Files to change:**
1. `config/thresholds.py` — add constant (e.g., `NACH_BOUNCE_HIGH_RISK = 2`)
2. `pipeline/reports/report_summary_chain.py` — reference constant in signal computation
3. `pipeline/reports/key_findings.py` — reference constant in findings generation

**Files NOT changed:** Anything else.

---

## 9. Extensibility and Scalability

### Adding New Modules

The architecture defines clear extension points:

| Extension Point | How to Add |
|---|---|
| New analytics tool | Add to `tools/analytics.py` + register in executor + add IntentType |
| New event type | Add to `KEYWORD_RULES` list OR write `_detect_*()` function |
| New report section | Add schema field + builder logic + renderer block |
| New intent | Add to `IntentType` enum + `INTENT_TOOL_MAP` + `PARSER_PROMPT` |
| New LLM model | Change `settings.py` |
| New category | Add entry to `categories.yaml` |
| New risk threshold | Add to `thresholds.py` |
| New interaction signal | Add rule to `_compute_interaction_signals()` |

### Scalability

**Horizontal scaling bottleneck:** Single-process, in-memory CSV cache. Removing this requires:
- Replace `data/loader.py` CSV loading with database queries
- Replace module-level cache dict with Redis

**LLM throughput bottleneck:** Sequential LLM calls for persona + review + bureau narrative (3 calls per combined report). Can be parallelised with `asyncio.gather()` since they are independent — no code changes needed outside `report_orchestrator.py`.

**Data volume:** Pandas in-memory processing works for ~100k rows. For millions of transactions, replace with DuckDB or BigQuery connector in `loader.py`.

### Current Bottlenecks

1. **LLM latency:** 3–8 seconds per summary on local hardware. Mitigated by async execution and caching.
2. **Report cache scope:** In-memory, process-scoped. Lost on restart. Replace with Redis for persistence.
3. **CSV loading:** Full dataset loaded on first call. Acceptable for dev; use database in production.
4. **Single Ollama instance:** All models share one Ollama process. Concurrent report generation queues LLM calls.

---

## 10. Deployment Architecture

### Current (Development)

```
Developer Machine
├── Python 3.11+
├── Ollama (localhost:11434)
│   ├── mistral (intent parsing)
│   ├── llama3.2 (query explanation)
│   └── deepseek-r1:14b (report summaries)
├── Streamlit (localhost:8501)
└── Data files (CSV, local filesystem)
```

**Startup:**
```bash
ollama serve                # Start Ollama daemon
ollama pull mistral         # Pull models (one-time)
ollama pull deepseek-r1:14b
streamlit run app.py        # Launch UI
```

### Production (Recommended)

```
┌─────────────────────────────────────────────────────────────────────┐
│  PRESENTATION TIER                                                  │
│  Nginx → Streamlit (multi-worker) or FastAPI REST API               │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────────┐
│  APPLICATION TIER                                                   │
│  Python workers (3–8 processes)                                     │
│  Redis (report cache + insight cache)                               │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │
              ┌───────────────────────┴────────────────────┐
              ▼                                            ▼
┌─────────────────────────┐               ┌───────────────────────────┐
│  LLM TIER               │               │  DATA TIER                │
│  Ollama server (GPU)    │               │  PostgreSQL / BigQuery    │
│  ml.g5.12xlarge         │               │  (replace CSV files)      │
│  or A6000 workstation   │               │                           │
└─────────────────────────┘               └───────────────────────────┘
```

### Dependencies

```
langchain-ollama
langchain-core
pandas
pydantic>=2.0
streamlit
fpdf2
jinja2
pyyaml
Pillow
```

Install: `pip install -r requirements.txt`

---

## 11. Complete Execution Walkthrough

**Scenario:** A loan officer opens the Streamlit app and asks: *"Generate a combined report for customer 5004898"*

```
Step 1 — UI
  User types query in Streamlit chat input.
  app.py: process_query("Generate combined report for customer 5004898")
  Stage indicator updates: [Parsing...]

Step 2 — Intent Parsing
  IntentParser.parse("Generate combined report for customer 5004898")
  LLM (mistral) extracts: {intent: COMBINED_REPORT, customer_id: 5004898}
  Confidence: 0.9 (valid CID + known intent)
  Stage indicator: [Planning...]

Step 3 — Query Planning
  QueryPlanner.create_plan(intent)
  Validates 5004898 in rgs.csv AND dpd_data.csv CRNs
  Plan: [{"tool": "generate_combined_report", "args": {"customer_id": 5004898}}]
  Stage indicator: [Executing...]

Step 4 — Tool Execution
  ToolExecutor calls generate_combined_report_pdf(5004898)

  4a. generate_customer_report_pdf(5004898):
      → build_customer_report() — 12 sections
      → detect_events() → [self_transfer_post_salary HIGH]
      → compute_account_quality() → {classification: CONDUIT}
      → generate_customer_review() [DeepSeek-R1, ~4s]
        - think block: logged at DEBUG
        - answer: "Financial Overview:\n...\nTransaction Events:\n..."
      → render_report_pdf() → reports/customer_5004898.pdf

  4b. generate_bureau_report_pdf(5004898):
      → extract_bureau_features() — PL, CC vectors
      → aggregate_bureau_features() → BureauExecutiveSummaryInputs
      → _compute_interaction_signals() → ["ELEVATED LEVERAGE..."]
      → generate_bureau_review() [DeepSeek-R1, ~4s]
        - think block: logged at DEBUG
        - answer: "Portfolio Overview:\n...\nBehavioral Insights:\n..."
      → render_bureau_report_pdf() → reports/bureau_5004898.pdf

  4c. generate_combined_executive_summary(banking, bureau) [DeepSeek-R1, ~3s]
      → synthesised 6-8 line summary

  4d. render_combined_report_pdf() → reports/combined_5004898.pdf

  Stage indicator: [Analysing...]

Step 5 — Insight Extraction
  get_transaction_insights_if_needed(5004898)
  Check cache: miss → LLM pattern extraction (llama3.2)
  Result: {patterns: ["salary-consistent", "emi-committed"]}
  Store in cache.
  Stage indicator: [Generating...]

Step 6 — Response Generation (Streaming)
  ResponseExplainer.stream_explain(intent, results, insights)
  EXPLAINER_PROMPT + formatted results + pattern context
  LLM (llama3.2) streams: "I've generated a combined report for customer ###4898..."
  Each chunk yielded → displayed in real-time in Streamlit

  strip_think() applied — any <think> content logged, not shown.

Step 7 — Audit Logging
  AuditLogger.log({
    timestamp: "2026-03-04T14:23:01",
    query: "Generate combined report for customer 5004898",
    intent: "combined_report",
    tools: ["generate_combined_report"],
    latency_ms: 12400,
    success: true
  })
  Written to logs/audit_20260304.jsonl

Step 8 — UI Update
  Streamlit shows:
  - Streaming response text
  - PDF download buttons: [Banking Report] [Bureau Report] [Combined Report]
  - Stage indicator: [Complete]
```

**Total time:** ~12–15 seconds (dominated by 3 sequential LLM summary calls, ~4s each).

---

## 12. Folder Structure Explanation

```
langchain_agentic_v7_hs/
│
├── main.py                    Entry point — CLI demos and interactive mode
├── app.py                     Entry point — Streamlit web UI (Kotak-branded)
│
├── config/                    CONFIGURATION (never contains business logic)
│   ├── settings.py            Model names, file paths, LLM parameters, feature flags
│   ├── prompts.py             All 8 LLM prompt templates
│   ├── thresholds.py          All risk threshold constants
│   ├── intents.py             Intent → tool mapping for all 44 intents
│   ├── categories.yaml        Category definitions (keywords, aliases, direction)
│   ├── category_loader.py     YAML loader with @lru_cache + fuzzy alias resolution
│   └── section_tools.py       Report section → builder function mapping
│
├── schemas/                   DATA CONTRACTS (Pydantic + dataclasses)
│   ├── intent.py              ParsedIntent, IntentType (44 values)
│   ├── response.py            PipelineResponse, ToolResult, AuditLog
│   ├── customer_report.py     CustomerReport + all sub-block schemas
│   ├── bureau_report.py       BureauReport + executive summary inputs
│   ├── transaction_insights.py TransactionInsights, TransactionPattern
│   ├── loan_type.py           LoanType enum + 80-entry normalisation map
│   ├── category_presence.py   CategoryPresenceResult, SupportingTransaction
│   └── transaction_summary.py Transaction summary helpers
│
├── pipeline/                  CORE PIPELINE LOGIC
│   ├── core/                  Query answering pipeline (5 phases)
│   │   ├── orchestrator.py    TransactionPipeline — main coordinator
│   │   ├── intent_parser.py   IntentParser — LLM + regex fallback
│   │   ├── planner.py         QueryPlanner — deterministic validation + plan
│   │   ├── executor.py        ToolExecutor — tool dispatch + fail-soft
│   │   ├── explainer.py       ResponseExplainer — streaming narration
│   │   └── audit.py           AuditLogger — JSONL audit trail
│   │
│   ├── reports/               Report generation pipeline
│   │   ├── report_orchestrator.py    Main entry: generate_customer_report_pdf()
│   │   ├── customer_report_builder.py Deterministic 12-section data collection
│   │   ├── bureau_report_builder.py  Bureau report construction
│   │   ├── report_planner.py         LLM-based section planning (optional)
│   │   ├── report_summary_chain.py   LLM summary generation (4 functions)
│   │   └── key_findings.py           Deterministic risk annotation
│   │
│   ├── extractors/            Bureau data processing
│   │   ├── bureau_feature_extractor.py    Per-loan-type feature vectors
│   │   ├── bureau_feature_aggregator.py   Portfolio-level aggregation
│   │   └── tradeline_feature_extractor.py Pre-computed feature loading
│   │
│   ├── renderers/             Output rendering (NO data logic)
│   │   ├── pdf_renderer.py           Customer report PDF + HTML
│   │   ├── bureau_pdf_renderer.py    Bureau report PDF + HTML
│   │   └── combined_report_renderer.py Combined report PDF + HTML
│   │
│   └── insights/              Transaction pattern extraction
│       ├── transaction_flow.py  LLM pattern detection + caching
│       └── insight_store.py     In-memory pattern cache
│
├── tools/                     ANALYTICS TOOLS (pure functions → Dict)
│   ├── analytics.py           15 core analytics functions
│   ├── bureau.py              Bureau report generator tool
│   ├── bureau_chat.py         4 lightweight bureau query tools
│   ├── combined_report.py     Combined report generator tool
│   ├── category_resolver.py   Category presence lookup
│   ├── account_quality.py     Account classification (conduit/primary/secondary)
│   ├── event_detector.py      Two-layer semantic event detection
│   ├── scorecard.py           Scorecard generation
│   └── transaction_fetcher.py Transaction retrieval
│
├── features/                  FEATURE DEFINITIONS (dataclasses)
│   ├── bureau_features.py     BureauLoanFeatureVector — per-loan-type schema
│   └── tradeline_features.py  TradelineFeatures — portfolio-level schema
│
├── data/                      DATA ACCESS LAYER
│   ├── loader.py              Cached CSV loading (rgs.csv, dpd_data.csv, salary CSVs)
│   └── rgs.csv                Banking transaction data (primary dataset)
│
├── utils/                     SHARED UTILITIES
│   ├── helpers.py             format_inr(), mask_customer_id(), print_header()
│   ├── llm_utils.py           strip_think(), stream_strip_think()
│   ├── narration_utils.py     Transaction narration parsing
│   └── transaction_filter.py  Transaction filtering + LLM formatting
│
├── templates/                 HTML TEMPLATES (Jinja2)
│   ├── customer_report.html   Banking report HTML template
│   ├── bureau_report.html     Bureau report HTML template
│   └── combined_report.html   Combined report HTML template
│
├── docs/                      DOCUMENTATION
│   ├── system_architecture.md This document
│   └── feature_ideas.md       Backlog: future features, events, reasoning improvements
│
├── logs/                      AUDIT LOGS (auto-created)
│   └── audit_YYYYMMDD.jsonl   Daily JSONL audit trail
│
└── reports/                   GENERATED REPORTS (auto-created)
    └── *.pdf / *.html         Output files
```

---

## 13. Key Technical Decisions

### Decision 1 — Local LLM via Ollama (not cloud API)

**Why:** Banking transaction data and customer financial information is highly sensitive. Running models locally via Ollama ensures no customer data leaves the organisation's infrastructure. Also eliminates per-token API costs and network latency.

**Trade-off:** Lower model quality than GPT-4, higher hardware requirements. Mitigated by choosing reasoning models (DeepSeek-R1) that approach GPT-4 quality on structured tasks.

### Decision 2 — Three Separate LLM Models

**Parser (mistral):** Fast, JSON-reliable, low latency. Intent parsing runs on every query — speed matters more than reasoning depth.

**Explainer (llama3.2):** Fast streaming. Query answering is user-facing real-time — 3B model streams quickly.

**Summary (deepseek-r1:14b):** Deep reasoning. Report generation is async and quality-critical — the reasoning model produces more accurate cross-signal interpretations.

### Decision 3 — Deterministic Core, LLM Periphery

Every piece of logic that can be expressed as Python code is expressed as Python code. LLMs are used only for natural language understanding and prose generation. This makes the system:
- Auditable (deterministic outputs from rules)
- Reproducible (same data → same analysis)
- Debuggable (failures are in Python, not LLM black boxes)
- Cheaper (fewer LLM calls)

### Decision 4 — Pydantic v2 for Schemas

Enables runtime validation, automatic serialisation, and IDE type inference. The `model_copy(update={...})` pattern avoids mutating report objects mid-pipeline, preventing a class of subtle bugs where sections from one report bleed into another.

### Decision 5 — YAML-Driven Category Configuration

Categories (salary, betting, rent, EMI) are defined in `categories.yaml`, not in code. This allows a non-engineer (product manager, analyst) to add or modify category detection without a code deployment. The `@lru_cache` on the loader means the YAML is parsed once per process.

### Decision 6 — Fail-Soft Report Generation

Any optional section (LLM summaries, tradeline features, events) is wrapped in try/except. Reports are generated with whatever data is available. This was a deliberate trade-off: a partial report delivered immediately is more valuable than a perfect report that sometimes fails entirely.

### Decision 7 — Two-Paragraph LLM Report Structure

Modelled on the bureau report structure which was validated to produce good outputs. Paragraph 1 (Financial Overview) uses the LLM for synthesis — converting structured numbers into flowing prose. Paragraph 2 (Transaction Events) forces the LLM to narrate specific detected events with mandatory inclusion of all events. This structure prevents the LLM from "forgetting" events that don't fit neatly into a paragraph.

### Decision 8 — `index_col=False` in CSV Loading

The source transaction CSV (`rgs.csv`) has trailing tab characters on every data row, producing 11 fields against a 10-column header. Without `index_col=False`, pandas silently treats column 0 as the row index, shifting all column assignments by one. This caused `tran_partclr` to receive 'NULL' strings → NaN floats → `AttributeError: 'float' has no attribute 'lower'` in keyword matching. `index_col=False` prevents the auto-index behaviour.

---

## 14. System Strengths

### Architectural Strengths

**1. Clean separation of concerns** — The distinction between deterministic Python (data, features, thresholds) and LLM (narration, parsing) means each layer can be tested and improved independently. Adding a new risk rule never requires touching the LLM prompts.

**2. Fail-soft at every layer** — The pipeline never crashes due to an LLM failure. Reports degrade gracefully — a missing persona section is logged and skipped, not raised as an exception.

**3. Model-agnostic** — The entire LLM stack is abstracted behind LangChain's `ChatOllama`. Swapping from llama3.2 to deepseek-r1 to phi4 is one constant change in `settings.py`.

**4. Audit trail** — Every query, parsed intent, tools executed, response, and latency is logged to JSONL. Compliance and debugging are built in, not bolted on.

**5. Schema-first** — No `Dict[str, Any]` leaks across module boundaries (except tool outputs, which must be flexible). All inter-module contracts are typed and validated.

### Functional Strengths

**6. Two-layer event detection** — The keyword rules + custom detector pattern means adding a new financial event pattern is a configuration change (YAML-like dict entry), not an architectural change.

**7. Dual output formats** — Every report renders to both PDF (for download/storage) and HTML (for browser viewing), from the same typed schema object.

**8. Category presence lookup** — The system can answer "does this customer have gambling transactions?" with supporting transaction evidence — not just a yes/no. This is highly valuable for underwriting decisions.

**9. Combined report coherence** — The banking "Executive Summary" in the combined report uses `customer_report.customer_review` — the exact same cached field. Content is guaranteed identical to the standalone banking report. No risk of conflicting summaries.

---

## 15. Possible Improvements

### Short-Term (Next Sprint)

**1. Richer interaction signal text** (Section 5a of feature_ideas.md)
Current signals state numbers without interpretation ("CC util 90%"). Update string templates in `_compute_interaction_signals()` to carry domain interpretation ("maxing revolving credit while carrying installment burden — dual leverage").

**2. Event implication field**
Add `implication` key to each event dict in `event_detector.py`. `format_events_for_prompt()` appends it so the LLM narrates implications without deriving them. (Section 5c of feature_ideas.md)

**3. FOIR in financial overview**
`(sum(EMI) + rent) / salary.avg_amount * 100` — computable from existing `CustomerReport` fields. Inject into `_build_data_summary()`. Most important lending metric currently missing from the report.

**4. NACH/cheque bounce detection**
Add `MANDATE RETURN`, `NACH RETURN`, `ECS RETURN`, `CHEQUE BOUNCE`, `DISHONOUR` to `KEYWORD_RULES` as HIGH significance. Zero false positive risk, extremely high signal value.

### Medium-Term

**5. Account behaviour classifier** (`classify_account_behavior()`)
Deterministic function computing `distribution_ratio`, `accumulation_score`, `recipient_diversity_post_salary`. Outputs labeled classification (PRIMARY / CONDUIT / DISTRIBUTION HUB / SECONDARY / SAVINGS) with evidence. Injected into prompt before LLM generates review. (Section 5b of feature_ideas.md)

**6. Structured reasoning trace (Path 2 from Section 6)**
Pre-compute: feature values → annotations → interaction signals → account classification → risk verdict. LLM receives a near-complete analysis and only writes sentences. This is the single highest-leverage improvement for report quality.

**7. Parallel LLM summary calls**
The three LLM calls in combined report generation (customer review, bureau review, combined summary) are independent. `asyncio.gather()` would reduce latency by ~2/3.

**8. Salary gap detection**
If salary present for 3+ months then absent for 2+ consecutive months → HIGH event. Valuable income disruption signal not currently detected.

### Long-Term

**9. Database backend**
Replace `data/loader.py` CSV loading with PostgreSQL/BigQuery. Required for multi-user production deployment. No changes needed to any other module.

**10. Fine-tuning pipeline (Path 3 from Section 6)**
Once 500+ reports are generated and expert-reviewed, fine-tune a 7B–14B model on `(structured_reasoning_trace → expert_report)` pairs. A specialised model trained on Indian banking data will outperform general models on this domain.

**11. Retrieval-Augmented Reasoning (Path 5 from Section 6)**
Store domain knowledge rules as text documents. Retrieve 5–10 most relevant rules per customer profile and inject into prompt. Allows a credit risk analyst to add interpretation rules without touching code.

**12. Redis report cache**
Replace module-level dict cache with Redis. Reports persist across process restarts. Enables multi-worker deployment without cache miss penalty.

---

*Document generated from full codebase analysis — 2026-03*
*All file references are relative to project root: `/langchain_agentic_v7_hs/`*
