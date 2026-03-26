# Using Reasoning Traces to Improve Report Quality

This document explains how to use the `--log-reasoning` feature in `batch_reports.py` to systematically improve prompts, detect hallucinations, and refine the report generation pipeline.

---

## 1. Generating the Log

```bash
# Set SUMMARY_MODEL = "deepseek-r1:14b" in config/settings.py first

# Single customer
python batch_reports.py --crns 698167220 --log-reasoning reports/reasoning_log.txt

# Full batch
python batch_reports.py --source tl_features --log-reasoning reports/reasoning_log.txt
```

The log file contains reasoning traces for two summary types:
- **CustomerReview** — Banking transaction summary (salary, EMI, spending, events)
- **BureauReview** — Bureau tradeline summary (portfolio, DPD, utilization, risk signals)

Each entry is timestamped and labelled, making it easy to grep:
```bash
grep -A 50 "\[CustomerReview\]" reports/reasoning_log.txt
grep -A 50 "\[BureauReview\]" reports/reasoning_log.txt
```

---

## 2. What to Look For

### 2a. Hallucination Detection

The model's reasoning trace reveals when it fabricates data. Look for phrases like:

| Trace pattern | Problem | Action |
|---|---|---|
| "I'll estimate..." / "approximately..." | Model is guessing a number | Add the missing data point to `_build_data_summary()` or `_build_bureau_data_summary()` |
| "The data doesn't mention X, but typically..." | Model is filling gaps with general knowledge | Add "If X is not present, omit it entirely" to the prompt rule in `config/prompts.py` |
| "Let me calculate..." / "sum of..." | Model is doing arithmetic | Precompute the value in the builder and pass it as a labelled field |
| "I assume this means..." | Ambiguous data label | Rename the field in the data summary to be self-explanatory |

**Example workflow:**
1. Grep the trace for "estimate", "assume", "calculate", "probably", "typically"
2. Note which data point triggered it
3. Either add the missing precomputed value to the data summary, or add a prohibition to the prompt

### 2b. Prompt Compliance Audit

The trace shows the model's internal decision process against your prompt rules. Check:

- **Does it acknowledge each rule?** A well-tuned prompt will show the model reasoning: "The rules say I should not mention scores, so I'll describe the behavior instead."
- **Does it skip rules?** If the trace never mentions a rule, the model may be ignoring it. Consider moving that rule higher in the prompt or rephrasing it.
- **Does it misinterpret a rule?** E.g., "No arithmetic" being interpreted as "don't mention any numbers." Rephrase for clarity.

### 2c. Data Coverage Gaps

The trace reveals what the model wishes it had:

- "There's no information about..." — A field you could add to the data summary
- "I see salary data but no frequency..." — An existing feature not being passed through
- "The DPD section doesn't clarify which product..." — A label that needs more context

Cross-reference these gaps against the full feature sets in `features/bureau_features.py` and `schemas/customer_report.py` — the data may already be computed but not included in the summary builder.

### 2d. Reasoning Quality Assessment

Compare the trace across models to evaluate reasoning depth:

| Signal | Good reasoning | Poor reasoning |
|---|---|---|
| Data grounding | "The data says 65% utilization, tagged HIGH RISK, so I'll flag this" | "Utilization seems high" |
| Constraint awareness | "Rule says no arithmetic, so I'll quote the precomputed FOIR directly" | Silently computes a ratio |
| Structure compliance | "Paragraph 1 is portfolio overview, paragraph 2 is behavioral insights" | Mixes facts and risk commentary |

---

## 3. Iterative Prompt Improvement Workflow

```
Step 1: Run batch with --log-reasoning
Step 2: Grep traces for hallucination/violation patterns (see 2a-2b)
Step 3: Edit the prompt in config/prompts.py OR add data to the summary builder
Step 4: Re-run same CRNs, compare traces
Step 5: Repeat until traces show clean reasoning
```

### Concrete examples of fixes driven by traces

**Trace says:** "I need to calculate net cashflow but the rule says no arithmetic..."
**Fix:** Precompute `net_monthly_cashflow` in `_build_data_summary()` and pass it as a labelled line: `"Monthly Net Cashflow: ₹42,000 [HEALTHY]"`

**Trace says:** "The data mentions 3 tradelines with DPD > 0 but doesn't say which products..."
**Fix:** In `_build_bureau_data_summary()`, append product names next to DPD counts: `"DPD > 0: 3 tradelines (PL, CC, BL)"`

**Trace says:** "I'll mention the score classification as instructed... wait, rule says don't mention scores"
**Fix:** The model caught itself — good. But if the final output still contains the score, the prompt rule needs to be stronger or moved earlier.

