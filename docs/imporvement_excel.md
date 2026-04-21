# Batch Report Optimization — Implementation Document

## System Prompt

You are implementing optimizations to a batch report generation pipeline for a banking/bureau credit decisioning system. The project is at `/Users/ayyoob/Desktop/Projects/langchain_agentic_v7_hs/`. Use Python interpreter `/Users/ayyoob/anaconda3/bin/python`. Follow the project's existing patterns: fail-soft (try/except with logger.warning), deterministic numbers (never LLM for computation), centralized config in `config/settings.py` and `config/thresholds.py`. Do NOT change any LLM model or prompt — quality must be preserved. Implement phases in order (Phase 2 → 3 → 1 → 4 → 5 → 6). After each phase, verify with `python batch_reports.py --crns 698167220 --output reports/test_batch.xlsx`.

---

## Problem Statement

Generating combined reports for 2000 customers takes ~130 hours serially (~4min/customer). The batch pipeline (`batch_reports.py`) processes each customer sequentially. Within each customer, 3 LLM calls run sequentially even though the first 2 are independent. The final Excel is only produced after ALL customers complete — a crash near the end loses progress. Adding new Excel columns requires editing multiple places in `build_excel_row()`.

**Goal:** Reduce wall-clock time by 5-10x through parallelism, make Excel columns trivially extensible, and ensure crash-resilient incremental output.

---

## Measured Token Usage (Real Data — CRN 698167220)

Token-level instrumentation has been implemented (see Phase 0 below). Here are the **measured** numbers from a single customer run on local Ollama with llama3.2 3B:

| LLM Chain | Input Tokens | Output Tokens | Reasoning Tokens | Wall Time | Speed |
|---|---|---|---|---|---|
| **CustomerReview** | 885 | 345 | 0 | 19.9s | 17.3 tok/s |
| **BureauReview** | 1,443 | 257 | 0 | 29.0s | 8.9 tok/s |
| **CombinedSummary** | 1,613 | 192 | 0 | 24.2s | 7.9 tok/s |
| **TOTAL** | **3,941** | **794** | **0** | **73.1s** | **10.9 tok/s avg** |

**Key corrections from earlier estimates:**
- **Only 3 LLM calls in batch mode**, not 4. `generate_customer_persona()` is only called in `save_intermediate=True` (interactive) path, NOT in the batch pipeline's `save_intermediate=False` path.
- Input tokens are smaller than estimated (3,941 vs ~5,000 estimated)
- Speed varies per call (17.3 tok/s first call due to warm cache, drops to ~8 tok/s for later calls competing for Ollama resources)
- LLM wall time is 73s out of ~76s total = **96% of time is LLM inference** for this customer

### DeepSeek-R1 14B on SageMaker (Production)

Production uses **deepseek-r1 14B** on SageMaker, NOT llama3.2 locally. Key differences:

| Factor | llama3.2 3B (local Ollama) | deepseek-r1 14B (SageMaker) |
|---|---|---|
| Model size | 3B params | 14B params |
| Reasoning tokens | 0 (no thinking) | **200-800 per call** (thinking model) |
| Input token budget | Same prompts | Same prompts + reasoning overhead |
| Output speed | 8-17 tok/s | Depends on GPU instance (see below) |
| Total tokens/customer | ~4,735 | **~6,000-8,000** (incl. reasoning) |

**Estimated deepseek-r1 14B token budget per customer:**

| LLM Chain | Input Tokens | Output Tokens | Reasoning Tokens | Est. Total |
|---|---|---|---|---|
| CustomerReview | ~900 | ~350 | ~300-600 | ~1,550-1,850 |
| BureauReview | ~1,450 | ~260 | ~400-800 | ~2,110-2,510 |
| CombinedSummary | ~1,600 | ~200 | ~200-500 | ~2,000-2,300 |
| **TOTAL** | **~3,950** | **~810** | **~900-1,900** | **~5,660-6,660** |

**SageMaker throughput estimates:**

| Instance | GPU | Approx. Speed | Per-Customer LLM Time | 2000 Customers (serial) |
|---|---|---|---|---|
| ml.g5.xlarge | 1x A10G (24GB) | ~15-25 tok/s | ~90-120s | ~50-67h |
| ml.g5.2xlarge | 1x A10G (24GB) | ~15-25 tok/s | ~90-120s | ~50-67h |
| ml.p4d.24xlarge | 8x A100 (80GB) | ~80-120 tok/s | ~20-30s | ~11-17h |

**Note:** These are rough estimates. Actual throughput depends on SageMaker endpoint configuration, batch size, and whether continuous batching is enabled. The token instrumentation (Phase 0) will give exact numbers on SageMaker.

---

