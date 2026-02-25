# Technical Overview — Transaction Intelligence System
## LangChain Agentic v7 HS

---

## 1. What the System Does

A **natural language querying system** over two private data sources:
1. **Banking transactions** — tab-delimited CSV (`rgs.csv`) with debit/credit history
2. **Bureau/CIBIL tradelines** — DPD (Days Past Due) data (`dpd_data.csv`) and pre-computed
   behavioral scores (`tl_features.csv`)

A user types a question ("Show spending by category for customer 12345" or "Bureau report for
CRN 98765") and the system parses the intent, runs deterministic analytics tools, optionally
invokes an LLM for narration, and responds — or generates a full PDF report.

All LLM inference runs **locally via Ollama** (no cloud API calls, no data leaves the machine).

---

## 2. System Architecture

```
┌───────────────────────────────────────────────────────────┐
│                   User Interface Layer                    │
│   app.py (Streamlit)             main.py (CLI / REPL)     │
└────────────────────────┬──────────────────────────────────┘
                         │ query(text) / query_stream(text)
┌────────────────────────▼──────────────────────────────────┐
│              TransactionPipeline (orchestrator.py)         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ Stage 1  │ │ Stage 2  │ │ Stage 3  │ │  Stage 4/5  │  │
│  │ Intent   │→│ Planner  │→│Executor  │→│  Explainer  │  │
│  │ Parser   │ │          │ │          │ │  + Insights │  │
│  └──────────┘ └──────────┘ └──────────┘ └─────────────┘  │
└───────────────────────────────────────────────────────────┘
         │              │              │
   LLM: Mistral    Pure Python   Pure Python     LLM: llama3.2
   format=json     (validation)  (tool_map)      (narration)
         │                              │
┌────────▼──────────┐     ┌────────────▼─────────────────┐
│   config/         │     │   tools/                     │
│   prompts.py      │     │   analytics.py  (15 fns)     │
│   thresholds.py   │     │   bureau_chat.py (4 fns)     │
│   intents.py      │     │   category_resolver.py       │
│   category_loader │     │   bureau.py / combined.py    │
└───────────────────┘     └──────────────────────────────┘
         │                              │
┌────────▼──────────────────────────────▼──────────────────┐
│                     Data Layer                            │
│   data/loader.py — module-level DataFrame cache          │
│   rgs.csv (transactions)  dpd_data.csv  tl_features.csv  │
└───────────────────────────────────────────────────────────┘
```

---

## 3. The Five-Stage Query Pipeline

### Stage 1 — Intent Parser (`pipeline/core/intent_parser.py`)

**Goal**: Convert free-text query → structured `ParsedIntent` object.

**Model**: `mistral` via Ollama, `temperature=0`, `format="json"`, `seed=42`

**Prompt engineering**:
- `PARSER_PROMPT` (94 lines, in `config/prompts.py`) lists all 23 valid intent names, the 40+
  category values, and the exact JSON schema the model must output.
- The prompt forces JSON output, and Ollama's `format="json"` guarantees valid JSON structure.

**Confidence scoring** (`calculate_confidence()`):
```
base = 0.5
+0.20 if intent is in VALID_INTENTS (not UNKNOWN)
+0.15 if customer_id extracted
+0.10 if category extracted (for category intents)
+0.05 if date range present
```
If confidence < `CONFIDENCE_THRESHOLD_RETRY` (0.6), the system retries the parse once
before falling through to the regex fallback.

**Regex fallback** (`_fallback_parse()`):
Handles common patterns without LLM: customer ID extraction (`\b\d{5,10}\b`), bureau intents
(`"bureau"` keyword), combined report, category presence queries.

**Category normalization** (`normalize_category_name()`):
`difflib.get_close_matches()` with cutoff=0.7 resolves typos like "Foood" → "Food".

**Output**: `ParsedIntent(intent, customer_id, category, start_date, end_date, top_n, confidence, raw_query)`

---

### Stage 2 — Query Planner (`pipeline/core/planner.py`)

**Goal**: Validate the parsed intent and produce an execution plan.

**Entirely deterministic — no LLM.**

**Validation checks**:
- `customer_id` exists in `rgs.csv` (banking) or `dpd_data.csv` (bureau), depending on intent type
- Bureau intents validate against `valid_bureau_customers` (CRNs from dpd_data)
- `COMBINED_REPORT` checks customer is present in at least one data source
- Category intents validate against live transaction categories from the DataFrame
- Date formats validated with `datetime.strptime(date, "%Y-%m-%d")`

**Plan building**:
Looks up `INTENT_TOOL_MAP[intent]` → list of tool names → list of `{"tool": name, "args": {...}}` dicts.
`COMPARE_CATEGORIES` is a special case: expands to one tool call per category.

**Safety**: `MAX_TOOLS_PER_QUERY = 5` prevents runaway plans.

---

### Stage 3 — Tool Executor (`pipeline/core/executor.py`)

**Goal**: Execute each tool in the plan and collect `ToolResult` objects.

**tool_map** (20+ entries):
```python
{
  "debit_total":               analytics.debit_total,
  "get_spending_by_category":  analytics.get_spending_by_category,
  "generate_customer_report":  _generate_customer_report_with_pdf,
  "generate_bureau_report":    _generate_bureau_report_with_pdf,
  "category_presence_lookup":  category_presence_lookup,
  "bureau_credit_card_info":   bureau_credit_card_info,
  ...
}
```

All tools return `Dict[str, Any]`. Every call is wrapped in `try/except`:
```python
ToolResult(tool_name, args, result={}, success=False, error=str(e))
```
The pipeline continues even if a tool fails — fail-soft throughout.

---

### Stage 4 — Transaction Insight Extraction (`pipeline/insights/transaction_flow.py`)

**Conditional** — only fires for `INSIGHT_INTENTS`:
`{LENDER_PROFILE, CUSTOMER_REPORT, FINANCIAL_OVERVIEW}`

**Model**: `llama3.2`, `temperature=0`, `format="json"`

Uses `TRANSACTION_INSIGHT_PROMPT` to extract behavioral patterns from up to 40 recent
transactions formatted as `date | DR/CR | amount | category | type`.

`get_insight_extractor()` returns a module-level singleton. Results are cached in
`pipeline/insights/insight_store.py` (module-level dict keyed by `(customer_id, scope)`).

**Filtering** (`utils/transaction_filter.py`):
Five scopes: `patterns`, `recurring_only`, `top_merchants`, `credits_only`, `default`.
Each scope selects the most relevant 40 transactions for the LLM.

---

### Stage 5 — Response Explainer (`pipeline/core/explainer.py`)

**Model**: `llama3.2`, `temperature=0`, `seed=42`

Merges tool results and (optional) transaction insights into a single string, then passes
to `EXPLAINER_PROMPT.format(query=..., data=...)`.

**Streaming**: `stream_explain()` calls `llm.stream(prompt)` and yields chunks.
`STREAM_DELAY` (default 0.025s) can be injected between chunks for readable UX.

**Special formatters**:
- `_format_category_presence()` — structured display for category lookup results
- `_format_customer_report()` — extracts key highlights from full report dict

**Audit**: Every query is logged as JSONL to `logs/audit_YYYYMMDD.jsonl`
(`AuditLog` schema: timestamp, raw_query, parsed_intent, tools_executed, response, latency_ms).

---

## 4. Report Generation Pipelines

Three parallel report verticals share infrastructure:

```
Customer Report (Banking)     Bureau Report           Combined Report
─────────────────────────     ─────────────────       ───────────────
customer_report_builder       bureau_feature_         Calls both above
 ├── _get_salary_block          extractor              + executive
 ├── _get_emi_block              (per-LoanType)          summary LLM
 ├── _get_rent_block           bureau_feature_         combined_report_
 ├── _get_bills_block            aggregator             renderer.py
 └── _get_category_overview    tradeline_feature_
                                extractor
report_orchestrator.py        key_findings.py
 (planner-driven)              (NO LLM, pure
                                thresholds)
report_summary_chain.py       report_summary_chain.py
 generate_customer_review      generate_bureau_review
 generate_customer_persona

pdf_renderer.py               bureau_pdf_renderer.py  combined_report_renderer.py
(fpdf2 + Jinja2 HTML)
```

### Report Planner

`pipeline/reports/report_planner.py` — LLM (mistral) decides which sections to include based
on a `data_profile` dict (has_salary, has_emi, transaction_count, month_count, ...).

Has a deterministic `_default_plan()` fallback that fires on any LLM error — in practice
this is the reliable path.

### Caching

`_REPORT_CACHE: Dict[(customer_id, period_str), CustomerReport]` in `report_orchestrator.py`.
No TTL — cache lives for the process lifetime. `invalidate_customer_cache()` allows manual purge.

---

## 5. Bureau Feature Extraction

### Loan Type Taxonomy (`schemas/loan_type.py`)

`LoanType` enum with 13 canonical types: `PL, CC, HL, AL, BL, LAP, LAS, LAD, GL, TWL, CD, CMVL, OTHER`.

`LOAN_TYPE_NORMALIZATION_MAP` maps 100+ raw strings from the bureau CSV to canonical types:
```python
"PERSONAL LOAN"      → LoanType.PL
"CREDIT CARD"        → LoanType.CC
"GOLD LOAN"          → LoanType.GL
```
`normalize_loan_type()` uses `.get()` with fallback to `LoanType.OTHER`.

`ON_US_SECTORS = {"KOTAK BANK", "KOTAK PRIME"}` — tracks own-bank vs competitor tradelines.

### Feature Vector (`pipeline/extractors/bureau_feature_extractor.py`)

Per-customer, per-loan-type processing:
1. Load `dpd_data.csv` into a list of dicts (module-level cache `_bureau_df`)
2. Filter rows by `crn == customer_id`
3. Group rows by `normalize_loan_type(row["loan_type_new"])`
4. Call `_build_feature_vector(loan_type, tradelines)` for each group

Key computations:
- **DPD**: `_compute_max_dpd()` reads pre-computed `max_dpd` and `months_since_max_dpd` columns
- **Utilization** (CC only): `sum(outstanding) / sum(credit_limit)` across live tradelines
- **Vintage**: Average of `tl_vin_1` (months since opening)
- **Forced events**: Regex `[A-Z]{3}` in `dpd_string` excluding `STD`, `XXX`
- **Timeline**: `earliest_opened`, `latest_opened`, `latest_closed` from `date_opened`/`date_closed`
- **Monthly exposure**: Rolling 24-month sanction exposure chart data for PDF

### Pre-computed Tradeline Features (`pipeline/extractors/tradeline_feature_extractor.py`)

`tl_features.csv` contains 65+ model-ready behavioral signals (already computed by an upstream
scoring engine). The extractor loads the CSV, looks up by `crn`, and hydrates the
`TradelineFeatures` dataclass via `_COLUMN_MAP` (CSV column → field name mapping).

Cross-field consistency fixes applied after loading:
- If `months_since_last_0p_uns` is null but `months_since_last_0p_pl` is not → fill from PL
- If `max_dpd_9m_cc < max_dpd_6m_cc` → override with 6M value (temporal subset logic)
- If `pct_0plus_24m_pl > pct_0plus_24m_all` → override All with PL (PL is a subset)

### Key Findings (`pipeline/reports/key_findings.py`)

**Zero LLM calls.** Pure threshold comparison against named constants from `config/thresholds.py`.

```python
import config.thresholds as T

if ei.max_dpd > T.DPD_HIGH_RISK:         # 90 days
    findings.append(high_risk finding)
elif ei.max_dpd > T.DPD_MODERATE_RISK:   # 30 days
    findings.append(moderate finding)
```

Produces `KeyFinding(category, finding, inference, severity)` objects.
Severity labels: `"high_risk"`, `"moderate_risk"`, `"concern"`, `"positive"`, `"neutral"`.

Four finding groups:
1. **Portfolio** — overall delinquency, total tradelines, sanctioned/outstanding amounts
2. **Loan-type** — per-type analysis (CC utilization, PL balance %, HL/AL presence)
3. **Tradeline** — behavioral scores (enquiry velocity, interpurchase time, missed payments)
4. **Composite** — multi-signal risk combinations (high enquiries + new PL + high utilization)

---

## 6. Configuration Architecture

### Single Sources of Truth

| File | Owns |
|---|---|
| `config/thresholds.py` | 35+ business rule thresholds (DPD_HIGH_RISK=90, CC_UTIL_HIGH_RISK=75, …) |
| `config/prompts.py` | All 7 LLM prompts as named string constants |
| `config/settings.py` | Model names, file paths, LLM_TEMPERATURE=0, LLM_SEED=42, STREAM_DELAY |
| `config/intents.py` | INTENT_TOOL_MAP (44 mappings), REQUIRED_FIELDS, MAX_TOOLS_PER_QUERY |
| `config/category_loader.py` | YAML-driven category config with `@lru_cache` |
| `schemas/loan_type.py` | LOAN_TYPE_NORMALIZATION_MAP (100+ raw → 13 canonical) |

### Category Configuration (`config/categories.yaml`)

YAML-driven, not hardcoded. Each category entry has:
```yaml
Food:
  display_name: Food & Dining
  direction: DR           # debit-only
  keywords: [zomato, swiggy, restaurant, hotel, cafe]
  aliases: [food, dining, eating]
  min_count: 1
```
`resolve_category_alias()` resolves user input → canonical key using:
exact match → display name match → alias match → partial match.

---

## 7. Category Presence Resolution (4-Strategy Matching)

`tools/category_resolver.py` — used for EMI, rent, utility detection in reports
and for `CATEGORY_PRESENCE_LOOKUP` queries:

```
Strategy 1: Direct column match
  df['category_of_txn'].str.lower() == user_category.lower()

Strategy 2: YAML config match
  Check all category_matches values in CategoryConfig

Strategy 3: Keyword match
  Any keyword from get_all_keywords_for_category() found in narration

Strategy 4: Fuzzy match (if fuzzywuzzy installed)
  token_set_ratio(narration, category) >= threshold (default 75)
```

Strategies are tried in order; first hit wins. Returns `CategoryPresenceResult`
with `present`, `total_amount`, `transaction_count`, and up to 10 `SupportingTransaction` objects.

---

## 8. Rendering Pipeline

### HTML (Primary)
Jinja2 templates (`templates/customer_report.html`, `bureau_report.html`, `combined_report.html`)
with Chart.js for monthly exposure timeseries charts.

Custom filters registered on the Jinja2 `Environment`:
```python
env.filters['mask_id']   = mask_customer_id     # ###XXXX format
env.filters['inr_units'] = format_inr_units     # "1.86 Cr", "54 L"
env.filters['segment']   = strip_segment_prefix # removes sort-code prefix
```

### PDF (Secondary)
`fpdf2` (pure Python, no system dependencies). `ReportPDF` extends `FPDF` with:
- `section_title()`, `section_text()`, `key_value()`, `table_header()`, `table_row()`
- `_sanitize_text()`: replaces Unicode (₹, —, ", ") with Latin-1 equivalents for PDF safety

`BureauReportPDF` and `CombinedReportPDF` both extend `ReportPDF`, overriding only the
`header()` method. Helper functions (`_render_key_finding`, `_render_group_header`, etc.)
defined once in `bureau_pdf_renderer.py` and imported into `combined_report_renderer.py`.

---

## 9. Key Design Principles

| Principle | Implementation |
|---|---|
| **Determinism > Intelligence** | All risk scoring and threshold checking is pure Python. LLM is used only for narration/persona, never for decisions. |
| **Fail-soft everywhere** | Every LLM call and every tool execution is wrapped in `try/except`. Failures produce `None` or empty results, never crashes. |
| **Local inference** | All models run via Ollama. No data transmitted to cloud. Two models: `mistral` (parsing, structured JSON) and `llama3.2` (narration). |
| **Configuration-driven** | Business rules live in `config/thresholds.py`, not inside logic functions. Prompts in `config/prompts.py`. Categories in YAML. |
| **Multi-layer caching** | DataFrame (module-level), categories (`@lru_cache`), reports (`_REPORT_CACHE` dict), insights (`_INSIGHT_CACHE` dict). |
| **Schema-first** | All inter-module data is typed via Pydantic models (`ParsedIntent`, `CustomerReport`, `ToolResult`, `AuditLog`) or dataclasses (`BureauLoanFeatureVector`, `TradelineFeatures`). |

---

## 10. Data Flow — End to End

```
User: "Lender profile for customer 10001"
  │
  ├─ IntentParser (Mistral, JSON mode)
  │    → ParsedIntent(intent=LENDER_PROFILE, customer_id=10001, confidence=0.85)
  │
  ├─ QueryPlanner (pure Python)
  │    → validates 10001 ∈ rgs.csv customers
  │    → plan = [{"tool": "generate_lender_profile", "args": {"customer_id": 10001}}]
  │
  ├─ ToolExecutor
  │    → analytics.generate_lender_profile(10001)
  │    → ToolResult(success=True, result={...creditworthiness dict...})
  │
  ├─ Transaction Insight Extraction (LENDER_PROFILE in INSIGHT_INTENTS)
  │    → filter last 40 transactions (scope="patterns")
  │    → llama3.2 JSON → TransactionInsights(patterns=[...])
  │    → cached in _INSIGHT_CACHE[(10001, "patterns")]
  │
  └─ ResponseExplainer (llama3.2, streaming)
       → EXPLAINER_PROMPT.format(query=..., data=tool_results + insights)
       → streams response tokens to UI
       → AuditLogger.log(latency_ms, ...)
```

---

## 11. Streaming Architecture

```python
# orchestrator.query_stream()
def query_stream(self, query: str, ...) -> Iterator[str]:
    intent   = self.parser.parse(query)          # blocking (LLM)
    plan, _  = self.planner.create_plan(intent)  # blocking (pure Python)
    results  = self.executor.execute(plan)        # blocking (tools)
    insights = get_transaction_insights_if_needed(intent, ...)  # blocking (LLM)
    yield from self.explainer.stream_explain(intent, results, insights)  # streaming

# explainer.stream_explain()
for chunk in self.llm.stream(prompt):
    if chunk.content:
        yield chunk.content
    if self.stream_delay > 0:
        time.sleep(self.stream_delay)  # STREAM_DELAY = 0.025s default
```

Stages 1–4 block sequentially (no parallelism). Stage 5 (explanation) streams.

---

## 12. LLM Configuration Summary

| Use | Model | Temperature | Seed | Format | Prompt |
|---|---|---|---|---|---|
| Intent parsing | mistral | 0 | 42 | json | PARSER_PROMPT (94 lines) |
| Report section planning | mistral | 0 | 42 | json | REPORT_PLANNER_PROMPT |
| Transaction insights | llama3.2 | 0 | 42 | json | TRANSACTION_INSIGHT_PROMPT |
| Customer review (3-4 lines) | llama3.2 | 0 | 42 | text | CUSTOMER_REVIEW_PROMPT |
| Customer persona (4-5 lines) | llama3.2 | 0.1 | 42 | text | CUSTOMER_PERSONA_PROMPT |
| Bureau narrative | llama3.2 | 0 | 42 | text | BUREAU_REVIEW_PROMPT |
| Combined executive summary | llama3.2 | 0 | 42 | text | COMBINED_EXECUTIVE_PROMPT |

`temperature=0` everywhere except persona (0.1) for slight variety. `seed=42` for
reproducibility. All hardcoded values now sourced from `config/settings.py`.

---

---

# Senior Tech Lead Q&A — Likely Questions

## Architecture & Design

**Q1. Why Ollama/local models instead of OpenAI or Anthropic API?**
> The transaction and bureau data is sensitive financial PII (customer IDs, transaction amounts,
> bureau tradelines). Running inference locally means zero data egress. The tradeoff is lower
> model quality vs. privacy guarantee. Ollama also removes API cost and latency variability.

**Q2. Why use two different models (Mistral for parsing, llama3.2 for narration)?**
> Intent parsing requires strict structured JSON output — Mistral follows instruction formats
> and JSON mode more reliably. llama3.2 is used for all generative narration (summaries,
> personas, explanations) where creative prose matters more than JSON discipline.

**Q3. Why is `format="json"` used for some chains but not others?**
> Ollama's `format="json"` forces the model to produce valid JSON structure (brackets,
> quotes) but does not validate the JSON against a schema. It's used when we *must* parse
> the response programmatically (intent parser, report planner, insight extractor). Narrative
> chains don't use it because we want flowing prose, not JSON.

