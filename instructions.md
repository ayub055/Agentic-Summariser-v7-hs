# Project Architecture — Kotak Agentic Reader (v7)

This document is the **single source of truth** for the project's architecture.
It covers both the shared agentic pipeline and all report verticals.
Use this as context before making any changes.

---

## 1. Project Overview

A LangChain-based agentic system that answers natural-language financial queries.
Three report types share one pipeline:

| Vertical | Data Source | Customer ID Column | Report Type |
|---|---|---|---|
| **Banking** | `data/rgs.csv` | `cust_id` | Customer Report PDF |
| **Bureau** | `dpd_data.csv` (tab-separated) | `crn` | Bureau Tradeline Report PDF |
| **Combined** | Both sources | either | Combined Report PDF (banking + bureau) |

**Key rule:** Determinism > intelligence. All numbers are computed deterministically. LLM is used **only** for narration of pre-computed results.

---

## 2. Directory Structure

```
langchain_agentic_v7_hs/
│
├── app.py                          # Streamlit UI (shared for all verticals)
├── main.py                         # CLI entry point
├── dpd_data.csv                    # Bureau tradeline data (tab-separated)
├── tl_features.csv                 # Pre-computed tradeline features (tab-separated)
├── instructions.md                 # THIS FILE
│
├── config/
│   ├── intents.py                  # INTENT_TOOL_MAP, REQUIRED_FIELDS
│   ├── categories.yaml             # Category taxonomy for banking
│   ├── category_loader.py          # YAML loader for categories
│   ├── section_tools.py            # Report section → tool mapping
│   └── settings.py                 # Model names, thresholds, file paths
│
├── schemas/
│   ├── intent.py                   # IntentType enum + ParsedIntent model
│   ├── loan_type.py                # LoanType enum (13 types), normalization map, SECURED_LOAN_TYPES
│   ├── bureau_report.py            # BureauReport dataclass
│   ├── customer_report.py          # CustomerReport model + ReportMeta
│   ├── response.py                 # PipelineResponse, ToolResult, AuditLog
│   ├── category_presence.py        # Category presence lookup schema
│   ├── transaction_insights.py     # Transaction insight patterns
│   └── transaction_summary.py      # Transaction summary schema
│
├── features/
│   ├── bureau_features.py          # BureauLoanFeatureVector dataclass
│   └── tradeline_features.py       # TradelineFeatures dataclass (pre-computed)
│
├── data/
│   ├── loader.py                   # Banking CSV loader (get_transactions_df)
│   └── rgs.csv                     # Banking transaction data
│                                   # Columns: cust_id, dr_cr_indctor, tran_date,
│                                   #          prty_name, tran_amt_in_ac, tran_partclr,
│                                   #          sal_flag, tran_type, category_of_txn
│
├── pipeline/
│   ├── orchestrator.py             # TransactionPipeline (main entry, shared)
│   ├── intent_parser.py            # LLM + fallback intent parsing
│   ├── planner.py                  # QueryPlanner (validation + plan creation)
│   ├── executor.py                 # ToolExecutor (tool dispatch)
│   ├── explainer.py                # LLM-powered response narration
│   ├── audit.py                    # JSONL audit logging
│   │
│   ├── # --- Banking Report Path ---
│   ├── customer_report_builder.py  # Deterministic report assembly
│   ├── report_orchestrator.py      # Wires builder → LLM → PDF for banking
│   ├── report_planner.py           # Section planner for customer reports
│   ├── report_summary_chain.py     # LLM narration chains (banking + bureau)
│   ├── pdf_renderer.py             # ReportPDF base class + banking PDF/HTML render
│   │
│   ├── # --- Bureau Report Path ---
│   ├── bureau_feature_extractor.py # Raw CSV → per-loan-type feature vectors
│   ├── bureau_feature_aggregator.py# Feature vectors → executive summary inputs
│   ├── bureau_report_builder.py    # Wires extraction → aggregation → BureauReport
│   ├── tradeline_feature_extractor.py # tl_features.csv → TradelineFeatures
│   ├── bureau_pdf_renderer.py      # BureauReportPDF + PDF/HTML render
│   ├── key_findings.py             # 40+ deterministic findings engine (KeyFinding dataclass)
│   │
│   ├── # --- Combined Report Path ---
│   ├── combined_report_renderer.py # CombinedReportPDF + PDF/HTML render
│   │                               # Reuses helpers from bureau_pdf_renderer.py
│   │
│   ├── # --- Shared Utilities ---
│   ├── transaction_flow.py         # Transaction insight extraction
│   ├── insight_store.py            # Insight caching
│   └── result_merger.py            # Multi-tool result merging
│
├── tools/
│   ├── analytics.py                # Banking analytics tools (debit_total, etc.)
│   ├── spending.py                 # Spending analysis tools
│   ├── bureau.py                   # generate_bureau_report_pdf (bureau tool entry)
│   ├── bureau_chat.py              # Bureau chat/query tool
│   ├── combined_report.py          # generate_combined_report_pdf (combined tool entry)
│   ├── category_resolver.py        # Category presence lookup tool
│   ├── income.py                   # Income analysis tools
│   ├── lookup.py                   # Lookup utilities
│   ├── schemas.py                  # Tool-specific schemas
│   └── transaction_fetcher.py      # Raw transaction fetching
│
├── utils/
│   ├── helpers.py                  # mask_customer_id, format_inr, formatting
│   ├── narration_utils.py          # Narration formatting helpers
│   └── transaction_filter.py       # Transaction filtering logic
│
├── templates/
│   ├── customer_report.html        # Jinja2 template for banking PDF/HTML
│   ├── bureau_report.html          # Jinja2 template for bureau PDF/HTML
│   └── combined_report.html        # Jinja2 template for combined PDF/HTML
│
├── reports/                        # Generated PDF + HTML outputs
└── logs/                           # Audit JSONL logs
```