## Measured Timing Breakdown (Per Customer)

Based on the instrumented run (CRN 698167220, llama3.2 3B local):

| Step | Component | Measured Time | % of Total |
|---|---|---|---|
| 1 | Banking build (deterministic) | ~8s | 10% |
| 2 | **LLM #1: CustomerReview** | **19.9s** | **26%** |
| 3 | Bureau build (deterministic) | ~2s (cached) | 3% |
| 4 | **LLM #2: BureauReview** | **29.0s** | **38%** |
| 5 | **LLM #3: CombinedSummary** | **24.2s** | **32%** |
| 6 | Scorecard + Checklist + Render | ~3s | 4% |
| **TOTAL** | | **~76s** | |

**LLM dominates:** 73.1s / 76s = **96% of wall time is LLM inference** (for this small-transaction customer).

For customers with 100+ transactions, the deterministic steps (merchant fuzzy matching, event detection) take longer (15-25s), so LLM share drops to ~70-80% and total time reaches 4 minutes.

---

## Quick Wins Playbook — Ordered by Effort vs Impact

Implementation order optimized for **fastest time-to-value**. Each step is independent enough to deploy and measure before moving to the next. The first 3 wins require minimal or zero code changes.

### Win 1: Bigger GPU on SageMaker (0 code changes, ~6x speedup)

**Effort:** 30 min (infrastructure only)
**Impact:** 133h → ~22h for 2000 customers

The current bottleneck is 96% LLM inference. A bigger GPU doesn't need any code changes — just a SageMaker endpoint config update.

| Current | Target | What changes |
|---|---|---|
| ml.g5.xlarge (1x A10G, 24GB) | ml.g5.12xlarge (4x A10G, 96GB) | Endpoint config only |
| ~15-25 tok/s, serial | ~60-100 tok/s, 4x concurrency | Same model, more VRAM |
| ~240s per customer | ~40s per customer | 6x faster |

**Steps:**
1. Update SageMaker endpoint to `ml.g5.12xlarge` (or `ml.p4d.24xlarge` for 128GB+ VRAM)
2. Enable concurrent inference on the endpoint (set `MAX_CONCURRENT_INVOCATIONS=8`)
3. Run the same `batch_reports.py` — no code changes needed
4. Check `*.tokens.jsonl` to measure actual tok/s improvement

**Why this is Win 1:** Zero risk, zero code changes, immediately measurable. The token instrumentation (Phase 0) is already in place to validate the speedup. If the GPU alone gets you to acceptable speed, you may not need the remaining wins.

---

### Win 2: Intra-Customer Parallelism — Phase 1 (~30 min code, +1.5x on top of Win 1)

**Effort:** 30 min (modify 1 file: `tools/combined_report.py`)
**Impact:** Shaves ~28s off every customer by running banking + bureau LLM calls in parallel

Currently the 3 LLM calls run in sequence:
```
CustomerReview (20s) → BureauReview (29s) → CombinedSummary (24s) = 73s serial
```

After Phase 1:
```
┌─ CustomerReview (20s) ─┐
│                        ├→ CombinedSummary (24s) = 45s total
└─ BureauReview  (29s) ──┘
```

**Steps:**
1. Extract banking/bureau branches into `_build_and_review_banking()` and `_build_and_review_bureau()`
2. Wrap in `ThreadPoolExecutor(max_workers=2)` for the `save_intermediate=False` path
3. Set `OLLAMA_NUM_PARALLEL=2` (or ensure SageMaker endpoint allows 2 concurrent requests per worker)
4. Run, check token JSONL — CustomerReview and BureauReview timestamps should overlap

**Combined with Win 1:** 133h → ~22h (GPU) → ~15h (parallel LLM) for 2000 customers.

---

### Win 3: Inter-Customer Parallelism — Phase 4 (~1h code, +2-4x on top of Win 2)

**Effort:** 1h (modify `batch_reports.py` + `config/settings.py`)
**Impact:** Process 2-8 customers simultaneously instead of 1 at a time

**Steps:**
1. Add `--workers N` CLI flag and `BATCH_MAX_WORKERS` config
2. Wrap the CRN loop in `ThreadPoolExecutor(max_workers=N)`
3. Use `threading.Lock` on CSV append (or per-customer xlsx — existing pattern)
4. Start with `--workers 2`, increase based on GPU headroom

**Scaling math (deepseek-r1 14B on SageMaker):**

| GPU Config | --workers | LLM Concurrency | Per-Customer (eff.) | 2000 Customers |
|---|---|---|---|---|
| 1x A10G (24GB) | 1 | 2 (Phase 1) | ~160s | ~89h |
| 4x A10G (96GB) | 4 | 8 (Phase 1 × 4) | ~40s | ~22h |
| 4x A10G + Phase 1 | 4 | 8 | ~27s | ~15h |
| **128GB (p4d or similar)** | **8** | **16** | **~13s** | **~7h** |