**Q4. The report planner uses an LLM to decide which sections to include. Why not just
always include all sections?**
> The planner avoids generating sections with no data (e.g., an EMI section for a customer
> with no EMI transactions). The LLM decides based on a `data_profile` dict (has_salary,
> has_emi, transaction_count…). The deterministic `_default_plan()` fallback produces the
> same result reliably, so the LLM path is arguably redundant — a valid design critique.

**Q5. `key_findings.py` is 584 lines of pure threshold logic. Why not use an LLM to
generate findings?**
> Banking risk rules are regulatory and need to be auditable. A threshold-based approach
> is deterministic, explainable, and consistent — the same input always produces the same
> finding. LLM-generated risk labels would be non-deterministic and hard to audit.
> The LLM is used only *after* findings are extracted, to narrate them in natural language.

**Q6. How do you ensure the thresholds used in `key_findings.py` are the same ones the
LLM uses when generating the bureau narrative?**
> Both import from `config/thresholds.py` using the alias `import config.thresholds as T`.
> The same constant (e.g., `T.CC_UTIL_HIGH_RISK = 75`) is used in the deterministic
> threshold check AND referenced by name in the LLM prompt context that shows annotated
> data. There is a single source of truth.

**Q7. You have three caching layers (data, reports, insights). What happens if data is
updated?**
> `_transactions_df` (module-level) requires a process restart or calling
> `load_transactions(force_reload=True)`. `_REPORT_CACHE` has `clear_report_cache()` and
> `invalidate_customer_cache()`. `_INSIGHT_CACHE` has `clear_all_cache()`. There is no
> automatic cache invalidation — this is suitable for a batch/session-based analytics tool
> where data is refreshed daily, not for real-time systems.