---

## 3. Shared Pipeline (All Verticals)

Every user query flows through the same 5-phase pipeline. **No new agents, planners, executors, or UI components are created for new verticals.**

```
User Query (text)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: INTENT PARSER  (pipeline/intent_parser.py)           │
│  ├─ LLM-based JSON extraction (primary)                       │
│  └─ Regex fallback parser (secondary)                         │
│  Output: ParsedIntent { intent, customer_id, category, ... }  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: PLANNER  (pipeline/planner.py)                       │
│  ├─ Validates customer_id against correct data source:        │
│  │   - Banking intents → valid_customers (from rgs.csv)       │
│  │   - BUREAU_REPORT   → valid_bureau_customers (from dpd)    │
│  │   - COMBINED_REPORT → validates against both sources       │
│  ├─ Normalizes categories                                     │
│  ├─ Validates date ranges                                     │
│  └─ Looks up INTENT_TOOL_MAP → builds execution plan          │
│  Output: [{ tool: "tool_name", args: {...} }, ...]            │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: EXECUTOR  (pipeline/executor.py)                     │
│  ├─ Dispatches each plan step to registered tool function      │
│  ├─ tool_map keys → Python callables                          │
│  └─ Wraps results in ToolResult { success, result, error }    │
│  Output: List[ToolResult]                                      │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: EXPLAINER  (pipeline/explainer.py)                   │
│  ├─ Formats tool results into LLM prompt                      │
│  ├─ Streams LLM narration back to UI                          │
│  └─ For reports: narrative is generated inside the tool itself │
│  Output: Streaming text response                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 5: UI  (app.py — Streamlit)                             │
│  ├─ Renders streaming text in chat bubble                     │
│  ├─ If pdf_path in result → shows download button             │
│  └─ Maintains chat history in st.session_state                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Intent System

### 4a. IntentType Enum (`schemas/intent.py`)

All supported intents. Adding a new capability = adding a new enum value here first.

| Intent | Tool(s) | Required Fields |
|---|---|---|
| `TOTAL_SPENDING` | `debit_total` | `customer_id` |
| `TOTAL_INCOME` | `get_total_income` | `customer_id` |
| `SPENDING_BY_CATEGORY` | `get_spending_by_category` | `customer_id` |
| `TOP_CATEGORIES` | `top_spending_categories` | `customer_id` |
| `SPENDING_IN_PERIOD` | `spending_in_date_range` | `customer_id`, `start_date`, `end_date` |
| `FINANCIAL_OVERVIEW` | `get_total_income`, `debit_total`, `top_spending_categories` | `customer_id` |
| `COMPARE_CATEGORIES` | `get_spending_by_category` (per category) | `customer_id`, `categories` |
| `CUSTOMER_REPORT` | `generate_customer_report` | `customer_id` |
| `LENDER_PROFILE` | `generate_lender_profile` | `customer_id` |
| `CREDIT_ANALYSIS` | `get_credit_statistics` | `customer_id` |
| `DEBIT_ANALYSIS` | `get_debit_statistics`, `top_spending_categories`, `debit_total` | `customer_id` |
| `ANOMALY_DETECTION` | `detect_anomalies` | `customer_id` |
| `BALANCE_TREND` | `get_balance_trend` | `customer_id` |
| `INCOME_STABILITY` | `get_income_stability` | `customer_id` |
| `CASH_FLOW` | `get_cash_flow` | `customer_id` |
| `CATEGORY_PRESENCE_LOOKUP` | `category_presence_lookup` | `customer_id`, `category` |
| `BUREAU_REPORT` | `generate_bureau_report` | `customer_id` |
| `COMBINED_REPORT` | `generate_combined_report` | `customer_id` |

### 4b. Intent Mapping (`config/intents.py`)

Two dicts control routing:
- `INTENT_TOOL_MAP`: IntentType → list of tool name strings
- `REQUIRED_FIELDS`: IntentType → list of required field names

### 4c. Intent Parser (`pipeline/intent_parser.py`)

Two-stage parsing:
1. **LLM parser** — sends query to Ollama with `PARSER_PROMPT`, extracts JSON
2. **Fallback parser** — regex-based keyword matching (runs if LLM fails or confidence < threshold)

Bureau keywords in fallback: `"bureau report"`, `"bureau"`, `"cibil report"`, `"cibil"`, `"tradeline report"`, `"credit bureau"` — checked **before** generic "report" keywords to avoid misclassification.

---

## 5. Bureau Report Vertical — Complete Architecture

### 5a. Data Flow

```
User: "Generate bureau report for 100384958"
    │
    ▼