**Combined with Win 1+2:** 133h → ~7-15h for 2000 customers. **This is likely sufficient for production.**

---

### Win 4: Crash Resilience — Phase 3 (~1h code, no speed gain but prevents data loss)

**Effort:** 1h (modify `tools/excel_exporter.py`, `tools/combined_report.py`, `batch_reports.py`)
**Impact:** A crash at customer 1999 no longer loses all progress

Currently the Excel is only written per-customer as individual files, then merged at the end. If the process dies, completed customers are preserved via resume mode. But:
- Resume mode scans `reports/excel/*.xlsx` files (slow for thousands)
- No single progress file to inspect mid-run

**Steps:**
1. Add `append_row_to_csv()` — writes each customer to a single master CSV immediately
2. Add `csv_to_excel()` — converts CSV to xlsx at end
3. Update resume mode to read completed CRNs from CSV (fast lookup)
4. The CSV is also useful for monitoring: `wc -l reports/batch_progress.csv` shows progress

**Do this before running the full 2000-customer batch.** The speed wins are useless if a crash at hour 6 means restarting from scratch.

---

### Win 5: Skip HTML Rendering — Phase 5 (~30 min code, saves ~3s/customer)

**Effort:** 30 min (add `--skip-html` flag, add `render_html` parameter)
**Impact:** Saves ~3s per customer (mostly Jinja2 + file I/O). Small per-customer gain but compounds: 3s × 2000 = 100 min saved.

Only do this if you don't need the HTML reports for this batch run (e.g. you only need the Excel summary).

---

### Win 6: Column Registry Refactor — Phase 2 (~2h code, no speed gain)

**Effort:** 2h (refactor `tools/excel_exporter.py`)
**Impact:** Zero speed improvement. Makes adding/removing Excel columns trivial.

**Do this when:** You need to add new columns (scorecard, checklist, persona data) to the Excel output. Not urgent for the speed problem.

---

### Win 7: vLLM / SageMaker Continuous Batching — Phase 6 (~2h code + infra, +2-3x on top of Win 3)

**Effort:** 2h code + SageMaker/vLLM setup
**Impact:** Continuous batching processes 8-16 LLM requests as a single GPU batch, eliminating per-request scheduling overhead

**When to do this:** Only if Wins 1-3 don't get you to acceptable speed. vLLM gives the most benefit when you have many concurrent requests (8+). With `--workers 8` from Win 3, the GPU is already saturated — vLLM's continuous batching squeezes out the last 2-3x.

**Steps:**
1. Add `_get_llm()` factory in `report_summary_chain.py`
2. Add `LLM_BACKEND` / `VLLM_BASE_URL` to `config/settings.py`
3. Deploy vLLM on SageMaker (or run locally: `vllm serve deepseek-ai/deepseek-r1-14b`)
4. Set `LLM_BACKEND=vllm` and run

---

### Summary: Cumulative Impact

```
                                    deepseek-r1 14B, 2000 customers
                                    ─────────────────────────────────
Baseline (current)                  ████████████████████████████████████  133h

Win 1: Bigger GPU (0 code)          ██████████                            ~22h

Win 2: + Intra-parallel (30min)     ███████                               ~15h

Win 3: + Inter-parallel (1h)        ███                                   ~7h

Win 4: + Crash resilience (1h)      ███ (same speed, but safe)            ~7h

Win 5: + Skip HTML (30min)          ██▌                                   ~6h

Win 7: + vLLM batching (2h)         █▌                                    ~3h
```

**Total code effort for Wins 1-5:** ~3 hours of implementation for a **20x speedup** (133h → 6h).

**Recommended stopping point:** After Win 4 (crash resilience). At ~7h for 2000 customers, you can run the batch overnight. Win 7 (vLLM) is only worth it if you need to run batches multiple times per day.

---

## Current Architecture (What Exists Today)

### Entry Point: `batch_reports.py`
- Loops over CRNs sequentially
- For each CRN: calls `generate_combined_report_pdf(crn, save_intermediate=False)`
- After ALL CRNs complete: `merge_excel_reports()` reads all individual `reports/excel/{crn}.xlsx` files and concatenates them
- Resume mode: checks if `reports/excel/{crn}.xlsx` exists, skips if so
- **NEW (Phase 0):** Token usage auto-logged to `{output}.tokens.jsonl` + summary printed at end