---

## Implementation Details

**Q8. How does the intent confidence score work? What's the retry logic?**
> Base score 0.5 → increments for each extracted field (+0.2 for valid intent, +0.15 for
> customer_id, +0.10 for category, +0.05 for dates). If confidence < 0.6
> (`CONFIDENCE_THRESHOLD_RETRY`), the parser retries the LLM call once.
> If still below 0.4 (`CONFIDENCE_THRESHOLD_LOW`), a warning is logged.
> Below 0.6 after retry → regex fallback `_fallback_parse()`.

**Q9. The regex fallback in intent_parser — how robust is it?**
> It handles the most common patterns only: numeric customer IDs, "bureau" keyword,
> "combined report", and category presence queries. It is not a full parser — it is a
> safety net for Mistral failures. The model must be running for full intent resolution.

**Q10. How does `LOAN_TYPE_NORMALIZATION_MAP` handle loan types not in the 100+ entry map?**
> `normalize_loan_type()` uses `dict.get(raw_type.strip().upper(), LoanType.OTHER)`.
> Unknown types default to `LoanType.OTHER`. This is logged implicitly when the feature
> vector is built, since `OTHER` will aggregate all unknown types together.

**Q11. What are the null-safety patterns used for bureau CSV parsing?**
> Two sets of helpers: `_safe_float(val, default=0.0)` / `_safe_int(val, default=0)` in
> `bureau_feature_extractor.py` (returns default for NULL/empty) and
> `_safe_optional_float(val)` / `_safe_optional_int(val)` / `_safe_optional_str(val)` in
> `tradeline_feature_extractor.py` (returns `None` for NULL/empty). The Optional variants
> are used for `TradelineFeatures` where `None` means "data not available" vs. 0.