Intent Parser → intent=BUREAU_REPORT, customer_id=100384958
    │
    ▼
Planner → validates CRN against dpd_data.csv (NOT rgs.csv)
    │       → plan: [{ tool: "generate_bureau_report", args: { customer_id: 100384958 } }]
    ▼
Executor → calls _generate_bureau_report_with_pdf(customer_id=100384958)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  tools/bureau.py :: generate_bureau_report_pdf(customer_id)                │
│                                                                             │
│  Step 1: BUILD (deterministic)                                              │
│  └─ bureau_report_builder.build_bureau_report(customer_id)                 │
│      ├─ bureau_feature_extractor.extract_bureau_features(customer_id)      │
│      │   ├─ Load dpd_data.csv (tab-separated, cached)                     │
│      │   ├─ Filter rows by crn == customer_id                              │
│      │   ├─ Normalize each raw loan_type → LoanType enum                  │
│      │   ├─ Group tradelines by canonical LoanType                         │
│      │   └─ Compute BureauLoanFeatureVector per group                     │
│      │       ├─ loan_count, live_count, closed_count                       │
│      │       ├─ total_sanctioned, total_outstanding, overdue               │
│      │       ├─ secured (per-tradeline check against SECURED_LOAN_TYPES)  │
│      │       ├─ max_dpd, delinquency_flag                                 │
│      │       ├─ utilization_ratio (CC only)                                │
│      │       ├─ forced_event_flags (from dpd_string)                      │
│      │       ├─ on_us_count / off_us_count (KOTAK sectors)                │
│      │       └─ avg_vintage_months, months_since_last_payment             │
│      │                                                                     │
│      ├─ bureau_feature_aggregator.aggregate_bureau_features(vectors)       │
│      │   └─ Returns BureauExecutiveSummaryInputs:                         │
│      │       total_tradelines, live, closed, exposure, outstanding,        │
│      │       unsecured_exposure (using vec.secured), delinquency, max_dpd │
│      │                                                                     │
│      ├─ key_findings.generate_key_findings(executive_inputs, vectors, tf) │
│      │   └─ 40+ deterministic findings, severity-tagged                   │
│      │                                                                     │
│      ├─ Assemble BureauReport { meta, feature_vectors, executive_inputs,  │
│      │                          key_findings }                             │
│      └─ Validate (fail-soft: live+closed==total, CC-only util, no negs)   │
│                                                                             │
│  Step 2: NARRATE (fail-soft)                                                │
│  └─ report_summary_chain.generate_bureau_review(executive_inputs)          │
│      ├─ _build_bureau_data_summary(inputs) → plain text block             │
│      ├─ BUREAU_REVIEW_PROMPT → LLM (Ollama LCEL chain)                    │
│      └─ Returns narrative string (or None on failure)                      │
│                                                                             │
│  Step 3: RENDER (fail-soft)                                                 │
│  └─ bureau_pdf_renderer.render_bureau_report_pdf(report)                   │
│      ├─ _build_bureau_pdf(report) → FPDF                                  │
│      │   ├─ Page 1: Meta + Portfolio Summary + Executive Narrative         │
│      │   ├─ Page 2: Key Findings & Inferences                             │
│      │   └─ Page 3: Product-wise Table + Behavioral Features              │
│      ├─ Save PDF to reports/bureau_{id}_report.pdf                        │
│      └─ Save HTML to reports/bureau_{id}_report.html (Jinja2 template)    │
│                                                                             │
│  Returns: (BureauReport, pdf_path)                                          │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
Executor wrapper → converts to dict { executive_inputs, feature_vectors, narrative, pdf_path }
    │
    ▼