### Per-Customer Orchestrator: `tools/combined_report.py` :: `generate_combined_report_pdf()`
Sequential steps (lines 26-186):
1. **Build banking data** (deterministic): `build_customer_report(customer_id)` — `pipeline/reports/customer_report_builder.py`
2. **LLM: Customer review** (885 in → 345 out): `generate_customer_review(report, rg_salary_data)` — only if >=10 transactions
3. **Build bureau data** (deterministic): `build_bureau_report(customer_id)` — `pipeline/reports/bureau_report_builder.py`
4. **LLM: Bureau review** (1,443 in → 257 out): `generate_bureau_review(executive_inputs, tradeline_features, monthly_exposure)`
5. **LLM: Combined summary** (1,613 in → 192 out): `generate_combined_executive_summary(banking_text, bureau_text, ...)` — DEPENDS ON steps 2 and 4
6. **Render HTML** (~0.5s): `render_combined_report()` via Jinja2 — `pipeline/renderers/combined_report_renderer.py`
7. **Export Excel row** (~0.1s): `build_excel_row()` + `export_row_to_excel()` → `reports/excel/{crn}.xlsx`

**Key insight:** Steps 1-2 (banking) and steps 3-4 (bureau) are COMPLETELY INDEPENDENT. Step 5 depends on both.

**Note:** `generate_customer_persona()` is NOT called in batch mode (`save_intermediate=False`). Only 3 LLM calls per customer, not 4.

### Excel Exporter: `tools/excel_exporter.py`
- 20 template columns defined in `TEMPLATE_COLUMNS` list (line 31-52)
- `build_excel_row()` (lines 59-268): manual mapping of each column with inline extraction logic
- `export_row_to_excel()` (line 275): writes one-row DataFrame to xlsx per customer
- `merge_excel_reports()` (line 300): reads ALL individual xlsx files, concatenates, writes master file

### LLM Calls: `pipeline/reports/report_summary_chain.py`
All 3 per-customer LLM calls are in this file. Each creates a new `ChatOllama` instance and calls `.invoke()` synchronously:
- `generate_customer_review()` — line ~56-97, uses `SUMMARY_MODEL`
- `generate_bureau_review()` — line ~928-965, uses `SUMMARY_MODEL`
- `generate_combined_executive_summary()` — line ~973-1022, uses `SUMMARY_MODEL`
- `summarize_exposure_timeline()` — DETERMINISTIC, no LLM (despite being in this file)

**All 4 functions now instrumented with `log_token_usage()`** — token counts, wall time, and throughput are automatically captured per call.

### Caching (all module-level, loaded once per process)
- `_transactions_df` in `data/loader.py` — banking transactions from `data/rgs.csv`
- `_bureau_df` in `pipeline/extractors/bureau_feature_extractor.py` — from `dpd_data.csv`
- `_tl_features_df` in `pipeline/extractors/tradeline_feature_extractor.py` — from `tl_features.csv`
- All read-only after initial load → thread-safe for parallel reads

### Data NOT Currently in Excel (but computed during HTML render)
- Scorecard: `compute_scorecard()` in `tools/scorecard.py` → verdict, signals, strengths, concerns
- Checklist: `compute_checklist()` in `pipeline/renderers/combined_report_renderer.py` → bureau + banking flags
- Persona: `compute_probable_persona()` in same file → profiles, stress flags, summary

---

## Phase 0: Token Usage Instrumentation (DONE)

**Status: IMPLEMENTED**

**Files modified:**
- `utils/llm_utils.py` — Added `log_token_usage()`, `get_token_summary()`, `print_token_summary()`, `set_token_log_file()`
- `pipeline/reports/report_summary_chain.py` — All 4 LLM functions instrumented with timing + token capture
- `batch_reports.py` — Auto-enables token JSONL logging alongside output Excel

**What it does:**
- Every LLM `chain.invoke()` call is timed and token-counted
- Extracts from `AIMessage.usage_metadata` (standard) and `response_metadata` (Ollama-specific `prompt_eval_count`/`eval_count`)
- Logs per-call: input_tokens, output_tokens, reasoning_tokens, wall_time_s, tokens_per_sec, model name
- Writes JSONL to `{output_excel}.tokens.jsonl` (e.g. `reports/batch_output.tokens.jsonl`)
- Prints summary table at batch end
- Thread-safe (uses `threading.Lock`)
- Model-agnostic: works with Ollama (ChatOllama), vLLM (ChatOpenAI), or any LangChain BaseChatModel

**Usage:**
```bash
# Batch run — token log is automatic
python batch_reports.py --crns 698167220 --output reports/test_batch.xlsx
# → creates reports/test_batch.tokens.jsonl + prints summary

# Programmatic access
from utils.llm_utils import get_token_summary, get_token_records
summary = get_token_summary()  # aggregated by label
records = get_token_records()  # raw per-call list
```