**Q12. How does the 4-strategy category matching work and why is the order important?**
> Strategies are tried in order — first hit wins:
> 1. Exact column match (fastest, most precise)
> 2. YAML `category_matches` (controlled vocabulary)
> 3. Keyword scan of narration text (broad)
> 4. Fuzzy narration match (catch-all, threshold 75%)
> Order matters because fuzzy matching has false-positive risk. Running it last ensures
> it only fires when the more precise strategies fail. fuzzywuzzy is an optional
> dependency — the system degrades to exact matching if not installed.

**Q13. What schema validation strategy is used? Why mix Pydantic and dataclasses?**
> Pydantic models are used at system boundaries where validation is needed at runtime:
> `ParsedIntent`, `CustomerReport`, `ToolResult`, `AuditLog`. Dataclasses are used for
> internal, immutable computed data (`BureauLoanFeatureVector`, `TradelineFeatures`,
> `BureauExecutiveSummaryInputs`) where validation overhead isn't warranted and where
> `asdict()` serialization for JSON rendering is needed.

**Q14. How is prompt injection prevented?**
> The user query is passed as a variable into the explainer prompt (`data=tool_results`),
> not as a system instruction. The intent parser uses a structured JSON output format that
> limits what the model can produce. However, there is no explicit sanitization of the
> raw query text — this is a risk if the system is exposed to untrusted users.