Explainer → streams LLM narration to UI
    │
    ▼
UI → shows narrative + PDF download button
```

### 5b. Loan Type Taxonomy (`schemas/loan_type.py`)

**LoanType enum** — 13 canonical types:
`PL`, `CC`, `HL`, `AL`, `BL`, `LAP`, `LAS`, `LAD`, `GL`, `TWL`, `CD`, `CMVL`, `OTHER`

**LOAN_TYPE_NORMALIZATION_MAP** — maps 54+ raw loan type strings from `dpd_data.csv` to canonical enum.

**SECURED_LOAN_TYPES** — `Set[str]` of raw loan type names where `sec_flag=1`. Checked at raw level because some canonical types (BL, CC) have both secured and unsecured variants.

**`is_secured(raw_loan_type: str) -> bool`** — checks raw string against `SECURED_LOAN_TYPES`.

**`normalize_loan_type(raw_loan_type: str) -> LoanType`** — maps raw string via `LOAN_TYPE_NORMALIZATION_MAP`, defaults to `OTHER`.

**ON_US_SECTORS** — `{"KOTAK BANK", "KOTAK PRIME"}` for on-us/off-us classification.

### 5c. Secured Classification Flow

```
Raw loan_type string (per tradeline)
    │
    ▼
is_secured(raw_loan_type) → bool
    │  (checks against SECURED_LOAN_TYPES set of raw strings)
    ▼
BureauLoanFeatureVector.secured = any(is_secured(tl) for tl in tradelines_in_group)
    │  (True if ANY tradeline in the canonical group is secured)
    ▼
Used downstream by:
  ├─ bureau_feature_aggregator.py → vec.secured (for unsecured_exposure calc)
  └─ bureau_pdf_renderer.py      → vec.secured (for PDF/HTML display)
```

### 5d. Key Findings Engine (`pipeline/key_findings.py`)

- Generates 40+ deterministic, threshold-based findings
- Each `KeyFinding` has: `category`, `finding`, `inference`, `severity`
- Severity levels: `high_risk`, `moderate_risk`, `concern`, `neutral`, `positive`
- No LLM — purely rule-based
- Input: `BureauExecutiveSummaryInputs` + `Dict[LoanType, BureauLoanFeatureVector]` + `TradelineFeatures`

### 5e. Key Files — Bureau Vertical

| File | Role | Key Functions |
|---|---|---|
| `schemas/loan_type.py` | Taxonomy | `LoanType`, `normalize_loan_type()`, `is_secured()` |
| `features/bureau_features.py` | Feature definition | `BureauLoanFeatureVector` dataclass |
| `features/tradeline_features.py` | Pre-computed features | `TradelineFeatures` dataclass (25 customer-level features) |
| `pipeline/bureau_feature_extractor.py` | Raw data → features | `extract_bureau_features(customer_id)` |
| `pipeline/tradeline_feature_extractor.py` | CSV → pre-computed features | `extract_tradeline_features(customer_id)` |
| `pipeline/bureau_feature_aggregator.py` | Features → summary | `aggregate_bureau_features(vectors)`, `BureauExecutiveSummaryInputs` |
| `pipeline/bureau_report_builder.py` | Assembly + validation | `build_bureau_report(customer_id)` |
| `pipeline/key_findings.py` | Deterministic findings | `generate_key_findings(ei, vectors, tf)`, `KeyFinding` |
| `schemas/bureau_report.py` | Report schema | `BureauReport` dataclass (includes `tradeline_features`, `key_findings`) |
| `tools/bureau.py` | Tool entry point | `generate_bureau_report_pdf(customer_id)` |
| `pipeline/report_summary_chain.py` | LLM narration | `generate_bureau_review(executive_inputs, tradeline_features)` |
| `pipeline/bureau_pdf_renderer.py` | PDF/HTML output | `render_bureau_report_pdf(report)` |
| `templates/bureau_report.html` | HTML template | Jinja2 with `mask_id` + `inr` filters |

---

## 6. Banking Report Vertical — Architecture

```
User: "Generate report for customer 100101174"
    │
    ▼