---

## 4. Comparing Models

Run the same CRNs with different reasoning models and diff the traces:

```python
# In config/settings.py, switch SUMMARY_MODEL between:
"deepseek-r1:14b"    # baseline
"qwq:32b"            # Qwen reasoning — compare depth
"qwen3:14b"          # Qwen3 thinking mode
"phi4-reasoning:14b" # Microsoft reasoning
```

```bash
# Run each model, save separate logs
SUMMARY_MODEL=deepseek-r1:14b  → --log-reasoning reports/trace_deepseek.txt
SUMMARY_MODEL=qwq:32b          → --log-reasoning reports/trace_qwq.txt

# Compare
diff reports/trace_deepseek.txt reports/trace_qwq.txt
```

**What to compare:**
- Which model catches more prompt rule violations in its reasoning?
- Which model hallucinates less (fewer "assume"/"estimate" in traces)?
- Which model follows the two-paragraph structure more reliably?
- Reasoning length vs output quality — longer traces don't always mean better output

---

## 5. Batch Analysis Script

Quick one-liner to scan a reasoning log for red flags:

```bash
# Count hallucination signals per summary type
grep -c "estimate\|assume\|calculate\|probably\|typically\|I think" reports/reasoning_log.txt

# Find which CRN traces have issues (look at timestamps to correlate)
grep -B2 "assume\|estimate" reports/reasoning_log.txt

# Count entries per type
grep -c "\[CustomerReview\]" reports/reasoning_log.txt
grep -c "\[BureauReview\]" reports/reasoning_log.txt
```

---

## 6. Using Traces to Train & Strengthen the Agent

Beyond prompt debugging, reasoning traces are a training asset. Below are practical techniques ordered by effort — start from the top.

### 6a. Few-Shot Reasoning Examples (No Training Needed)

The fastest win. Curate 2-3 gold-standard traces from your logs and embed them directly in the prompt as examples.

**How to do it:**
1. Run a batch with `--log-reasoning` using `deepseek-r1:14b` or `qwq:32b`
2. Pick the best traces — ones that reference all data points, follow the prompt structure, and produce clean output
3. Hand-edit if needed (remove hallucinated parts, tighten reasoning)
4. Add to `BUREAU_REVIEW_PROMPT` or `CUSTOMER_REVIEW_PROMPT` in `config/prompts.py`:

```
Here is an example of correct reasoning and output:

DATA: [paste a representative data summary]

REASONING PROCESS:
- Customer has 12 tradelines (8 live, 4 closed) — I'll state exact counts
- CC utilization at 82% exceeds the 75% concern threshold — flag in behavioral insights
- 2 PL accounts opened in last 6 months — mention as credit hunger signal
- HL serviced regularly — positive signal to acknowledge

OUTPUT: [paste the corresponding clean narrative]
```

**Why it works:** The model mimics the demonstrated reasoning pattern. No fine-tuning, no infra. Works with any model including `llama3.2`.

**Token cost:** Each example adds ~300-500 tokens. With `deepseek-r1:14b` (32k context), you can fit 2-3 examples easily.

### 6b. Self-Verification Pass (Catch Hallucinated Numbers)

Add a second LLM call after narration to verify the output against the source data.

**How to do it:**
After `generate_bureau_review()` produces a narrative, run a verification prompt:
```
Given this data:
{data_summary}

And this generated narrative:
{narrative}

List any numbers, amounts, or percentages in the narrative that do NOT appear
in the data. Return JSON: {"verified": true} or {"verified": false, "issues": ["..."]}
```

Use `format="json"` on the verification call. If verification fails, regenerate or flag the report.

**Cost:** Adds ~5-10 seconds per report on Ollama. Worth it for batch runs where quality matters.

**Where to add:** In `generate_bureau_review()` and `generate_customer_review()` in `pipeline/reports/report_summary_chain.py`, after the `strip_think()` call.

### 6c. Automated Prompt Refinement with DSPy

DSPy treats prompts as optimizable programs. Instead of manually editing prompts, DSPy tests variations and picks the best one.

**How to do it:**
1. `pip install dspy`
2. Define your task as a DSPy signature:
   ```python
   class BureauReview(dspy.Signature):
       """Generate a bureau portfolio review narrative."""
       data_summary: str = dspy.InputField()
       narrative: str = dspy.OutputField()
   ```
3. Provide 20-50 (data_summary, expected_narrative) pairs as examples
4. Run DSPy's `BootstrapFewShot` or `MIPROv2` optimizer — it automatically selects the best few-shot examples and prompt phrasing
5. DSPy works with Ollama as a backend via `dspy.OllamaLocal`