**Sample JSONL output:**
```json
{"timestamp": "2026-04-01T02:25:34", "label": "CustomerReview", "customer_id": 698167220, "model": "llama3.2", "input_tokens": 885, "output_tokens": 345, "reasoning_tokens": 0, "total_tokens": 1230, "wall_time_s": 19.9, "tokens_per_sec": 17.3}
{"timestamp": "2026-04-01T02:26:03", "label": "BureauReview", "customer_id": 698167220, "model": "llama3.2", "input_tokens": 1443, "output_tokens": 257, "reasoning_tokens": 0, "total_tokens": 1700, "wall_time_s": 29.02, "tokens_per_sec": 8.9}
{"timestamp": "2026-04-01T02:26:27", "label": "CombinedSummary", "customer_id": "###7220", "model": "llama3.2", "input_tokens": 1613, "output_tokens": 192, "reasoning_tokens": 0, "total_tokens": 1805, "wall_time_s": 24.15, "tokens_per_sec": 7.9}
```

---

## Phase 2: Column Registry for Excel (Start Here)

**Files to modify:** `tools/excel_exporter.py`

**What to do:**

1. Define a `RowContext` dataclass at module top holding all inputs that any column extractor might need:
   ```python
   @dataclass
   class RowContext:
       customer_id: int
       customer_report: Optional[CustomerReport]
       bureau_report: Optional[BureauReport]
       combined_summary: Optional[str]
       rg_salary_data: Optional[dict]
       exposure_summary: Optional[str]
       pdf_path: Optional[str]
   ```

2. Define `ColumnDef`:
   ```python
   @dataclass
   class ColumnDef:
       name: str
       extractor: Callable[[RowContext], Any]
       default: Any = None
   ```

3. Extract each column's logic from the current `build_excel_row()` into named functions. Example for salary:
   ```python
   def _extract_salary(ctx: RowContext) -> Optional[str]:
       # Current lines 97-115 of build_excel_row()
       salary_amount = None
       salary_company = None
       if ctx.rg_salary_data and ctx.rg_salary_data.get("rg_sal"):
           rg_sal = ctx.rg_salary_data["rg_sal"]
           salary_amount = rg_sal.get("salary_amount")
           salary_company = rg_sal.get("merchant")
       elif ctx.customer_report and ctx.customer_report.salary:
           salary_amount = ctx.customer_report.salary.avg_amount
           narration = ctx.customer_report.salary.narration or ""
           salary_company = narration.split()[0].title() if narration else None
       if salary_amount is not None and salary_company:
           return f"{salary_amount:,.0f} / {salary_company}"
       elif salary_amount is not None:
           return f"{salary_amount:,.0f}"
       return None
   ```

4. Build `COLUMN_REGISTRY` list with all 20 columns. Derive `TEMPLATE_COLUMNS = [col.name for col in COLUMN_REGISTRY]`.

5. Simplify `build_excel_row()`:
   ```python
   def build_excel_row(...) -> Dict[str, Any]:
       ctx = RowContext(customer_id, customer_report, bureau_report,
                        combined_summary, rg_salary_data, exposure_summary, pdf_path)
       return {col.name: _safe_extract(col, ctx) for col in COLUMN_REGISTRY}

   def _safe_extract(col: ColumnDef, ctx: RowContext) -> Any:
       try:
           return col.extractor(ctx)
       except Exception:
           return col.default
   ```

**Verify:** Run single customer batch, compare output Excel columns and values against current baseline.

---

## Phase 3: Incremental Excel Output

**Files to modify:** `tools/excel_exporter.py`, `tools/combined_report.py`, `batch_reports.py`

**What to do:**

### In `tools/excel_exporter.py`:
1. Add `append_row_to_csv(row, csv_path, lock=None)`:
   ```python
   def append_row_to_csv(row: Dict[str, Any], csv_path: str, lock=None) -> None:
       p = Path(csv_path)
       p.parent.mkdir(parents=True, exist_ok=True)
       write_header = not p.exists() or p.stat().st_size == 0
       ordered = {col: row.get(col) for col in TEMPLATE_COLUMNS}
       df = pd.DataFrame([ordered])
       if lock:
           lock.acquire()
       try:
           df.to_csv(csv_path, mode="a", header=write_header, index=False)
       finally:
           if lock:
               lock.release()
   ```

2. Add `csv_to_excel(csv_path, xlsx_path)`:
   ```python
   def csv_to_excel(csv_path: str, xlsx_path: str) -> str:
       df = pd.read_csv(csv_path)
       for col in TEMPLATE_COLUMNS:
           if col not in df.columns:
               df[col] = None
       df = df[TEMPLATE_COLUMNS]
       Path(xlsx_path).parent.mkdir(parents=True, exist_ok=True)
       df.to_excel(xlsx_path, index=False)
       return os.path.abspath(xlsx_path)
   ```