Intent Parser → intent=CUSTOMER_REPORT, customer_id=100101174
    │
    ▼
Planner → validates customer_id against rgs.csv
    │       → plan: [{ tool: "generate_customer_report", args: { customer_id: ... } }]
    ▼
Executor → calls _generate_customer_report_with_pdf(customer_id)
    │
    ▼
report_orchestrator.generate_customer_report_pdf(customer_id)
    ├─ customer_report_builder → assembles CustomerReport (Pydantic model)
    ├─ report_summary_chain → LLM narration per section
    ├─ pdf_renderer → ReportPDF + Jinja2 HTML
    └─ Returns (CustomerReport, pdf_path)
```

### Key Files — Banking Vertical

| File | Role |
|---|---|
| `data/loader.py` | `get_transactions_df()` — loads `data/rgs.csv` |
| `tools/analytics.py` | Banking analytics tools (debit_total, credit stats, etc.) |
| `tools/spending.py` | Spending analysis tools |
| `pipeline/customer_report_builder.py` | Deterministic report assembly |
| `pipeline/report_orchestrator.py` | Wires builder → LLM → PDF |
| `pipeline/pdf_renderer.py` | `ReportPDF` base class (also imported by bureau/combined) |
| `schemas/customer_report.py` | `CustomerReport` model + `ReportMeta` |
| `templates/customer_report.html` | Jinja2 HTML template |

---

## 7. Combined Report Vertical — Architecture

Generates both banking and bureau reports (reusing caches), then merges into one document.

```
User: "Generate combined report for 100101174"
    │
    ▼
Intent Parser → intent=COMBINED_REPORT, customer_id=100101174
    │
    ▼
Planner → validates against both data sources (fail-soft: proceeds if at least one exists)
    │
    ▼
Executor → tools/combined_report.py :: generate_combined_report_pdf(customer_id)
    │
    ▼
    ├─ generate_customer_report_pdf(customer_id)  [reuses cache if available]
    ├─ generate_bureau_report_pdf(customer_id)    [reuses cache if available]
    └─ combined_report_renderer.render_combined_report_pdf(cust_report, bureau_report)
        ├─ CombinedReportPDF (inherits ReportPDF)
        ├─ Reuses _render_key_finding, _render_feature_pair from bureau_pdf_renderer.py
        └─ Save to reports/combined_{id}_report.pdf + .html