**Q15. How does streaming work in the Streamlit UI?**
> `orchestrator.query_stream()` is a generator. Streamlit's `st.write_stream()` consumes
> it chunk by chunk. Stages 1–4 (parsing, planning, execution, insights) block before
> streaming begins — the user sees a progress indicator during these phases, then the
> text streams in for the LLM explanation phase.

---

## Performance & Scalability

**Q16. What is the approximate end-to-end latency breakdown?**
> Rough estimates on local hardware (M-series Mac, Ollama):
> - Intent parsing (Mistral): 1–3s
> - Planner (pure Python): < 50ms
> - Tool execution (pandas analytics): 100–500ms per tool
> - Transaction insights (llama3.2): 2–5s (conditional)
> - Explanation (llama3.2, streaming): 3–8s first token, then continuous
> - PDF rendering (fpdf2 + Jinja2): 1–2s
> Total for a simple query: ~5–10s. Full report: 15–30s.

**Q17. `_REPORT_CACHE` has no TTL. What's the failure mode?**
> In a long-running session, stale reports accumulate in memory. If data is refreshed
> mid-session, the cache returns the old report. Mitigation: `invalidate_customer_cache()`
> is exposed for manual purge. Long-term: add a TTL or timestamp-based invalidation.

**Q18. Can this handle multiple concurrent users?**
> No — module-level caches (`_transactions_df`, `_bureau_df`, `_REPORT_CACHE`,
> `_INSIGHT_CACHE`) are process-global and not thread-safe. Ollama itself is single-threaded
> per model instance. For multi-user use, each user session would need a separate process
> or proper async/locking around the caches.