### In `tools/combined_report.py`:
- Remove the Excel export block (lines 168-183). The function should only return data — let the caller handle persistence.
- Instead, return `(customer_report, bureau_report, pdf_path, combined_summary, rg_salary_data, exposure_text)` — all data needed to build an Excel row externally.

### In `batch_reports.py`:
1. In `run_batch()`, create master CSV path: `reports/batch_progress.csv`
2. After each customer completes: call `build_excel_row()` then `append_row_to_csv(row, master_csv)`
3. At batch end: call `csv_to_excel(master_csv, output_excel)` to produce final xlsx
4. Update resume mode: read CRNs from `batch_progress.csv` column "CRN" instead of scanning `reports/excel/*.xlsx`
5. Keep backward compat: if `--legacy-resume` flag passed, use old per-file check

**Verify:** Run 3 CRNs, kill after 2, resume — verify 2 rows in CSV, resume picks up from 3rd.

---

## Phase 1: Intra-Customer Parallelism

**Files to modify:** `tools/combined_report.py`, `utils/llm_utils.py`

**What to do:**

### In `tools/combined_report.py`:
1. Extract banking branch (current lines 51-73) into:
   ```python
   def _build_and_review_banking(customer_id: int) -> Tuple[Optional[CustomerReport], Optional[dict]]:
       """Build CustomerReport + LLM review. Returns (report, rg_salary_data)."""
       from pipeline.reports.customer_report_builder import build_customer_report
       from pipeline.reports.report_summary_chain import generate_customer_review
       from data.loader import load_rg_salary_data
       customer_report = build_customer_report(customer_id)
       rg_salary_data = None
       try:
           rg_salary_data = load_rg_salary_data(customer_id) or None
       except Exception:
           pass
       if customer_report.meta.transaction_count >= 10:
           try:
               customer_report.customer_review = generate_customer_review(
                   customer_report, rg_salary_data=rg_salary_data)
           except Exception:
               pass
       return customer_report, rg_salary_data
   ```

2. Extract bureau branch (current lines 74-94) into:
   ```python
   def _build_and_review_bureau(customer_id: int) -> Optional[BureauReport]:
       """Build BureauReport + LLM narrative. Returns report."""
       from pipeline.reports.bureau_report_builder import build_bureau_report
       from pipeline.reports.report_summary_chain import generate_bureau_review
       bureau_report = build_bureau_report(customer_id)
       try:
           bureau_report.narrative = generate_bureau_review(
               bureau_report.executive_inputs,
               tradeline_features=bureau_report.tradeline_features,
               monthly_exposure=bureau_report.monthly_exposure,
               customer_id=customer_id)
       except Exception:
           pass
       return bureau_report
   ```

3. In `generate_combined_report_pdf()`, when `save_intermediate=False`:
   ```python
   from concurrent.futures import ThreadPoolExecutor
   with ThreadPoolExecutor(max_workers=2) as pool:
       banking_future = pool.submit(_build_and_review_banking, customer_id)
       bureau_future = pool.submit(_build_and_review_bureau, customer_id)
       customer_report, rg_salary_data = banking_future.result(timeout=120)
       bureau_report = bureau_future.result(timeout=120)
   # Combined summary still sequential (depends on both reviews)
   ```

4. Keep the `save_intermediate=True` path unchanged (used for single-customer interactive mode).

### In `utils/llm_utils.py`:
The `_token_log_lock` (threading.Lock) added in Phase 0 already protects the token log file and reasoning log writes from concurrent threads.

**Prerequisite:** Set `OLLAMA_NUM_PARALLEL=2` environment variable when starting Ollama.

**Expected savings:** Banking (build + LLM: ~28s) and Bureau (build + LLM: ~31s) run in parallel instead of serial → **saves ~28s per customer** (the shorter branch runs for free).

**Verify:** Run single CRN, check output matches baseline. Run 3 CRNs, check no corruption.

---

## Phase 4: Inter-Customer Parallelism (Worker Pool)

**Files to modify:** `batch_reports.py`, `config/settings.py`

**What to do:**

### In `config/settings.py`:
```python
BATCH_MAX_WORKERS = 2  # default conservative; increase with GPU capacity
```

### In `batch_reports.py`:
1. Add `--workers N` CLI argument (default from `BATCH_MAX_WORKERS`)
2. Extract single-customer processing into `_process_one_customer(crn)`:
   - Calls `generate_combined_report_pdf(crn, save_intermediate=False)`
   - Calls `build_excel_row()` with returned data
   - Returns the row dict (or None on failure)