```

### Key Files — Combined Vertical

| File | Role |
|---|---|
| `tools/combined_report.py` | Tool entry point |
| `pipeline/combined_report_renderer.py` | `CombinedReportPDF` + PDF/HTML render |
| `templates/combined_report.html` | Jinja2 HTML template |

---

## 8. Guiding Principles

1. **Reuse the existing pipeline** — no new agents, planners, executors, or UI
2. **Bureau/Combined are parallel verticals**, not new systems
3. **No LLM touches raw data** — LLM sees only pre-computed summary inputs
4. **All features are deterministic** — if logic could be in LLM, move it to features
5. **Features ≠ report sections** — features are computed inputs to the report
6. **Fail-soft** — LLM narration and PDF rendering are wrapped in try/except; a failed narration still returns the data
7. **Secured classification is per raw loan type**, not per canonical type (because BL and CC have both secured and unsecured variants)

---

## 9. How to Add a New Tool or Intent

### Step-by-step:

1. **`schemas/intent.py`** — Add `NEW_INTENT = "new_intent"` to `IntentType` enum
2. **`config/intents.py`** — Add to `INTENT_TOOL_MAP` and `REQUIRED_FIELDS`
3. **`pipeline/intent_parser.py`** — Add to `VALID_INTENTS`, `PARSER_PROMPT` examples, and `_fallback_parse` keywords
4. **`tools/your_tool.py`** — Implement the tool function
5. **`pipeline/executor.py`** — Register in `tool_map`
6. **`pipeline/planner.py`** — Add tool name to `_get_tool_args` (for arg extraction)
7. **`app.py`** — If the tool produces a PDF, add handling in the report generation block

### For report-type tools specifically:

- Builder goes in `pipeline/` (deterministic, no LLM)
- LLM narration goes in `pipeline/report_summary_chain.py`
- PDF renderer goes in `pipeline/` (imports `ReportPDF` from `pdf_renderer.py`)
- HTML template goes in `templates/`
- Schema goes in `schemas/`
- Planner must validate customer ID against the **correct data source**

---

## 10. Data Sources

### Banking: `data/rgs.csv`
- Standard CSV (tab-separated, `\t` delimiter — confirm via `settings.py`)
- Key columns: `cust_id`, `dr_cr_indctor` (D=debit/C=credit), `tran_date`, `prty_name`, `tran_amt_in_ac`, `tran_partclr`, `sal_flag`, `tran_type`, `category_of_txn`
- Loaded by `data/loader.py` → `get_transactions_df()` (cached)

### Bureau: `dpd_data.csv` (project root)
- **Tab-separated** CSV
- Key columns: `crn` (customer ID), `loan_type_new` (raw loan type), `loan_status`, `sanction_amount`, `out_standing_balance`, `over_due_amount`, `creditlimit`, `last_payment_date`, `tl_vin_1` (vintage months), `sector`, `dpd_string`, `max_dpd`, `months_since_max_dpd`, `dpdf1`–`dpdf36` (36 monthly DPD flags), `date_opened`, `date_closed`
- Loaded by `pipeline/bureau_feature_extractor.py` → `_load_bureau_data()` (cached)

### Bureau Pre-computed Features: `tl_features.csv` (project root)
- **Tab-separated** CSV
- Key column: `crn` (customer ID, same as `dpd_data.csv`)
- 25 pre-computed customer-level features grouped into 6 categories:
  - **Loan Activity** (3): recency of trades, new PL trades, total trade count
  - **DPD & Delinquency** (5): max DPD by product/window, months since last 0+ DPD
  - **Payment Behavior** (5): % DPD trades, % missed payments, good closure ratio
  - **Utilization** (2): CC balance utilization, PL balance remaining
  - **Enquiry Behavior** (2): unsecured enquiries, trade-to-enquiry ratio
  - **Loan Acquisition Velocity** (7): interpurchase times across product/window combos
- NULL values mean data not available (not zero)
- Loaded by `pipeline/tradeline_feature_extractor.py` → `extract_tradeline_features()` (cached)

---

## 11. LLM Configuration

- **Model**: Ollama (local) — model names in `config/settings.py`
- **Chains**: LangChain LCEL (`ChatOllama | ChatPromptTemplate | StrOutputParser`)
- **Intent parsing**: LLM extracts JSON from `PARSER_PROMPT`
- **Narration**: Separate prompts for banking sections and bureau executive summary
- **Style**: Hinglish narration for bureau reports

---

## 12. Visualization Layer (Planned)

The bureau (and combined) HTML report will include a **Portfolio Visualizations** section with 4 interactive charts rendered via Chart.js (CDN, no server-side dependency):

| Chart | Data Source | Dimension |
|---|---|---|
| Product Mix by Count | `vec.loan_count` per loan type | Donut |
| Secured vs Unsecured | Sum secured/unsecured loan counts | Pie |
| Live vs Closed | `executive_inputs.live_tradelines` / `closed_tradelines` | Donut |
| On-Us vs Off-Us | Sum `vec.on_us_count` / `vec.off_us_count` | Pie |

Implementation plan:
- **HTML**: Chart.js injected via Jinja2 `<script>` blocks with data from `vectors_data` — zero new Python deps
- **PDF**: Matplotlib-generated PNG images embedded via `fpdf2.image()` — requires `matplotlib` dependency
- Charts live in `templates/bureau_report.html` and `pipeline/bureau_pdf_renderer.py`

---