**Q19. Why does `transaction_flow.py` use a singleton `_insight_extractor` instead of
constructing a new one per call?**
> `ChatOllama` model loading has non-trivial overhead. The singleton pattern ensures the
> model is loaded once per process. This is fine for single-user CLI/Streamlit but would
> need a connection pool for concurrent usage.

---

## Data & Domain

**Q20. What is DPD (Days Past Due) and how is it computed from the raw data?**
> DPD measures how many days a loan payment is overdue. `max_dpd` and
> `months_since_max_dpd` are pre-computed columns in `dpd_data.csv`. The extractor reads
> these directly rather than recomputing from the raw `dpd_string` (a month-by-month
> payment history encoded as e.g. "000STD030060WRF"). `_extract_forced_event_flags()`
> does parse `dpd_string` to find 3-letter non-standard events (WRF=Written-off, SET=Settlement,
> SMA=Special Mention Account).

**Q21. What is the significance of ON_US_SECTORS?**
> `ON_US_SECTORS = {"KOTAK BANK", "KOTAK PRIME"}` identifies Kotak's own lending
> products within a customer's bureau profile. `on_us_count` vs `off_us_count` in the
> feature vector lets the bank understand how much of a customer's debt exposure is with
> Kotak itself — relevant for credit decisioning (concentration risk, cross-sell opportunity).