3. Replace sequential loop with:
   ```python
   import threading
   from concurrent.futures import ThreadPoolExecutor, as_completed

   csv_lock = threading.Lock()
   with ThreadPoolExecutor(max_workers=args.workers) as pool:
       futures = {pool.submit(_process_one_customer, crn): crn for crn in crns}
       for future in as_completed(futures):
           crn = futures[future]
           try:
               row = future.result(timeout=180)
               if row:
                   append_row_to_csv(row, master_csv, lock=csv_lock)
                   succeeded += 1
               else:
                   failed += 1
           except Exception as exc:
               logger.error("CRN %s failed: %s", crn, exc)
               failed += 1
   ```

### GPU/SageMaker Scaling Guide

**Local Ollama:**

| GPU VRAM | Model | OLLAMA_NUM_PARALLEL | --workers | Effective LLM concurrency |
|---|---|---|---|---|
| 8GB | llama3.2 3B | 4 | 2 | 4 |
| 24GB | llama3.2 3B | 8 | 4 | 8 |
| 24GB | deepseek-r1 14B | 2 | 1 | 2 |
| 80GB A100 | deepseek-r1 14B | 4 | 2 | 4 |

**SageMaker (deepseek-r1 14B):**

| Instance | Max Concurrent Requests | --workers | Est. Per-Customer | Est. 2000 Customers |
|---|---|---|---|---|
| ml.g5.xlarge (1x A10G) | 2-4 | 1-2 | ~100s | ~28-56h |
| ml.g5.12xlarge (4x A10G) | 8-16 | 4-8 | ~30s eff. | ~8-17h |
| ml.p4d.24xlarge (8x A100) | 32+ | 8-16 | ~10s eff. | ~3-6h |

Rule of thumb: `--workers × 2 ≈ max concurrent LLM requests` (each worker uses 2 internal threads from Phase 1).

### Thread Safety (already verified)
- DataFrame caches (`_transactions_df`, `_bureau_df`) — read-only after first load, safe
- `ChatOllama` — new instance per call in `report_summary_chain.py`, no shared state
- CSV append — protected by `threading.Lock`
- Token log — protected by `_token_log_lock` (added in Phase 0)
- `_REPORT_CACHE` — not used in batch path (`save_intermediate=False`)

**Verify:** Run with `--workers 2` on 5 CRNs. Compare output to sequential run. Monitor with `nvidia-smi`.

---

## Phase 5: Reduce Intermediate I/O

**Files to modify:** `tools/combined_report.py`, `pipeline/renderers/combined_report_renderer.py`, `batch_reports.py`

**What to do:**

