# Batch Report Stamping — Performance Optimization Research

> **Classification:** Performance Engineering Research
> **Scope:** Optimize combined report generation for batch stamping (100–1000+ customers)
> **Focus:** LLM bottleneck mitigation, parallelization strategies, model trade-offs

---

## Table of Contents

1. [Current Bottleneck Analysis](#1-current-bottleneck-analysis)
2. [LLM Call Inventory — The Real Cost](#2-llm-call-inventory--the-real-cost)
3. [Optimization Strategies (Easy → Deep)](#3-optimization-strategies-easy--deep)
4. [Strategy 1 — Kill the Report Planner LLM Call](#4-strategy-1--kill-the-report-planner-llm-call)
5. [Strategy 2 — Parallel Customer + Bureau Reports](#5-strategy-2--parallel-customer--bureau-reports)
6. [Strategy 3 — Parallel LLM Calls Within Each Report](#6-strategy-3--parallel-llm-calls-within-each-report)
7. [Strategy 4 — Model Selection Matrix](#7-strategy-4--model-selection-matrix)
8. [Strategy 5 — Batch LLM Prompting](#8-strategy-5--batch-llm-prompting)
9. [Strategy 6 — Skip Optional Narratives](#9-strategy-6--skip-optional-narratives)
10. [Strategy 7 — Ollama Concurrency Tuning](#10-strategy-7--ollama-concurrency-tuning)
11. [Strategy 8 — Pre-Compute and Cache Deterministic Data](#11-strategy-8--pre-compute-and-cache-deterministic-data)
12. [Strategy 9 — Template-Based Narrative (Zero LLM)](#12-strategy-9--template-based-narrative-zero-llm)
13. [Strategy 10 — GPU/Infrastructure Optimization](#13-strategy-10--gpuinfrastructure-optimization)
14. [Combined Impact Estimates](#14-combined-impact-estimates)
15. [Recommended Implementation Order](#15-recommended-implementation-order)
16. [DeepSeek-R1 Specific Concerns](#16-deepseek-r1-specific-concerns)

---

## 1. Current Bottleneck Analysis

### Per-Customer Combined Report — Current Call Chain

```
generate_combined_report_pdf(customer_id)
│
├─ [SEQ] generate_customer_report_pdf()           ~8-15s total
│   ├─ _build_report_with_planner()
│   │   ├─ build_data_profile()                    ~20ms   (deterministic)
│   │   ├─ ReportPlanner.plan()                    ~1-3s   ◀ LLM CALL #1 (mistral)
│   │   ├─ execute_section() × 6-8 sections        ~100ms  (deterministic)
│   │   ├─ compute_account_quality()               ~15ms   (deterministic)
│   │   └─ detect_events()                         ~50ms   (deterministic)
│   │
│   ├─ load_rg_salary_data()                       ~10ms   (file I/O, cached)
│   ├─ generate_customer_persona()                 ~2-5s   ◀ LLM CALL #2 (SUMMARY_MODEL)
│   ├─ generate_customer_review()                  ~2-5s   ◀ LLM CALL #3 (SUMMARY_MODEL)
│   ├─ extract_tradeline_features()                ~5ms    (file I/O, cached)
│   └─ render_report_pdf()                         ~100ms  (CPU, no LLM)
│
├─ [SEQ] generate_bureau_report_pdf()              ~3-8s total
│   ├─ build_bureau_report()                       ~80ms   (deterministic)
│   │   ├─ extract_bureau_features()               ~30ms
│   │   ├─ aggregate_bureau_features()             ~1ms
│   │   ├─ extract_tradeline_features()            ~5ms    (cached)
│   │   ├─ extract_key_findings()                  ~20ms
│   │   └─ compute_monthly_exposure()              ~20ms
│   │
│   ├─ generate_bureau_review()                    ~2-5s   ◀ LLM CALL #4 (SUMMARY_MODEL)
│   └─ render_bureau_report_pdf()                  ~100ms  (CPU, no LLM)
│
├─ [SEQ] generate_combined_executive_summary()     ~2-5s   ◀ LLM CALL #5 (SUMMARY_MODEL)
│
├─ [SEQ] load_rg_salary_data()                     ~1ms    (cached)
├─ [SEQ] render_combined_report()                  ~200ms  (CPU, no LLM)
└─ [SEQ] export_row_to_excel()                     ~50ms   (I/O)
```

### Time Breakdown per Customer

| Component | Time (llama3.2) | Time (deepseek-r1:14b) | % of Total |
|---|---|---|---|
| LLM #1: Report planner | 1-3s | 3-8s | 10-15% |
| LLM #2: Customer persona | 2-5s | 5-15s | 15-20% |
| LLM #3: Customer review | 2-5s | 5-15s | 15-20% |
| LLM #4: Bureau review | 2-5s | 5-15s | 15-20% |
| LLM #5: Combined summary | 2-5s | 5-15s | 15-20% |
| Deterministic computation | ~0.5s | ~0.5s | 3-5% |
| PDF/HTML rendering | ~0.4s | ~0.4s | 2-3% |
| File I/O | ~0.1s | ~0.1s | <1% |
| **TOTAL per customer** | **~10-25s** | **~25-70s** | **100%** |

### Batch Projections (Current Sequential)

| Customers | llama3.2 | deepseek-r1:14b |
|---|---|---|
| 10 | 2-4 min | 4-12 min |
| 50 | 8-20 min | 20-58 min |
| 100 | 17-42 min | 42-117 min |
| 500 | 83-208 min | 208-583 min |
| 1000 | 167-417 min | 417-1167 min |

**The problem is clear: LLM calls are 90-95% of total time. With deepseek-r1:14b, batch processing is 2.5-3x slower than llama3.2.**

---

## 2. LLM Call Inventory — The Real Cost

### Per Customer: 5 Sequential LLM Calls

```
CALL #1  ReportPlanner.plan()             → mistral (JSON, fast)
         Purpose: Decide which sections to include
         Input:   ~200 chars (data profile)
         Output:  ~300 chars (JSON plan)
         VERDICT: UNNECESSARY — default plan covers 95% of cases

CALL #2  generate_customer_persona()      → SUMMARY_MODEL
         Purpose: 4-5 line lifestyle description
         Input:   ~1500 chars (comprehensive data + 20 txn sample)
         Output:  ~400 chars
         VERDICT: NICE-TO-HAVE — can be skipped in batch mode

CALL #3  generate_customer_review()       → SUMMARY_MODEL
         Purpose: 2-paragraph executive summary
         Input:   ~800 chars (data summary + events)
         Output:  ~600 chars
         VERDICT: ESSENTIAL — core value of the report

CALL #4  generate_bureau_review()         → SUMMARY_MODEL
         Purpose: 2-paragraph bureau narrative
         Input:   ~1500 chars (portfolio + behavioral features)
         Output:  ~600 chars
         VERDICT: ESSENTIAL — core value of the report

CALL #5  generate_combined_executive_summary() → SUMMARY_MODEL
         Purpose: Synthesized 2-paragraph merged summary
         Input:   ~1200 chars (banking + bureau text)
         Output:  ~500 chars
         VERDICT: ESSENTIAL for combined reports, but DERIVABLE
```

### Token Economics (deepseek-r1:14b)

deepseek-r1 generates a `<think>` block BEFORE the answer. This thinking block is:
- **Stripped and discarded** by `strip_think()` — the user never sees it
- Typically **2-5x longer** than the actual output
- **100% wasted compute** from a batch performance perspective

```
Without <think>:   input ~1000 tokens + output ~200 tokens = ~1200 tokens
With <think>:      input ~1000 tokens + output ~800 tokens (600 think + 200 answer)
                   = ~1800 tokens = 50% MORE compute for ZERO additional output value
```

For batch processing, the `<think>` block is pure overhead. The quality gain from reasoning may not justify the 2.5-3x slowdown.

---

## 3. Optimization Strategies (Easy → Deep)

| # | Strategy | Effort | Impact | Works With deepseek? |
|---|---|---|---|---|
| 1 | Kill the report planner LLM call | 30 min | -20% time | Yes |
| 2 | Parallel customer + bureau reports | 2 hrs | -30% time | Yes |
| 3 | Parallel LLM calls within report | 3 hrs | -25% time | Yes |
| 4 | Model selection matrix | 1 hr | -50-70% time | Replaces deepseek |
| 5 | Batch LLM prompting | 4 hrs | -40% time | Yes |
| 6 | Skip optional narratives | 30 min | -30% time | Yes |
| 7 | Ollama concurrency tuning | 1 hr | -20-40% time | Yes |
| 8 | Pre-compute deterministic data | 3 hrs | -5% time + enables other strategies | Yes |
| 9 | Template-based narrative | 1 day | -100% LLM time | Eliminates LLM |
| 10 | GPU/infrastructure | Varies | -50-80% time | Yes |

---

## 4. Strategy 1 — Kill the Report Planner LLM Call

### The Problem

`ReportPlanner.plan()` calls `mistral` to decide which sections to include. But the `_default_plan()` fallback already handles this perfectly — it checks `has_salary`, `has_emi`, `has_rent`, etc. and includes sections based on data availability.

The LLM adds nothing here. The decision is purely data-availability driven.

### Current Code Path

```python
# report_orchestrator.py, line 96-98
if use_planner:
    report = _build_report_with_planner(customer_id, months)  # ← 1 LLM call
else:
    report = build_customer_report(customer_id, months)        # ← 0 LLM calls
```

### The Fix

```python
# Option A: Pass use_planner=False (zero code change)
generate_customer_report_pdf(customer_id, use_planner=False)

# Option B: Add batch mode flag to settings.py
BATCH_MODE = True  # Skip LLM planner in batch

# Option C: Just use the default plan always (remove LLM planner)
```

### Impact

- **Saves:** 1-3s per customer (mistral) or 3-8s (if deepseek were used)
- **Risk:** Zero — the default plan is comprehensive
- **Effort:** 30 minutes (1 line change or settings flag)

---

## 5. Strategy 2 — Parallel Customer + Bureau Reports

### The Problem

`generate_combined_report_pdf()` calls customer and bureau reports **sequentially**:

```python
# combined_report.py, lines 48-58
customer_report, _ = generate_customer_report_pdf(customer_id)  # ~8-15s
bureau_report, _ = generate_bureau_report_pdf(customer_id)      # ~3-8s
# Total: 11-23s sequential
```

These are **completely independent** — they use different data sources (rgs.csv vs dpd_data.csv) and different LLM calls.

### The Fix

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

def generate_combined_report_pdf(customer_id: int, theme: str = "original"):
    # Run both report generations in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        customer_future = pool.submit(generate_customer_report_pdf, customer_id)
        bureau_future = pool.submit(generate_bureau_report_pdf, customer_id)

        customer_report, _ = customer_future.result()
        bureau_report, _ = bureau_future.result()

    # Combined summary still sequential (needs both reports)
    combined_summary = generate_combined_executive_summary(...)
    ...
```

### Impact

- **Saves:** ~3-8s per customer (bureau runs in parallel with customer)
- **Before:** customer(10s) + bureau(5s) + combined(3s) = 18s
- **After:** max(customer, bureau)(10s) + combined(3s) = 13s → **28% faster**
- **Risk:** Low — both reports are independent. Ollama handles concurrent requests.
- **Effort:** 2 hours (thread pool + error handling)

### Caveat: Ollama Single-GPU Serialization

If Ollama is running on a single GPU, concurrent LLM calls are **queued internally** by Ollama. The parallelism helps with the deterministic parts overlapping, but the LLM calls still serialize at the GPU level.

Real benefit comes when combined with Strategy 7 (Ollama concurrency tuning) or Strategy 10 (multiple GPU).

---

## 6. Strategy 3 — Parallel LLM Calls Within Each Report

### The Problem

Customer report makes 2 sequential LLM calls that are independent:

```python
# report_orchestrator.py, lines 118-128
report.customer_persona = generate_customer_persona(report)  # ~2-5s, reads report
report.customer_review = generate_customer_review(report)    # ~2-5s, reads report
# Total: 4-10s sequential
```

Both read from the same `CustomerReport` object (read-only). They can run in parallel.

### The Fix

```python
from concurrent.futures import ThreadPoolExecutor

# In generate_customer_report_pdf():
if include_summary and report.meta.transaction_count >= 10:
    with ThreadPoolExecutor(max_workers=2) as pool:
        persona_future = pool.submit(generate_customer_persona, report)
        review_future = pool.submit(
            generate_customer_review, report, rg_salary_data=rg_salary_data
        )

        try:
            report.customer_persona = persona_future.result(timeout=30)
        except Exception as e:
            logger.warning("Persona failed: %s", e)

        try:
            report.customer_review = review_future.result(timeout=30)
        except Exception as e:
            logger.warning("Review failed: %s", e)
```

### Impact

- **Saves:** 2-5s per customer (persona runs in parallel with review)
- **Same Ollama caveat:** GPU-level serialization may limit real gain to deterministic overlap only
- **Effort:** 3 hours (thread pool + timeout + error handling in both orchestrators)

---

## 7. Strategy 4 — Model Selection Matrix

### The Core Trade-off

```
                     Quality
                       ▲
deepseek-r1:14b   ●   │
                       │
llama3.2          ●    │
                       │
mistral (7B)      ●    │
                       │
phi4-mini              │  ●
                       │
                       └──────────────────► Speed
```

### Model Options for SUMMARY_MODEL

| Model | Size | Think Block? | Quality | Speed (est.) | Batch 100 |
|---|---|---|---|---|---|
| **deepseek-r1:14b** | 14B | Yes (2-5x overhead) | Excellent | ~5-15s/call | 42-125 min |
| **llama3.2** (current) | 3B | No | Good | ~2-5s/call | 17-42 min |
| **mistral** | 7B | No | Good (JSON-tuned) | ~1-3s/call | 8-25 min |
| **phi4-mini** | 3.8B | No | Good | ~1-3s/call | 8-25 min |
| **llama3.1:8b** | 8B | No | Very Good | ~3-7s/call | 25-58 min |
| **qwen2.5:7b** | 7B | No | Very Good | ~2-5s/call | 17-42 min |
| **gemma2:9b** | 9B | No | Very Good | ~3-7s/call | 25-58 min |

### The DeepSeek-R1 Problem for Batch

deepseek-r1:14b generates a `<think>` block that is:
1. **Always generated** — can't disable it
2. **Always stripped** — `strip_think()` removes it before output
3. **Doubles token generation** — 600 think tokens + 200 answer tokens vs 200 answer tokens
4. **14B parameters** — 2x memory and compute vs 7B models

**For batch stamping, deepseek-r1 is the worst choice.** The think block provides quality that's invisible in structured report summaries where the input data is pre-annotated with risk tags.

### Recommendation: Tiered Model Strategy

```python
# config/settings.py

# Interactive (single report, user is waiting):
SUMMARY_MODEL_INTERACTIVE = "deepseek-r1:14b"   # Quality matters, user waits

# Batch (stamping 100s of reports):
SUMMARY_MODEL_BATCH = "llama3.2"                 # Speed matters, quality is good enough
# Or even faster:
# SUMMARY_MODEL_BATCH = "mistral"                # Fastest, still adequate for summaries

# In batch_reports.py:
import config.settings as settings
settings.SUMMARY_MODEL = settings.SUMMARY_MODEL_BATCH
```

### Impact

- Switching from `deepseek-r1:14b` to `llama3.2`: **~2.5-3x faster**
- Switching from `deepseek-r1:14b` to `mistral`: **~4-5x faster**
- **Risk:** Slightly lower narrative quality (but prompts are highly structured — input is pre-annotated with tags like `[HIGH RISK]`, `[POSITIVE]`, so the LLM mostly arranges pre-computed findings into sentences)
- **Effort:** 1 hour (add batch model setting + wire it through)

---

## 8. Strategy 5 — Batch LLM Prompting

### The Idea

Instead of 1 LLM call per customer per narrative, batch multiple customers into one prompt.

### Option A: Multi-Customer Persona in One Call

```python
BATCH_PERSONA_PROMPT = """Generate 4-5 line personas for each of the following customers.
Output as JSON: {{"customer_<id>": "<persona text>", ...}}

{batch_data}
"""

# Batch 5 customers into one call
batch_data = "\n---\n".join(
    f"CUSTOMER {cid}:\n{_build_comprehensive_data(reports[cid])}"
    for cid in batch_group
)
```

### Option B: Combined Review + Persona in One Call

Instead of 2 separate LLM calls (persona + review) per customer, combine them:

```python
COMBINED_GENERATION_PROMPT = """Generate BOTH a customer review AND persona for this customer.

{data_summary}

Output as JSON:
{{"review": "<2 paragraph review>", "persona": "<4-5 line persona>"}}
"""
```

**This halves the LLM calls per customer from 2 to 1.**

### Impact

- Option A: **-60-80%** LLM calls (batch 5 customers = 1 call instead of 5)
- Option B: **-50%** LLM calls per customer report (2 calls → 1)
- **Risk:** Option A — longer prompts may degrade quality. Option B — low risk, same data.
- **Effort:** 4 hours (prompt engineering + JSON parsing + error handling)

### Caveat

Batching multiple customers in one prompt works best with larger models (8B+) that handle longer contexts. With 3B models, context window limitations may cause quality degradation.

---

## 9. Strategy 6 — Skip Optional Narratives

### What's Optional?

| Narrative | Essential? | Skip Impact |
|---|---|---|
| Customer persona | No — lifestyle description, nice-to-have | Report works without it |
| Customer review | **Yes** — core executive summary | Cannot skip |
| Bureau review | **Yes** — core bureau narrative | Cannot skip |
| Combined summary | Depends — synthesis of the above two | Can be derived differently |

### Batch Mode: Skip Persona

```python
# report_orchestrator.py
def generate_customer_report_pdf(
    customer_id, months=6, include_summary=True,
    skip_persona=False,  # NEW flag
    ...
):
    if include_summary and report.meta.transaction_count >= 10:
        if not skip_persona:
            report.customer_persona = generate_customer_persona(report)
        report.customer_review = generate_customer_review(report, ...)
```

### Batch Mode: Template Combined Summary

Instead of an LLM call for the combined summary, concatenate the banking and bureau reviews:

```python
def template_combined_summary(banking_review: str, bureau_review: str) -> str:
    """Deterministic combined summary — no LLM call."""
    return f"{banking_review}\n\n{bureau_review}"
```

This is crude but for batch stamping, the individual reviews already contain all the information.

### Impact

- Skip persona: **-1 LLM call** per customer (~2-5s saved with llama3.2, ~5-15s with deepseek)
- Template combined: **-1 LLM call** per customer
- **Total: -2 LLM calls = 40% fewer LLM calls**
- **Risk:** Persona loss is cosmetic. Template combined loses synthesis quality.
- **Effort:** 30 minutes each

---

## 10. Strategy 7 — Ollama Concurrency Tuning

### The Problem

Ollama defaults to **serial execution** — one inference at a time per model. When Strategy 2 or 3 sends concurrent requests, Ollama queues them.

### Ollama Environment Variables

```bash
# Allow parallel model instances (uses more VRAM)
OLLAMA_NUM_PARALLEL=2    # Process 2 requests simultaneously per model
                          # Requires ~2x VRAM for the model

# Keep model in memory between calls (avoid cold start)
OLLAMA_KEEP_ALIVE=60m    # Keep model loaded for 60 min

# For multiple different models loaded simultaneously
OLLAMA_MAX_LOADED_MODELS=2  # Keep both mistral + SUMMARY_MODEL in VRAM
```

### Starting Ollama with Concurrency

```bash
OLLAMA_NUM_PARALLEL=2 OLLAMA_KEEP_ALIVE=60m ollama serve
```

### Impact with `OLLAMA_NUM_PARALLEL=2`

- Strategy 2 (parallel reports) actually achieves real parallelism
- Strategy 3 (parallel persona + review) actually runs concurrently
- **Effective speedup:** ~1.5-1.8x (not 2x due to shared GPU bandwidth)
- **Requirement:** ~2x VRAM. For deepseek-r1:14b (~10GB), you need ~20GB VRAM
- **For llama3.2 (3B, ~2GB):** easily fits 2 parallel instances

### Ollama Batch API (Future)

Ollama doesn't currently have a native batch API, but there's an open issue for it. When available, this would be the optimal path for batch processing.

---

## 11. Strategy 8 — Pre-Compute and Cache Deterministic Data

### The Idea

Separate batch processing into two phases:

```
Phase 1: DETERMINISTIC (no LLM, fast, parallelizable)
    ├─ Build all CustomerReports (deterministic sections only)
    ├─ Build all BureauReports (deterministic)
    ├─ Extract all tradeline features
    ├─ Compute all scorecards
    ├─ Detect all events
    └─ Compute all account quality scores

Phase 2: LLM NARRATIVE (slow, sequential or batched)
    ├─ Generate customer reviews (essential)
    ├─ Generate bureau reviews (essential)
    └─ Generate combined summaries (optional)

Phase 3: RENDER (fast, parallelizable)
    ├─ Render all PDFs
    ├─ Render all HTMLs
    └─ Export Excel rows
```

### Why This Matters

Phase 1 takes ~0.5s per customer and is **trivially parallelizable** with `ProcessPoolExecutor`:

```python
from concurrent.futures import ProcessPoolExecutor

def phase1_deterministic(crns: list) -> dict:
    """Pre-compute all deterministic data in parallel."""
    with ProcessPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_build_single_customer_data, crns))
    return {crn: data for crn, data in zip(crns, results)}

# 1000 customers × 0.5s / 8 workers = ~62s for ALL deterministic work
```

Phase 2 is the bottleneck. By separating it, you can:
1. Apply model selection (Strategy 4) only to Phase 2
2. Skip optional narratives (Strategy 6)
3. Batch prompts (Strategy 5)
4. Retry failed LLM calls without re-computing data

### Impact

- Deterministic data for 1000 customers: **~1 minute** (parallel)
- Enables all other LLM strategies by decoupling data from narrative
- **Effort:** 3 hours (refactor orchestrator into phases)

---

## 12. Strategy 9 — Template-Based Narrative (Zero LLM)

### The Nuclear Option

For maximum batch speed, replace LLM narrative entirely with deterministic template generation.

### How It Would Work

The prompts already provide heavily structured, pre-annotated data to the LLM. The LLM mostly rearranges this into paragraphs. A template engine can do the same:

```python
def template_customer_review(report: CustomerReport, rg_salary_data: dict = None) -> str:
    """Generate customer review from templates — zero LLM calls."""
    sections = _build_data_summary(report, rg_salary_data=rg_salary_data)

    # Paragraph 1: Financial Overview
    para1_parts = []
    if report.salary:
        para1_parts.append(
            f"Customer ###... receives a monthly salary of INR {report.salary.avg_amount:,.0f}"
        )
    if report.monthly_cashflow:
        total_in = sum(m.get('inflow', 0) for m in report.monthly_cashflow)
        total_out = sum(m.get('outflow', 0) for m in report.monthly_cashflow)
        para1_parts.append(
            f"with total inflows of INR {total_in:,.0f} against outflows of INR {total_out:,.0f}"
        )
    # ... etc for EMI, rent, top categories

    # Paragraph 2: Events
    para2_parts = []
    if report.events:
        for event in report.events:
            sig = event.get("significance", "medium").upper()
            para2_parts.append(f"[{sig}] {event.get('label', event.get('type', 'Unknown'))}")

    return f"{'. '.join(para1_parts)}.\n\n{'  '.join(para2_parts)}"
```

### Quality Comparison

| Aspect | LLM Narrative | Template Narrative |
|---|---|---|
| Prose quality | Natural, flowing | Mechanical, formulaic |
| Factual accuracy | 99% (occasionally hallucinates) | 100% (deterministic) |
| Speed | 2-15s per call | <1ms |
| Consistency | Variable across runs | Identical across runs |
| Auditability | LLM is a black box | Fully traceable |

### Hybrid Approach

Use templates for batch, LLM for interactive:

```python
def generate_customer_review(report, *, batch_mode=False, **kwargs):
    if batch_mode:
        return template_customer_review(report, **kwargs)
    return _llm_customer_review(report, **kwargs)
```

### Impact

- **Eliminates ALL LLM calls** — combined report goes from 25-70s to ~1s
- Batch 1000 customers: from 42-125 min to **~10 min** (just deterministic + rendering)
- **Risk:** Reports read like form letters. Fine for internal batch audit. Not suitable for customer-facing output.
- **Effort:** 1 day (template development for 3 narratives)

---

## 13. Strategy 10 — GPU/Infrastructure Optimization

### Current Constraint

Single Ollama instance on a single GPU. All LLM calls serialize at the GPU level.

### Option A: Multiple Ollama Instances (Multiple GPUs)

```bash
# GPU 0: Handle customer persona + review
CUDA_VISIBLE_DEVICES=0 ollama serve --port 11434

# GPU 1: Handle bureau review + combined summary
CUDA_VISIBLE_DEVICES=1 ollama serve --port 11435
```

```python
# In code: route calls to different Ollama instances
CUSTOMER_LLM = ChatOllama(base_url="http://localhost:11434", model=SUMMARY_MODEL)
BUREAU_LLM = ChatOllama(base_url="http://localhost:11435", model=SUMMARY_MODEL)
```

### Option B: vLLM Instead of Ollama

vLLM is optimized for throughput (continuous batching, PagedAttention):

```bash
python -m vllm.entrypoints.openai.api_server \
    --model deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

**Key advantage:** vLLM batches concurrent requests at the GPU level automatically. No need for `OLLAMA_NUM_PARALLEL` — it's native.

**Typical speedup:** 2-5x over Ollama for batch workloads.

### Option C: Quantization

Smaller quantized models run faster with minor quality loss:

| Model | Quant | VRAM | Speed (relative) |
|---|---|---|---|
| deepseek-r1:14b | Q4_K_M (default) | ~10GB | 1x |
| deepseek-r1:14b | Q3_K_S | ~7GB | 1.3x |
| llama3.2:3b | Q4_K_M | ~2GB | 4-5x |
| llama3.2:3b | Q8_0 | ~3.5GB | 3-4x (better quality) |

### Impact

- Multi-GPU: **~2x speedup** per additional GPU
- vLLM: **~2-5x speedup** over Ollama for batch
- Quantization: **~1.3x speedup** with minor quality loss
- **Effort:** Option A: 2 hours. Option B: 1 day (migration). Option C: 30 min.

---

## 14. Combined Impact Estimates

### Scenario: 100 Customers, deepseek-r1:14b Baseline

| Optimization | Time | Speedup | Cumulative |
|---|---|---|---|
| **Baseline** (current sequential) | ~95 min | 1x | — |
| + Strategy 1 (kill planner) | ~80 min | 1.2x | 1.2x |
| + Strategy 6 (skip persona + template combined) | ~50 min | 1.6x | 1.9x |
| + Strategy 4 (switch to llama3.2 for batch) | ~20 min | 2.5x | 4.8x |
| + Strategy 2 (parallel customer + bureau) | ~14 min | 1.4x | 6.8x |
| + Strategy 7 (Ollama NUM_PARALLEL=2) | ~10 min | 1.4x | 9.5x |
| + Strategy 5 (combined review+persona prompt) | ~8 min | 1.25x | 11.9x |

**From 95 minutes to 8 minutes = ~12x speedup**

### Scenario: 100 Customers, Maximum Speed (Template Mode)

| Optimization | Time | Speedup |
|---|---|---|
| Strategy 9 (zero LLM) + Strategy 8 (parallel deterministic) | ~2 min | **48x** |

### Scenario: 1000 Customers

| Approach | Time |
|---|---|
| Current (deepseek-r1, sequential) | ~16 hours |
| Optimized (llama3.2, parallel, skip optional) | ~80 min |
| Maximum (template, parallel deterministic) | ~15 min |

---

## 15. Recommended Implementation Order

### Week 1 — Easy Kills (3-5 hours total)

```
Priority 1: Strategy 1 — Kill report planner LLM call
            → 1 line: use_planner=False in batch_reports.py
            → Impact: -10-15%

Priority 2: Strategy 6 — Skip persona in batch, template combined
            → Add skip_persona flag to orchestrator
            → Impact: -30-40% LLM calls

Priority 3: Strategy 4 — Model selection for batch
            → Add SUMMARY_MODEL_BATCH = "llama3.2" to settings
            → Override in batch_reports.py
            → Impact: -50-70% if switching from deepseek-r1

Priority 4: Strategy 7 — Ollama concurrency
            → Set OLLAMA_NUM_PARALLEL=2 + OLLAMA_KEEP_ALIVE=60m
            → Impact: -20-40% with parallel strategies
```

**Combined Week 1 impact: 5-8x faster batch processing**

### Week 2 — Structural (1-2 days)

```
Priority 5: Strategy 2 — Parallel customer + bureau
            → ThreadPoolExecutor in combined_report.py
            → Impact: -28% time

Priority 6: Strategy 3 — Parallel persona + review
            → ThreadPoolExecutor in report_orchestrator.py
            → Impact: -25% per customer report

Priority 7: Strategy 8 — Phase separation
            → Refactor batch_reports.py into 3 phases
            → Enables smarter retry, progress tracking
```

### Week 3 — Advanced (2-3 days)

```
Priority 8: Strategy 5 — Combined review+persona prompt
            → Single LLM call for both outputs
            → Impact: -50% customer report LLM calls

Priority 9: Strategy 9 — Template narratives (optional)
            → For maximum batch speed, zero LLM
            → Only if batch quality requirements are low
```

### Later — Infrastructure

```
Priority 10: Strategy 10 — vLLM / multi-GPU
             → When batch volumes exceed 500+ customers regularly
```

---

## 16. DeepSeek-R1 Specific Concerns

### Why DeepSeek-R1 Is Especially Slow for Batch

1. **Think Block Tax:** Every call generates 200-600 tokens of `<think>` content that is immediately discarded. For 5 calls per customer × 1000 customers = 5000 think blocks generated and thrown away.

2. **14B Parameters:** 2x the compute of 7B models per token. Combined with think blocks, effective cost is ~4x a 7B model.

3. **No Batch Optimization:** The think block can't be disabled. Even with prompt engineering like "Do not show your reasoning", the model still generates `<think>` internally.

4. **Diminishing Returns for Pre-Annotated Data:** The system already pre-computes risk tags (`[HIGH RISK]`, `[POSITIVE]`, `[CONCERN]`), interaction signals, and composite findings. The LLM's job is **arrangement, not analysis**. A reasoning model's strength (deep analysis) is wasted when the analysis is already done.

### When DeepSeek-R1 IS Worth It

- **Interactive single reports** where a user is waiting and quality matters
- **Combined executive summary** where synthesis across banking + bureau requires genuine reasoning
- **Novel or ambiguous financial patterns** not covered by deterministic tags

### Recommendation

```python
# config/settings.py

# For interactive use (single report, user waiting):
SUMMARY_MODEL = "deepseek-r1:14b"    # Quality-first

# For batch stamping:
SUMMARY_MODEL_BATCH = "llama3.2"     # Speed-first (or "qwen2.5:7b" for quality+speed)
```

Override at the start of `batch_reports.py`:

```python
# batch_reports.py
import config.settings as settings
settings.SUMMARY_MODEL = "llama3.2"  # Override for batch performance
```

### Quality Comparison: deepseek-r1 vs llama3.2 for Report Summaries

Given that prompts already include:
- Pre-computed numbers (salary, cashflow, FOIR)
- Pre-annotated risk tags (`[HIGH RISK]`, `[STRETCHED]`)
- Pre-computed interaction signals (`CREDIT HUNGRY + LOAN STACKING`)
- Pre-formatted event blocks with significance levels

The LLM's job is essentially **prose arrangement** — converting structured bullet points into flowing paragraphs. For this task, the quality difference between deepseek-r1 and llama3.2 is **marginal**. The structured input compensates for the smaller model's limitations.

---

## Appendix: Current `batch_reports.py` Limitations

The current batch script (`batch_reports.py`) has these performance issues:

```python
# Line 63-73: Pure sequential loop, no parallelism
for i, crn in enumerate(crns, 1):
    generate_combined_report_pdf(int(crn))  # ← blocking, sequential
```

1. **No parallelism** — processes one customer at a time
2. **No model override** — uses whatever SUMMARY_MODEL is set globally
3. **No phase separation** — deterministic + LLM + rendering all interleaved
4. **No progress callback** — just logs (no time estimates)
5. **No LLM timeout** — a stuck Ollama call blocks the entire batch
6. **Resume is file-based** — checks for Excel file existence, not partial state

All strategies above address these limitations.

---

*Research generated from full codebase analysis — 2026-03*
*All timing estimates are approximations based on model sizes and typical Ollama inference rates*