**When to use:** After you've collected enough traces to have a validation set. DSPy finds prompt improvements you wouldn't spot manually.

### 6d. Distillation — Teach a Small Model to Reason Like a Big One

Use traces from a large model (`qwq:32b`, `deepseek-r1:32b`) as training data for a smaller, faster model.

**Workflow:**
```
Step 1: Collect 300+ traces
   Run all your CRNs through qwq:32b with --log-reasoning
   Save pairs of (data_summary_prompt → full <think>...</think> + narrative)

Step 2: Format as training data
   Convert to ShareGPT/ChatML JSON:
   {"conversations": [
     {"from": "human", "value": "<the prompt with data summary>"},
     {"from": "gpt", "value": "<think>reasoning</think>narrative"}
   ]}

Step 3: Fine-tune a smaller model
   Use Unsloth (works on M-series Mac) to LoRA fine-tune qwen3:8b or llama3.2
   The small model learns to emit <think> traces AND produce better narratives

Step 4: Export and deploy
   Export to GGUF → import into Ollama → set as SUMMARY_MODEL
```

**Tools:**
- **Unsloth** — QLoRA fine-tuning, exports to GGUF for Ollama. Works on Apple Silicon.
- **MLX-LM** — Apple's native fine-tuning framework for M-series. Supports LoRA.
- **Axolotl** — More config-heavy, better for multi-GPU setups.

**Dataset size:** 200-500 high-quality pairs is enough for a narrow domain like credit narration. Curate aggressively — remove traces with hallucinated numbers.

**Key check:** After distillation, verify the smaller model doesn't hallucinate numbers. Run the self-verification pass (6b) on distilled outputs.

### 6e. Rejection Sampling — Filter Before Training

A lighter alternative to full RLHF. Generate multiple outputs, score them with rules, keep only the best for training.

**How to do it:**
1. For each data_summary, generate 5 responses with `temperature=0.3`
2. Score each response automatically:
   - Does every number in the narrative appear in the data summary? (+1)
   - Does it follow the two-paragraph structure? (+1)
   - Does it mention all HIGH RISK tagged items? (+1)
   - Is it within the target length (6-10 lines portfolio, 4-6 lines behavioral)? (+1)
3. Keep the highest-scoring response as training data
4. Use these curated (prompt, best_response) pairs for fine-tuning (6d)

**Why this beats raw distillation:** Even `qwq:32b` sometimes hallucinates. Rejection sampling ensures your training data is clean.

### 6f. RAG-Enhanced Narration (Policy Grounding)

Retrieve relevant credit policy snippets and include them in the narration prompt, so the model grounds its language in actual Kotak policy.

**How to do it:**
1. Store credit policy documents in a local vector store (ChromaDB or FAISS)
2. Use `nomic-embed-text` via Ollama for embeddings (stays local)
3. Before calling `generate_bureau_review()`, retrieve the 2-3 most relevant policy snippets based on the data summary
4. Inject into the prompt: "Relevant credit policies: {retrieved_snippets}"

**Example:** If the data shows CC utilization at 85%, the retriever pulls: "Kotak policy: CC utilization above 75% requires additional income verification for unsecured lending." The model then writes: "Credit card utilization stands at 85%, which per policy triggers additional income verification requirements."

**Tools:** ChromaDB (`pip install chromadb`), LangChain's `RetrievalQA` — both already compatible with your LangChain setup.

### 6g. Priority Roadmap

| Technique | Impact | Effort | Do When |
|---|---|---|---|
| Few-shot examples (6a) | High | Low | Now — immediate quality boost |
| Self-verification (6b) | High | Low | Now — catches hallucinations |
| Prompt refinement / DSPy (6c) | High | Medium | After collecting 50+ traces |
| Rejection sampling (6e) | Medium | Medium | Before any fine-tuning |
| Distillation (6d) | High | High | When you have 300+ curated pairs |
| RAG policy grounding (6f) | Medium | Medium | When policy docs are digitized |

---

## 7. Key Project Files Referenced

| File | Role in this workflow |
|---|---|
| `config/settings.py` | Switch `SUMMARY_MODEL` between reasoning models |
| `config/prompts.py` | Edit `CUSTOMER_REVIEW_PROMPT` and `BUREAU_REVIEW_PROMPT` based on trace findings |
| `pipeline/reports/report_summary_chain.py` | `_build_data_summary()` and `_build_bureau_data_summary()` — add missing data points here |
| `utils/llm_utils.py` | `strip_think()` — extracts and logs reasoning before stripping |
| `batch_reports.py` | `--log-reasoning` flag to generate trace files |