1. Add `--skip-html` flag to `batch_reports.py` — for runs that only need the Excel summary
2. Add `render_html=True` parameter to `generate_combined_report_pdf()`, passed through to `render_combined_report()`
3. In `render_combined_report()`: when `render_html=False`, skip Jinja2 rendering and file writes entirely, return empty string for path
4. Remove per-customer `.xlsx` file writes entirely (replaced by Phase 3's CSV append). Keep `export_row_to_excel()` available for single-customer interactive use.

**Verify:** Run with `--skip-html`, confirm Excel output is correct and no HTML files generated.

---

## Phase 6: vLLM / SageMaker Migration Path (for production scale)

**Files to modify:** `config/settings.py`, `pipeline/reports/report_summary_chain.py`

**What to do:**

### In `config/settings.py`:
```python
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")  # "ollama" or "vllm" or "sagemaker"
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
```

### In `pipeline/reports/report_summary_chain.py`:
1. Add factory function:
   ```python
   def _get_llm(model_name: str, temperature: float, seed: int = 42):
       from config.settings import LLM_BACKEND, VLLM_BASE_URL
       if LLM_BACKEND in ("vllm", "sagemaker"):
           from langchain_openai import ChatOpenAI
           return ChatOpenAI(base_url=VLLM_BASE_URL, model=model_name,
                             temperature=temperature)
       else:
           from langchain_ollama import ChatOllama
           thinking = is_thinking_model(model_name)
           return ChatOllama(model=model_name, temperature=temperature,
                             seed=seed, reasoning=thinking)
   ```
2. Replace the 3 `ChatOllama()` construction sites (lines ~50, 956, 1008) with `_get_llm()` calls
3. LCEL chains (`prompt | llm`) stay unchanged — `ChatOpenAI` and `ChatOllama` share the same `BaseChatModel` interface
4. Token instrumentation (`log_token_usage()`) already works with both backends — it reads from `usage_metadata` (standard) and `response_metadata` (Ollama fallback)

### Why vLLM / SageMaker
- Continuous batching: 8-16 concurrent requests processed in one GPU batch
- Same models (deepseek-r1 14B) via OpenAI-compatible API
- 8-10x throughput over Ollama for batch workloads
- **Token budget per 2000 customers:** ~3,941 × 2000 = **~7.9M input + ~1.6M output = ~9.5M total tokens** (without reasoning), or **~13M tokens** with deepseek reasoning overhead

**Verify:** Start vLLM server, set `LLM_BACKEND=vllm`, run single CRN, compare output quality to Ollama baseline. Check token JSONL includes reasoning token counts.

---

## Implementation Order & Dependencies

```
Phase 0 (token instrumentation) ── DONE
        │
Phase 2 (column registry) ─→ Phase 3 (incremental CSV) ─→ Phase 4 (inter-parallel)
                                                              ↑
Phase 1 (intra-parallel) ────────────────────────────────────┘
                                                              ↓
                                                         Phase 5 (reduce I/O)

Phase 6 (vLLM/SageMaker) ──────── independent, any time
```

**Recommended sequence:** 0 (done) → 2 → 3 → 1 → 4 → 5 → 6

---

## Projected Throughput (2000 customers)

### With llama3.2 3B (local Ollama) — measured baseline

| Configuration | Per Customer | Total | Speedup |
|---|---|---|---|
| Current (serial, 3 LLM) | ~76s (measured) | ~42h | 1x |
| + Phase 1 (intra-parallel) | ~48s | ~27h | 1.6x |
| + Phase 4 (2 workers, 8GB GPU) | ~24s eff. | ~13h | 3.2x |
| + Phase 4 (4 workers, 24GB GPU) | ~12s eff. | ~6.7h | 6.3x |
| + Phase 5 (skip HTML) | ~11s eff. | ~6.1h | 6.9x |

### With deepseek-r1 14B (SageMaker) — estimated

| Configuration | Per Customer | Total | Speedup vs serial |
|---|---|---|---|
| Current (serial, 3 LLM, 1 instance) | ~240s (4min) | ~133h | 1x |
| + Phase 1 (intra-parallel) | ~160s | ~89h | 1.5x |
| + Phase 4 (4 workers, 4x A10G) | ~40s eff. | ~22h | 6x |
| + Phase 6 (vLLM continuous batch) | ~15s eff. | ~8h | 17x |
| + Phase 5 (skip HTML) | ~13s eff. | ~7h | 19x |

---

## Top 5 Optimization Targets (by measured impact)

1. **LLM inference (3 chains in sequence) — 73s/76s = 96%**
   - CustomerReview: 19.9s (885 in → 345 out)
   - BureauReview: 29.0s (1,443 in → 257 out)
   - CombinedSummary: 24.2s (1,613 in → 192 out)
   - **Phase 1 saves ~28s** by parallelizing CustomerReview + BureauReview
   - **Phase 4+6 saves more** via inter-customer parallelism + continuous batching

2. **Merchant feature computation with fuzzy matching — 15-25s (heavy-txn customers)**
   - `compute_all_merchant_features()` → `_group_by_merchant()` with O(n*m) fuzzy matching
   - Not a factor for 21-txn test customer, but dominates for 100+ txn customers

3. **Kotak loan default checklist check — 1-3s**
   - Re-loads dpd_data.csv in `compute_checklist()`
   - Should reuse cached bureau data

4. **Bureau feature extraction — 2-10s**
   - First load of dpd_data.csv + feature vector computation
   - Cached after first customer in batch

5. **Excel/HTML rendering — 3s**
   - Phase 5 eliminates HTML when not needed

---

## Critical Files Reference

| File | Lines | Role in optimization |
|---|---|---|
| `utils/llm_utils.py` | ~340 | Phase 0 (token instrumentation — DONE), Phase 1 (thread-safe locks). |
| `pipeline/reports/report_summary_chain.py` | ~1050 | Phase 0 (instrumented — DONE), Phase 6 (LLM factory). All 3 batch LLM calls. |
| `batch_reports.py` | ~175 | Phase 0 (token logging — DONE), Phase 3 (incremental CSV), Phase 4 (worker pool), Phase 5 (--skip-html). |
| `tools/excel_exporter.py` | ~335 | Phase 2 (column registry), Phase 3 (CSV append). Row building + persistence. |
| `tools/combined_report.py` | 186 | Phase 1 (ThreadPool), Phase 5 (skip-html). Core orchestrator per customer. |
| `config/settings.py` | — | Phase 4 (BATCH_MAX_WORKERS), Phase 6 (LLM_BACKEND, VLLM_BASE_URL). |
| `pipeline/renderers/combined_report_renderer.py` | ~1400 | Phase 5 (render_html flag). HTML rendering + checklist + persona. |
