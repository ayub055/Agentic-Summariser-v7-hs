# Model Selection & Deployment Guide

> **Scope:** Ollama model availability, VRAM requirements, AWS SageMaker instance mapping
> **Context:** Choosing the right model for each pipeline role to reduce hallucination while balancing cost and latency

---

## 1. Current Model Assignment (Problem)

```python
# config/settings.py — CURRENT
PARSER_MODEL   = "mistral"      # 7B  — intent parsing (JSON)     ✅ works well
EXPLAINER_MODEL = "llama3.2"    # 3B  — streaming chat answers    ✅ acceptable
SUMMARY_MODEL   = "llama3.2"    # 3B  — report summaries (PDF)    ❌ hallucination-prone
```

The `SUMMARY_MODEL` is the bottleneck. Report summaries (banking review, bureau review, combined executive summary, customer persona) require:
- Strict instruction following (5-8 constraints per prompt)
- Exact number quotation (no rounding, no invention)
- Structural compliance (exactly 2 paragraphs, specific content per paragraph)
- Absence awareness (don't mention products not in the data)

A 3B model lacks the capacity for all of these simultaneously.

---

## 2. Candidate Models Available on Ollama

All models below are available via `ollama pull <name>` with zero setup.

### Tier 1 — Small (1B–3B) | Fast, Low Quality

| Model | Params | Ollama Command | VRAM (Q4) | Strengths | Weaknesses |
|-------|--------|---------------|-----------|-----------|------------|
| llama3.2 | 3B | `ollama pull llama3.2` | ~4 GB | Fast streaming, good for chat | Poor instruction following, hallucinates on complex prompts |
| deepseek-r1:1.5b | 1.5B | `ollama pull deepseek-r1:1.5b` | ~2 GB | Ultra-fast | Too small for any analytical task |
| qwen2.5:3b | 3B | `ollama pull qwen2.5:3b` | ~4 GB | Multilingual | Same limitations as llama3.2 |

**Verdict:** Suitable for `EXPLAINER_MODEL` (streaming speed matters). NOT suitable for `SUMMARY_MODEL`.

---

### Tier 2 — Medium (7B–8B) | Balanced

| Model | Params | Ollama Command | VRAM (Q4) | Strengths | Weaknesses |
|-------|--------|---------------|-----------|-----------|------------|
| mistral | 7B | `ollama pull mistral` | ~6 GB | Excellent JSON, fast, reliable | Weaker narrative prose |
| llama3.1:8b | 8B | `ollama pull llama3.1:8b` | ~6 GB | Good general purpose, 128K context | Moderate instruction following |
| qwen2.5:7b | 7B | `ollama pull qwen2.5:7b` | ~6 GB | Strong instruction following | Slightly slower |
| qwen3:8b | 8B | `ollama pull qwen3:8b` | ~6 GB | Latest Qwen, strong reasoning | Newer, less tested |
| gemma2:9b | 9B | `ollama pull gemma2:9b` | ~7 GB | Good prose quality | Limited financial domain |

**Verdict:** Good for `PARSER_MODEL` (mistral already optimal). Marginal improvement over 3B for summaries — not recommended as `SUMMARY_MODEL` given the complexity of the prompts.

---

### Tier 3 — Large (14B) | High Quality, Practical for Local ⭐ RECOMMENDED

| Model | Params | Ollama Command | VRAM (Q4) | Strengths | Weaknesses |
|-------|--------|---------------|-----------|-----------|------------|
| **deepseek-r1:14b** | 14B | `ollama pull deepseek-r1:14b` | **~12 GB** | Reasoning trace (`<think>`) catches constraint violations; strong math/structure | ~5-8s per summary; `strip_think()` needed (already implemented) |
| **qwen2.5:14b** | 14B | `ollama pull qwen2.5:14b` | **~12 GB** | Excellent instruction following; strong structured output | No reasoning trace |
| **qwen3:14b** | 14B | `ollama pull qwen3:14b` | **~12 GB** | Latest generation; hybrid thinking mode | Newer, less production-tested |
| mistral-small | 22B | `ollama pull mistral-small` | ~16 GB | Strong instruction following | Higher VRAM, slower |

**Verdict:** This is the sweet spot for `SUMMARY_MODEL`. 14B models run comfortably on a single 16GB+ GPU (any M-series Mac, RTX 4090, A4000). The quality jump from 3B→14B is massive for instruction-following tasks.

**Top pick: `deepseek-r1:14b`** — the reasoning trace is uniquely valuable for anti-hallucination because the model "thinks through" constraints before generating output.

---

### Tier 4 — XL (32B–70B) | Premium Quality, Requires Serious Hardware

| Model | Params | Ollama Command | VRAM (Q4) | Strengths | Weaknesses |
|-------|--------|---------------|-----------|-----------|------------|
| qwen2.5:32b | 32B | `ollama pull qwen2.5:32b` | ~24 GB | Near-GPT-4 quality | Needs 24GB+ GPU |
| deepseek-r1:32b | 32B | `ollama pull deepseek-r1:32b` | ~24 GB | Strong reasoning + quality | Needs 24GB+ GPU |
| llama3.3:70b | 70B | `ollama pull llama3.3:70b` | ~43 GB | Best open-source general model | Needs 48GB+ (dual GPU or A6000) |
| qwen2.5:72b | 72B | `ollama pull qwen2.5:72b` | ~45 GB | Premium quality | Same hardware requirement |
| deepseek-r1:70b | 70B | `ollama pull deepseek-r1:70b` | ~43 GB | Best reasoning model | Same hardware requirement |

**Verdict:** Overkill for this system's needs. The 14B tier already handles the prompt complexity. Use 32B+ only if hallucination persists after implementing the prompt fixes + 14B model.

---

## 3. Recommended Model Assignment

```python
# config/settings.py — RECOMMENDED

PARSER_MODEL    = "mistral"          # 7B  | ~6 GB  | JSON extraction, fast
EXPLAINER_MODEL = "llama3.2"         # 3B  | ~4 GB  | Streaming chat, speed-critical
SUMMARY_MODEL   = "deepseek-r1:14b"  # 14B | ~12 GB | Report summaries, quality-critical
```

### Why This Combination Works

| Role | Why This Model | Alternative |
|------|---------------|-------------|
| **Parser** (mistral 7B) | Already proven. JSON `format="json"` works reliably. Fast (~1-2s). No reason to change. | qwen2.5:7b (comparable) |
| **Explainer** (llama3.2 3B) | Streams quickly (~40 chars/sec). User sees real-time typing. Quality is acceptable for Q&A — data is pre-computed, LLM just narrates. | qwen2.5:3b |
| **Summary** (deepseek-r1:14b) | 4.7x larger than current. Reasoning trace catches "I was told not to mention CC util but reports usually have it" violations. Report gen is async — user is already waiting. Extra 3-5s is invisible. | qwen2.5:14b (no reasoning trace but better instruction following out-of-box) |

### Total VRAM Requirement

```
Ollama loads one model at a time (default), or multiple with --num-parallel

Minimum (sequential model loading):  ~12 GB (largest model dictates)
Optimal (all three loaded):          ~22 GB (6 + 4 + 12)

Hardware needed:
  - Apple M2 Pro/Max (16-32 GB unified) ✅
  - Apple M3/M4 Pro (18-36 GB unified)  ✅
  - RTX 4090 (24 GB VRAM)               ✅
  - RTX 3090 (24 GB VRAM)               ✅
  - A4000 (16 GB VRAM)                  ✅ (sequential loading)
  - RTX 4070 (12 GB VRAM)               ⚠️ (tight, sequential only)
```

---

## 4. AWS SageMaker Deployment

For production deployment where Ollama runs on a dedicated GPU server instead of a developer laptop.

### Instance Types by Model Size

| Model Size | SageMaker Instance | GPU | GPU Memory | On-Demand Price* | Use Case |
|------------|-------------------|-----|-----------|-----------------|----------|
| **3B** (llama3.2) | **ml.g5.xlarge** | 1× A10G | 24 GB | ~$1.41/hr | Explainer (streaming) |
| **7B** (mistral) | **ml.g5.xlarge** | 1× A10G | 24 GB | ~$1.41/hr | Parser (JSON) |
| **14B** (deepseek-r1:14b) | **ml.g5.2xlarge** | 1× A10G | 24 GB | ~$1.89/hr | Summary (quality) |
| **32B** (qwen2.5:32b) | **ml.g5.4xlarge** | 1× A10G | 24 GB | ~$2.53/hr | Premium summary (if needed) |
| **70B** (llama3.3:70b) | **ml.g5.12xlarge** | 4× A10G | 96 GB | ~$7.09/hr | Full-capability (overkill) |
| **70B** (FP16, no quant) | **ml.p4d.24xlarge** | 8× A100 | 320 GB | ~$37.69/hr | Research only |

*Prices are approximate US East region, on-demand. Savings Plans reduce by 30-60%. AWS announced up to 45% price reduction for P4/P5 instances effective June 2025.

### Recommended Production Setup

**Option A — Single Instance (Simple, Cost-Effective)**

```
ml.g5.2xlarge (1× A10G, 24 GB VRAM)
├── mistral (7B, Q4)       → ~6 GB
├── llama3.2 (3B, Q4)      → ~4 GB
└── deepseek-r1:14b (Q4)   → ~12 GB
    Total: ~22 GB ✅ fits in 24 GB

Cost: ~$1.89/hr = ~$1,380/month (on-demand)
      ~$830/month (1yr savings plan, ~40% off)
```

All three models loaded in Ollama simultaneously. Sequential inference (one model at a time per request). Sufficient for single-user or low-concurrency deployments.

**Option B — Split Instances (Higher Throughput)**

```
ml.g5.xlarge (Parser + Explainer)
├── mistral (7B)       → fast, handles all queries
└── llama3.2 (3B)      → streaming responses
Cost: ~$1.41/hr

ml.g5.xlarge (Summary — dedicated)
└── deepseek-r1:14b    → report generation only
Cost: ~$1.41/hr

Total: ~$2.82/hr = ~$2,060/month (on-demand)
       ~$1,240/month (1yr savings plan)
```

Separate Ollama instances. Summary generation doesn't block query answering. Better for multi-user production.

**Option C — Premium (32B Summary Model)**

```
ml.g5.xlarge  → Parser (mistral) + Explainer (llama3.2)
ml.g5.4xlarge → Summary (qwen2.5:32b or deepseek-r1:32b)

Total: ~$3.94/hr = ~$2,880/month (on-demand)
       ~$1,730/month (1yr savings plan)
```

Only if 14B quality isn't sufficient after prompt fixes are implemented.

### Instance Selection Decision Tree

```
Q: How many concurrent users?

  1-3 users  → Option A (ml.g5.2xlarge, ~$1.89/hr)
  3-10 users → Option B (2× ml.g5.xlarge, ~$2.82/hr)
  10+ users  → Option B + autoscaling on summary instance

Q: Is hallucination still present after prompt fixes + 14B?

  Yes → Upgrade summary to 32B: ml.g5.4xlarge (~$2.53/hr)
  No  → Stay with 14B on ml.g5.2xlarge
```

---

## 5. Cost Comparison — Local vs SageMaker

| Deployment | Hardware | Monthly Cost | Latency | Concurrency |
|-----------|----------|-------------|---------|-------------|
| **Local (dev laptop)** | M2 Pro 16GB | $0 (owned) | 5-8s/summary | 1 user |
| **Local (workstation)** | RTX 4090 24GB | $0 (owned) | 3-5s/summary | 1-2 users |
| **SageMaker g5.2xlarge** | A10G 24GB | ~$1,380/mo | 3-5s/summary | 1-3 users |
| **SageMaker 2×g5.xlarge** | 2× A10G | ~$2,060/mo | 3-5s/summary | 3-10 users |
| **SageMaker g5.4xlarge** (32B) | A10G 24GB | ~$2,880/mo | 5-8s/summary | 1-3 users |

---

## 6. Migration Steps

### Step 1 — Local Testing (No Cost)

```bash
# Pull the recommended summary model
ollama pull deepseek-r1:14b

# Verify it runs
ollama run deepseek-r1:14b "Summarize this: Total tradelines 5, live 3, closed 2."
```

### Step 2 — Update Config

```python
# config/settings.py — one line change
SUMMARY_MODEL = "deepseek-r1:14b"
```

### Step 3 — Test Reports

Generate reports for 5-10 customers. Check:
- No CC utilization mentioned for customers without credit cards
- No prompt example phrases echoed
- Exact numbers quoted from data
- Two-paragraph structure maintained

### Step 4 — SageMaker Deployment (When Ready)

```bash
# On SageMaker instance (ml.g5.2xlarge)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
ollama pull llama3.2
ollama pull deepseek-r1:14b

# Expose Ollama on internal network
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

Update `ChatOllama` base URL in code to point to SageMaker instance instead of localhost.

---

## 7. Model Quality vs Hallucination Matrix

How each model handles the specific hallucination types from the [hallucination fix plan](hallucination_fix_plan.md):

| Hallucination Type | llama3.2 (3B) | llama3.1:8b | deepseek-r1:14b | qwen2.5:14b | qwen2.5:32b |
|-------------------|--------------|------------|----------------|------------|------------|
| **V1** CC util invention | Frequent | Occasional | Rare (thinks through absence) | Rare | Very rare |
| **V2** Prompt example echo | Frequent | Occasional | Rare (reasoning separates instruction from data) | Occasional | Very rare |
| **V5** Persona speculation | Always | Frequent | Occasional | Occasional | Rare |
| **V7** Explainer over-interpretation | Occasional | Occasional | Rare | Rare | Very rare |
| **V8** Missing data fill-in | Frequent | Occasional | Rare (with absence markers) | Rare | Very rare |
| Structural compliance (2 paragraphs) | Poor | Moderate | Good | Good | Excellent |
| Number exactness | Poor | Moderate | Good | Good | Excellent |

**Key insight:** Moving from 3B→14B eliminates ~70% of hallucination incidents. The remaining ~30% requires the prompt/data fixes from the hallucination plan. Together they target near-zero.

---

*Guide generated from Ollama library, AWS SageMaker documentation, and system analysis — 2026-03*

Sources:
- [Ollama Model Library](https://ollama.com/library)
- [DeepSeek-R1 on Ollama](https://ollama.com/library/deepseek-r1)
- [Ollama VRAM Requirements Guide](https://localllm.in/blog/ollama-vram-requirements-for-local-llms)
- [AWS SageMaker Instance Types for LMI](https://docs.aws.amazon.com/sagemaker/latest/dg/large-model-inference-choosing-instance-types.html)
- [AWS SageMaker Pricing](https://aws.amazon.com/sagemaker/ai/pricing/)
- [AWS SageMaker GPU Price Reductions (June 2025)](https://aws.amazon.com/about-aws/whats-new/2025/06/price-reductions-amazon-sagemaker-ai-gpu-accelerated-instances/)
- [AWS EC2 G5 Instances](https://aws.amazon.com/ec2/instance-types/g5/)
- [Deploy LLMs on AWS — Cost Guide](https://blog.easecloud.io/en/ai-cloud/deploy-llms-on-aws/)
- [Ollama GPU Memory Requirements](https://ventusserver.com/ollama-gpu-memory-requirements-guide/)