**Q22. Why does the customer persona chain use `temperature=0.1` while everything else uses 0?**
> Persona generation ("Who is this customer as a person?") benefits from slight randomness
> to avoid formulaic, identical outputs across similar customers. A temperature of 0.1
> introduces minimal variance while keeping the output grounded. Risk/analysis chains use
> temperature=0 for reproducibility.

**Q23. How does the `compute_monthly_exposure()` function work and what is it used for?**
> For each of the past 24 calendar months, it sums `sanction_amount` for all tradelines
> that were active during that month (opened ≤ month end AND closed ≥ month start OR still
> live). The result is a time-series dict `{month_label: [PL_exposure, CC_exposure, ...]}`
> rendered as a stacked area chart in the bureau report HTML template via Chart.js.

---

## Code Quality

**Q24. Why were the prompts centralized into `config/prompts.py`?**
> Originally each module (intent_parser, explainer, transaction_flow, report_summary_chain)
> defined its own prompt string inline. Centralization means: a prompt change doesn't require
> finding which module owns it; prompts can be version-controlled and reviewed independently;
> the same threshold names referenced in prompts can be co-located with `config/thresholds.py`.

**Q25. What was the reasoning behind splitting `pipeline/` into 5 sub-packages?**
> A flat 22-file directory makes it difficult to understand which files are related.
> The split groups files by concern: `core/` (query pipeline), `insights/` (pattern extraction),
> `reports/` (report generation), `extractors/` (CSV feature computation), `renderers/` (PDF/HTML).
> `pipeline/__init__.py` re-exports the public API, so external callers (`app.py`, `tools/`) are
> completely unaffected by the reorganization.

---

*End of Technical Overview*
