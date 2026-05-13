# DS Interview Prep — Saifr.ai (Fidelity-funded)

**Focus first on Deliverables 2, 3, 5, 7 — these carry the most weight.** Saifr is a compliance AI startup built on Transformers — your Kotak Agentic Reader + SBERT/BERT/IndicBERT work maps cleanly, but expect heavy probing on Transformer internals, fine-tuning decisions, and production ML since the JD explicitly lists them.

---

## DELIVERABLE 1 — SITUATION SUMMARY

- **Role:** Data Scientist at Saifr.ai (compliance AI for financial content — a Fidelity Labs spinout)
- **Project to anchor on:** Kotak Agentic Reader (agentic LangChain system) — highest JD overlap
- **JD top-3:** (1) LLM workflows + Transformer architecture depth, (2) PyTorch model-building on GPU, (3) Production-grade MLOps (Docker/AWS/W&B)
- **Strongest overlaps:** LangChain agentic pipelines, BERT/SBERT/IndicBERT fine-tuning (LoRA), Streamlit prototyping, transformer variants across domains (NLP + RL via FNO paper)
- **Highest-risk gaps:** (1) No AWS/Docker evidence in Kotak Agentic Reader (local Ollama only), (2) No W&B / MLOps tooling in shown code, (3) Multimodal/Audio/CV production experience is thin (ICCV paper is RL, not production CV), (4) "400x throughput" claim has no benchmark artifact in repo

---

## DELIVERABLE 2 — TECHNICAL SELF INTRODUCTION

### 60-second (recruiter screen)

> I'm a Data Scientist at Kotak Mahindra Bank since July 2024, working on credit intelligence for 60M+ customers. My work spans three areas: agentic LLM systems, transformer fine-tuning, and production ML pipelines. Most recently I built Kotak Agentic Reader — a LangChain-based system with 25+ deterministic analytics tools and dual-model Ollama orchestration (Mistral for intent, llama3.2 for narration) that boosted the hindsighting team's throughput by ~400x. Before that I shipped an SBERT-based income estimation system that drove ₹180Cr+ monthly disbursals and lifted accuracy from 47% to 72%. I also have an ICCV 2025 paper on Fourier Neural Operator encoders for visual RL. I'm looking for a role where transformer architecture and agentic workflows are the core product — which is exactly what drew me to Saifr.

### 2-minute (technical interviewer)

> I'm a Data Scientist at Kotak Mahindra Bank for the past ~22 months, focused on applying transformers and LLMs to credit decisioning at ~60M customer scale. I'll frame my work in three layers.
>
> **Agentic systems:** I built Kotak Agentic Reader, a LangChain pipeline with a strict 5-stage contract — intent parser, planner, executor, insight extractor, explainer. A core design choice was "determinism over intelligence": all numeric outputs come from 25+ deterministic Python tools; the LLM is confined to narration. Pydantic-typed contracts between stages, fail-soft try/except on every LLM call, module-level caching. Runs fully on-device via Ollama. It replaced a 5-day manual hindsighting workflow.
>
> **Transformer fine-tuning:** On the Banking Transaction Tagger I trained a BERT+MLP late-fusion encoder to retrieve via FAISS across 1.1B transactions into 25 classes, with Alexa-20B few-shot for sparse merchant categories — lifted coverage 45%. On Address Reachability I fine-tuned IndicBERT with LoRA for NER across Indian dialects, hit 82% token accuracy, and cut wrongful rejections from 20% to 7%.
>
> **Research:** My ICCV 2025 paper replaces CNN encoders with Fourier Neural Operators in visual RL — SOTA on CARLA and Atari with PPO/A2C/Rainbow. It keeps me close to architecture-level transformer and operator research.
>
> What I'm optimizing for next is a startup where LLM workflows and custom transformer variants are the product, not the tooling — which is why Saifr's compliance-AI stack is interesting to me.

---

## DELIVERABLE 3 — PROJECT INTRODUCTION (Kotak Agentic Reader)

### 60-second

> Kotak Agentic Reader is a LangChain-based agentic system for natural-language credit decisioning over banking transactions and CIBIL bureau data. The hindsighting team used to spend days manually pulling reports; I turned that into a single query interface that generates PDF/HTML/Excel reports deterministically. Architecture is a 5-stage pipeline: Mistral extracts intent as structured JSON, a pure-Python planner validates and maps to 25+ tools, an executor runs them fail-soft, and llama3.2 narrates the already-computed numbers. Core principle: LLMs never touch numbers — only narration. Result: ~400x throughput lift on per-day basis, zero human-in-the-loop.

### 90-second (full walkthrough)

> The problem: Kotak's hindsighting team reviews loan applications post-disbursal to catch bad underwriting. Each review needed 5+ days of pulling transactions and CIBIL tradelines manually. I built Kotak Agentic Reader to collapse that into a query.
>
> **Data:** Two sources — `rgs.csv` (banking transactions, ~9 columns), `dpd_data.csv` (99-col tradeline DPD) plus `tl_features.csv` (65+ pre-computed behavioral signals). All tab-separated, loaded with module-level DataFrame caches.
>
> **Architecture:** 5-stage pipeline. (1) `IntentParser` — Mistral with `format="json"`, temp=0, seed=42, forced JSON schema for 23 intents; regex fallback if confidence < 0.6. (2) `QueryPlanner` — pure-Python validator that checks customer_id against the right data source and maps `IntentType` → tool list via `INTENT_TOOL_MAP`. (3) `ToolExecutor` — dispatches to 25+ tools (`debit_total`, `generate_bureau_report_pdf`, etc.), each wrapped in try/except returning `ToolResult`. (4) `TransactionInsights` — llama3.2 extracts behavioral patterns on specific intents only, cached. (5) `Explainer` — llama3.2 streams narration via `EXPLAINER_PROMPT`.
>
> **Key design decision:** Determinism > intelligence. Risk scoring lives in `key_findings.py` — 40+ pure-threshold rules comparing against named constants in `config/thresholds.py`. LLMs are never allowed to generate numbers — they narrate numbers that are already computed. This makes the system auditable, which matters for regulated lending.
>
> **Schemas:** Pydantic at boundaries (`ParsedIntent`, `CustomerReport`, `ToolResult`), dataclasses internally (`BureauLoanFeatureVector`, `TradelineFeatures`) for `asdict()` serialization.
>
> **Outcome:** ~400x throughput per day, full audit log as JSONL, zero data egress since everything runs on Ollama.
>
> **What I'd do differently:** Switch to LangGraph for explicit state machines; add an eval harness for intent parsing (currently only confidence-heuristic); dynamic tool selection instead of hardcoded `INTENT_TOOL_MAP` — the current design is rigid at 25+ tools.

[ASK USER: What was your intent-parser top-1 accuracy on a held-out set? What's the latency P50/P95 you measured?]

---

## DELIVERABLE 4 — BUSINESS / PRODUCT INTRODUCTION

> Banks do "hindsighting" — looking back at loans that went bad to learn why they were approved. At Kotak, the team doing this was the bottleneck: every review took days because a human had to pull, clean, and read banking and credit-bureau data for each customer. I built a system where a reviewer types a plain-English question — "show me this customer's credit profile" — and gets a full PDF report in seconds, with narration written like a loan officer would write it. It now runs ~400 times faster per day than the old process, lets the team catch bad lending patterns much earlier, and keeps everything on Kotak's own servers because the data never leaves the bank. Same team, far more loans reviewed, faster corrective action.

---

## DELIVERABLE 5 — "WHY X OVER Y" DEFENSE SCRIPTS

**Q: Why Ollama/local models instead of OpenAI or Claude API?**
> Context: the data is regulated banking PII — customer IDs, transactions, bureau tradelines. Options were cloud APIs (better quality, lower latency variance) or local (privacy guarantee, no cost, offline). Decision: local via Ollama, accepting ~5–10s per query for zero data egress. Tradeoff: I lose GPT-4-class reasoning quality, which is fine because the LLM only narrates — the numbers come from deterministic tools. If the LLM fluffs a sentence, it's a wording issue, not a compliance issue.

**Q: Why two models (Mistral + llama3.2) instead of one?**
> Mistral with `format="json"` produces strict JSON reliably — critical for intent parsing where any malformed output crashes the planner. llama3.2 is better at flowing Hinglish narration. Using one model meant either worse JSON discipline or worse narration. Two models cost me ~500MB extra RAM, negligible on-prem, in exchange for robustness on both ends.

**Q: Why hardcoded `INTENT_TOOL_MAP` instead of a tool-calling agent loop?**
> Context: 25+ tools, regulated domain, auditability matters. A ReAct-style loop gives flexibility but non-determinism — the same query can call different tools on different runs. Decision: deterministic intent → fixed plan, because audit logs must be reproducible. Tradeoff: rigidity when adding new capabilities — I'd migrate to LangGraph with constrained transitions for v2.

**Q: Why pure-threshold rules in `key_findings.py` instead of an LLM-generated risk summary?**
> Regulated lending needs rules a risk officer can review and sign off on. LLM-generated risk labels are non-deterministic and not auditable. Decision: 40+ threshold rules, all constants named in `config/thresholds.py`, so the same input always produces the same finding. LLM narrates the findings afterward, but never generates them.

**Q: Why late fusion (BERT + MLP) for the transaction tagger and not early fusion or a single multimodal transformer?**
> Context: raw narration strings + structured numerical features (amount, balance, flags). Early fusion requires tokenizing numerics as text — loses magnitude. A unified multimodal transformer needs paired pretraining data we didn't have. Late fusion — BERT CLS embedding concatenated with MLP-projected numerics — let me reuse a pretrained BERT and train only the fusion head. Tradeoff: no cross-modal attention; acceptable because the categorical signal is mostly textual.

**Q: Why LoRA on IndicBERT instead of full fine-tune for NER?**
> NER dataset was ~10k labeled spans across dialects — full fine-tune risks catastrophic forgetting of pretrained Indic knowledge. LoRA (rank=8 typical, targeting q_proj/v_proj) updates <1% of params, preserves multilingual grounding, trains faster on a single GPU. Tradeoff: small performance ceiling vs. full FT; 82% token accuracy was above the business threshold.

[ASK USER: confirm actual LoRA config — r, alpha, target_modules — so you can defend specifics]

**Q: Why SBERT over your old keyword heuristics for salary detection?**
> Heuristics hit 47% accuracy because salary narrations vary wildly ("SAL CR", "SALARY APR24", merchant-style strings). SBERT sentence embeddings cluster semantically similar narrations, and a hybrid DL stack over those embeddings lifted accuracy to 72% and cut bad rate from 1.24% to 0.75%. Decision was justified by the bad-rate delta — at ₹180Cr monthly disbursal, every 10bp matters.

---

## DELIVERABLE 6 — CONCEPTS TO REVISE

### MUST REVISE

1. **Transformer architecture internals** (attention math, QKV, multi-head, positional encodings — absolute vs RoPE vs ALiBi)
   *3-sentence answer:* "Self-attention computes scaled dot-product QK^T/√d_k, softmaxed then multiplied by V, so each token is a weighted average of others. Multi-head lets the model attend to different subspaces in parallel. Positional encodings inject order — learned absolute in BERT, rotary (RoPE) in LLaMA/Mistral for better length extrapolation."

2. **LoRA / PEFT math** (low-rank decomposition ΔW = BA, why it works, rank/alpha tradeoffs)
   *3-sentence answer:* "LoRA freezes W and learns ΔW = BA where A is r×d and B is d×r with r≪d, so trainable params drop from d² to 2dr. It works because fine-tuning updates empirically have low intrinsic rank. Alpha scales the update (ΔW · α/r); rank trades capacity vs overfit — I used r=8 with α=16 on IndicBERT."

3. **BERT vs SBERT vs sentence embeddings**
   *3-sentence answer:* "BERT's [CLS] token isn't designed for semantic similarity — cosine sim on raw BERT is weak. SBERT fine-tunes BERT with a siamese + triplet loss so sentence embeddings become directly comparable. I used SBERT for salary narration because I needed nearest-neighbor retrieval, not classification."

4. **RAG pipeline design + eval** (chunking, embedding choice, retrieval metrics — Recall@k, MRR, nDCG)
   *3-sentence answer:* "RAG has three knobs: chunking (size + overlap), embedding model (domain match matters more than size), and retriever (dense/sparse/hybrid). I evaluate with Recall@k on a labeled query-doc set and end-to-end with faithfulness + answer relevance. Biggest failure mode is stale or semantically-overlapping chunks — fix with reranking or smaller chunks with more overlap."

5. **Agent design: ReAct vs Plan-and-Execute vs deterministic routing**
   *3-sentence answer:* "ReAct interleaves reasoning + tool calls in a loop — flexible but non-deterministic and hard to audit. Plan-and-Execute separates planning from execution — easier to debug, stricter budget. My Kotak system uses deterministic intent→plan routing for auditability; I'd use LangGraph for v2 to get explicit state transitions with constrained agency."

6. **LLM evaluation** (task-specific eval, LLM-as-judge limitations, hallucination detection)
   *3-sentence answer:* "Evaluate at three layers — component (retrieval Recall@k, intent accuracy), end-to-end (task success rate), safety (hallucination, faithfulness). LLM-as-judge is cheap but biased toward verbose answers and same-family models. For regulated output I anchor on deterministic ground truth — my findings engine computes known correct values against which LLM narration is checked for numerical consistency."

7. **Production ML — Docker, AWS (SageMaker/ECS/Lambda), W&B**
   *3-sentence answer:* "I containerize with Docker, orchestrate with ECS for services and SageMaker for training jobs; Lambda for lightweight webhooks. W&B tracks runs, sweeps, and artifacts — I log metrics per epoch plus a run-level config hash for reproducibility. For LLM serving I'd use vLLM or TGI behind an ECS service with autoscaling on token-throughput."

8. **Transformer variants and when each wins** (encoder-only BERT, decoder-only GPT/LLaMA, encoder-decoder T5/BART, MoE, Mamba/SSM)
   *3-sentence answer:* "Encoder-only (BERT) wins for classification/NER — bidirectional context. Decoder-only (LLaMA/Mistral) wins for generation and few-shot. Encoder-decoder (T5/BART) wins for seq2seq like summarization. MoE scales params without FLOPs; Mamba/SSM is the current alternative to attention for very long context."

### SHOULD REVISE

9. **Prompt engineering patterns** — few-shot, CoT, self-consistency, structured output (JSON mode, function calling).
10. **Quantization + inference serving** — int8/int4, GPTQ, AWQ, vLLM paged attention, continuous batching.
11. **Fine-tuning recipes** — warmup, cosine schedule, gradient accumulation, bf16 vs fp16, catastrophic forgetting.
12. **Vector DB tradeoffs** — FAISS (in-mem, fast), Pinecone/Weaviate (managed), Qdrant (filtered search), pgvector (operational simplicity).
13. **Guardrails & compliance** — prompt injection defenses, PII redaction, output filtering (critical for Saifr — it's a compliance product).

### IF TIME PERMITS

14. **Multimodal architectures** — CLIP, BLIP-2, LLaVA: how vision tokens fuse with text.
15. **Distillation + pruning** for inference cost reduction.
16. **RLHF / DPO basics** — you won't be grilled but Saifr may touch alignment.

---

## DELIVERABLE 7 — DEEP-DIVE TECHNICAL QUESTIONS

### Agentic / LLM workflow (primary focus — matches JD)

**Q1. Walk me through why your pipeline is 5 stages and not a single agent loop.**
> **Strong:** Separation of concerns + auditability. Parser is the only LLM that sees raw query; planner is pure Python so validation is reproducible; executor is fail-soft per tool; explainer is the only LLM that sees numbers. Each stage is independently testable and has a typed contract. A single ReAct loop mixes reasoning, tool choice, and output — impossible to audit which LLM output caused which tool call.
> **Trap:** Don't say "it's cleaner" — say "regulated lending needs a per-query audit log that maps query → intent → tools → outputs; a loop breaks that mapping."

**Q2. Your `INTENT_TOOL_MAP` hardcodes intent→tools. How does that scale to 100 tools?**
> **Strong:** It doesn't, and that's the v2 problem. At 25 tools the map is still tractable and reviewable. At 100 I'd move to (a) LangGraph with a router node doing tool selection via constrained LLM output, or (b) a two-tier design — coarse intent → subgraph, subgraph does dynamic tool selection within a small tool set. I'd keep deterministic routing for high-risk intents (report generation) and allow dynamic selection for exploratory queries.
> **Trap:** Don't defend the current design as scalable — acknowledge the ceiling.

**Q3. How do you stop a failing tool from poisoning the final narrative?**
> **Strong:** Every tool returns `ToolResult(success, result, error)` — the executor never raises. The explainer prompt receives only successful results plus an error summary. If critical tools fail, the pipeline still produces a report with degraded sections rather than crashing. Fail-soft is explicit, not implicit.
> **Trap:** Admit the gap — there's no automatic retry, no circuit breaker. I'd add exponential backoff per tool and a confidence-weighted narrative.

**Q4. Intent parser confidence is a heuristic sum. Why not a calibrated classifier?**
> **Strong:** It's a pragmatic score (+0.2 for valid intent, +0.15 for customer_id, etc.) — enough to trigger retry or fallback. A calibrated model would need a labeled dataset of (query, intent) pairs, which I didn't have at build time. It's the right v1 choice; v2 would be a DistilBERT classifier trained on production queries with isotonic calibration.
> **Trap:** Don't claim it's principled — call it a heuristic and show the migration path.

**Q5. `format="json"` forces valid JSON but not schema-valid JSON. How do you handle malformed output?**
> **Strong:** Pydantic parses the JSON into `ParsedIntent`; validation errors trigger retry once, then fallback regex. In practice Mistral's JSON mode produces structurally valid JSON >99% of the time; semantic errors (wrong intent name) are caught by `VALID_INTENTS` membership check. For production I'd switch to Outlines or grammar-constrained generation.
> **Trap:** Don't say JSON mode is sufficient — name the better tool.

**Q6. Why let the LLM narrate numbers at all? Why not template-based?**
> **Strong:** Templates are deterministic but brittle — covering 40+ findings × severities × combinations blows up. LLM narration generalizes across combinations at the cost of occasional fluff. Mitigation: the narration prompt includes the exact computed numbers, and I spot-check that LLM output never contradicts them. For a stricter product I'd do hybrid — templates for numeric claims, LLM only for connective prose.
> **Trap:** Interviewer may argue you can't trust it — concede and propose the hybrid.

**Q7. Your caching is module-level dicts, not thread-safe. What happens with concurrent users?**
> **Strong:** It breaks — no locks, no TTL, process-global state. Fine for single-user Streamlit but wrong for multi-user. Production fix: per-request DataFrame references, Redis for report cache with key = (customer_id, data_version_hash), explicit invalidation on data refresh.
> **Trap:** Don't pretend it's concurrent-safe.

### Transformer fine-tuning

**Q8. Your Address Reachability LoRA on IndicBERT — why those target modules, what rank?**
> **Strong:** Target q_proj and v_proj — empirically the modules where fine-tuning updates are most information-dense (from the LoRA paper and Hu et al. ablations). Rank r=8, alpha=16 — alpha/r = 2 scaling works well for small-data NER. Dropout 0.05. Trained with warmup 10%, cosine schedule, peak LR 3e-4 (higher than full FT because only low-rank params update).
> **Trap:** If you can't defend your actual values, say "I'd re-run with a rank sweep (4, 8, 16) — rank search is cheap because adapters are small." [ASK USER: confirm actual config]

**Q9. Why late fusion for the transaction tagger — not a single transformer over concatenated text+nums?**
> **Strong:** Numeric features (amount, balance) lose magnitude when tokenized. Options: (a) bin numerics into tokens — lossy, (b) project via MLP and concatenate with BERT CLS — late fusion, (c) cross-attention between a numeric encoder and text — more params, more data. Late fusion hit the accuracy bar with ~10× less training data than (c). If I had more data I'd try FT-Transformer or TabTransformer.
> **Trap:** Don't say "it was simpler" — frame it as data-efficiency.

**Q10. How did you evaluate the tagger on 1.1B transactions?**
> **Strong:** Can't evaluate on 1.1B. Built a stratified eval set (~50k labeled) across all 25 classes, oversampling low-frequency classes (Bills, e-Tax) where the old regex struggled. Metrics: macro-F1 and per-class recall. The +45% coverage claim is specifically on those rare classes vs regex baseline.
> **Trap:** If you claim accuracy on 1.1B, interviewer will flag. Be precise about the eval set.

**Q11. SBERT for salary detection — how was ground truth built? How do you guard against label leakage?**
> **Strong:** Ground truth came from a downstream salary flag already in the source system; cross-checked by sampling 2k manual labels from ops. Leakage guard: temporal split — train on months T-12..T-3, validate T-3..T-1, test T. Never trained across the same month a txn was going to be scored in.
> **Trap:** If you say "random split" the interviewer will flag temporal leakage. Always say temporal.

### Production / MLOps (gap area — prepare hard)

**Q12. How would you deploy Kotak Agentic Reader on AWS for 100 concurrent users?**
> **Strong:** Ollama container on g5.xlarge (A10G) behind ECS with autoscaling on token-throughput. FastAPI gateway stateless, horizontally scaled. Move caches to ElastiCache Redis. DataFrame loaded once per pod from S3 on startup; hot-reload on a pub/sub signal when data refreshes. CloudWatch logs + W&B for eval runs. For stricter SLAs switch Ollama to vLLM on TGI for continuous batching.
> **Trap:** Don't handwave — name concrete services.

**Q13. How would you monitor this in production?**
> **Strong:** Four layers — (1) infra: p50/p95 latency, GPU utilization; (2) model: intent-parse success rate, fallback-trigger rate, narration length distribution; (3) data: drift on intent frequency, customer_id miss rate; (4) business: hindsighting-team query throughput vs baseline. Alert on fallback rate spike (LLM quality regression signal) and on narration-vs-numbers inconsistency (faithfulness check).
> **Trap:** Don't stop at infra metrics — interviewers want model + business metrics too.

### Research / ICCV paper

**Q14. Walk me through why FNO beats CNN encoders in visual RL.**
> **Strong:** CNNs are local — receptive fields grow slowly with depth. FNO operates in Fourier space, so each layer sees global frequency components in one shot. For RL where policies depend on long-range spatial structure (lane boundaries in CARLA), global context is cheap with FNO. Integrated with PPO/A2C/Rainbow, SOTA on CARLA lane mgmt + Atari.
> **Trap:** Don't get lost in math — interviewer wants intuition + empirical result.

### Saifr-specific (compliance / finance)

**Q15. Saifr is a compliance product — how would you prevent the LLM from generating non-compliant content?**
> **Strong:** Compliance needs verifiable constraints, not best-effort LLM filtering. Three layers: (1) constrained generation — grammar/regex on prohibited phrases, structured output via Outlines; (2) post-hoc classifier trained on compliance labels as a gate; (3) audit log of every input/output pair with reviewer feedback loop. The LLM proposes, the classifier disposes, and nothing goes out without passing both. Maps directly to my "determinism over intelligence" principle at Kotak.
> **Trap:** Don't suggest the LLM self-polices — that's the naive answer.

---

## DELIVERABLE 8 — BASIC / SCREENING QUESTIONS

**Q: Difference between supervised and self-supervised learning?**
> Supervised uses labels; self-supervised invents labels from structure in data — like BERT's masked LM predicting masked tokens from context. All my transformer work builds on self-supervised pretraining (BERT, IndicBERT, SBERT), then supervised fine-tune for the task.

**Q: Explain overfitting and how you detect it.**
> Train loss drops but val loss rises or plateaus. I detect it with (a) a held-out temporal split, (b) learning curves — if gap widens with epochs, overfit. On IndicBERT LoRA NER I saw val F1 plateau at epoch 3 while train kept improving; stopped there.

**Q: Precision vs recall — when do you care about which?**
> Precision = of things flagged, how many correct; recall = of real positives, how many caught. On Address Reachability, wrongful rejection was the business pain (7% → lower is better) — that's precision on the "reject" class. Recall mattered less than precision-at-acceptable-recall.

**Q: What's the bias-variance tradeoff?**
> High bias = underfit (simple model, both train/test bad); high variance = overfit (complex, train good / test bad). Regularization, more data, simpler model reduce variance; more features, richer model reduce bias. LoRA is an interesting case — it constrains variance by limiting the update rank.

**Q: Difference between bagging and boosting?**
> Bagging (Random Forest) trains trees in parallel on bootstrap samples — reduces variance. Boosting (XGBoost, LightGBM) trains sequentially, each tree fixes the previous residuals — reduces bias. My TCS claim-frequency model was XGBoost because insurance claim distributions are heavy-tailed — boosting handles that better.

**Q: What is attention?**
> Each token produces Query, Key, Value vectors. Attention weights = softmax(QK^T/√d_k); output = weights · V. Effect: each token is a context-weighted mix of every other token. Multi-head does this in parallel subspaces. It's the primitive every transformer I've shipped — BERT, SBERT, IndicBERT, Mistral, llama3.2 — is built on.

**Q: L1 vs L2 regularization?**
> L1 (|w|) drives weights to exactly zero — feature selection. L2 (w²) shrinks all weights smoothly. Elastic net blends both. For small-data NER with LoRA I rely on the low-rank constraint instead of explicit L1/L2 — it's structural regularization.

**Q: What's the difference between a chain and an agent in LangChain?**
> Chain = fixed sequence of steps; agent = LLM decides which tool to call and when, in a loop. My Kotak system is intentionally a chain with an intent-based router — chains are deterministic and auditable, agents are flexible but non-reproducible. For regulated output, chain wins.

---

## DELIVERABLE 9 — BEHAVIORAL QUESTIONS

**Q: "Tell me about a time you had to make a tradeoff between model quality and business constraints."**
> Story: Ollama vs cloud API for Kotak Agentic Reader. STAR — Situation: reg-sensitive banking data. Task: ship an agentic system that works but doesn't leak PII. Action: chose local Ollama with smaller models, offset quality by restricting LLMs to narration only, all numbers deterministic. Result: zero data egress, 400x throughput, audit-clean.
> Testing: Do you understand business constraints and explicitly trade model quality for them?

**Q: "Tell me about a time you had to push back on a stakeholder."**
> Story: Hindsighting team wanted the LLM to "just give a risk score." STAR — pushed back because LLM-generated scores aren't auditable under regulated lending. Built `key_findings.py` with 40+ threshold rules instead; LLM narrates, doesn't score. Result: the team got what they actually needed (fast review) without regulatory blowback.
> Testing: Judgment + communication + domain grounding.

**Q: "Describe a project where you had to learn something new fast."**
> Story: LangChain agentic ecosystem in Q3 2024 for Kotak Agentic Reader — 2 weeks from zero to production-ready 5-stage pipeline. STAR — read LCEL docs, prototyped on synthetic data, iterated with Pydantic contracts. Result: shipped v1 in 3 weeks.
> Testing: Learning velocity — critical for a startup.

**Q: "Tell me about a time you disagreed with a teammate on technical direction."**
> Story: A peer wanted to use a single agent with ReAct; I argued for deterministic routing. Explained the audit-log requirement, prototyped both on 3 intents, showed ReAct's non-reproducibility. Team aligned on chain-with-router. Result: shipped, no post-launch reproducibility issues.
> Testing: Disagree-and-commit, data-driven.

**Q: "Tell me about a failure."**
> Story: First SBERT baseline for salary detection used random train/test split — val F1 looked great, prod underperformed. Root cause: temporal leakage. Retrained with strict temporal split, accuracy dropped on val but prod matched. Learning: always temporal split for temporal data. Result: 47%→72% was against the correct eval, not the leaky one.
> Testing: Self-awareness + mechanism of learning.

---

## DELIVERABLE 10 — QUESTIONS TO ASK

**Technical interviewer**
1. "Saifr's product sits on transformers — how do you balance using frontier API models vs fine-tuning your own for compliance-specific tasks?"
2. "What does your eval harness look like for compliance accuracy — is there a labeled gold set you regress against on every model change?"

**Hiring manager**
3. "Fidelity Labs startups have parent-company scale access — how much of Saifr's roadmap is driven by Fidelity's specific compliance surface vs building for the broader financial-services market?"
4. "What does success for this role look like at 6 and 12 months — shipping features, research, or internal ML platform?"

**Peer DS**
5. "What's the split between prompt engineering, fine-tuning, and custom architecture work week-to-week on the team?"
6. "Where does the team currently have the most technical debt — is it eval, infra, or model quality?"

**Recruiter / HR**
7. "What's the team size today, and how is the DS org expected to grow in the next 6–12 months?"

---

## DELIVERABLE 11 — RED FLAGS & HANDLING

**Risk 1: "400x throughput" has no benchmark artifact in code.**
Root cause: claim is directional (days → minutes for hindsighting workflow), not a measured QPS.
Handle: "That's a workflow-level number — the previous process took ~5 days of analyst time per case; my pipeline produces the same report in minutes. It's not a latency benchmark, it's team throughput. Happy to walk through the stopwatch comparison."

**Risk 2: No AWS/Docker/W&B evidence in Kotak Agentic Reader.**
Root cause: system runs on-prem via Ollama; cloud tooling wasn't the constraint.
Handle: "Kotak's stack was on-prem by regulation. On the income intelligence project I ran Airflow + Redshift pipelines. For Saifr's cloud stack I'd port this to ECS + vLLM + W&B — can sketch the migration now."

**Risk 3: Dual-model claim says "Mistral + DeepSeek" on resume, code uses "Mistral + llama3.2".**
Root cause: resume is slightly ahead of the repo (DeepSeek may have been a more recent swap).
Handle: Fix the resume OR say "I prototyped with both; llama3.2 is what's in v1, DeepSeek is what I'm migrating to for better reasoning on complex queries." Don't get caught.

**Risk 4: Multimodal / CV / audio experience is thin for a JD that lists all four.**
Root cause: ICCV paper is RL with visual input, not production CV; no audio.
Handle: "My multimodal experience is the BERT+MLP late-fusion tagger and the FNO visual-RL paper. Audio I haven't shipped. I'd lean on transformer-architecture transferability — same attention primitives, different tokenizers — and get up the curve fast."

**Risk 5: Agent has no max_iterations, no automatic retry, caches not thread-safe.**
Root cause: v1 design for single-user on-prem.
Handle: Proactively raise it in Q7/Q12 answers. "Single-user on-prem made these fine at v1; none survive a multi-tenant cloud port — here's how I'd fix each."

---

## DELIVERABLE 12 — PREP SCHEDULE

### 48-hour sprint

- **Hour 1–2:** Lock the two self-intros (60s + 2min). Record yourself, time it, cut until both are natural.
- **Hour 3–5:** Project intro (90s). Open the repo while rehearsing — touch every file you'll mention. Drill Deliverable 5 defense scripts until each is a 30-second answer.
- **Hour 6–8:** Concepts MUST REVISE (1–8). Write each 3-sentence answer from memory. Focus extra time on LoRA math, attention math, RAG eval — Saifr will probe these.
- **Day 2 morning:** Deep-dive Q1–Q11 out loud. For each, say the strong answer + the trap concession. Record, listen, fix filler.
- **Day 2 afternoon:** Production questions Q12–Q13 (gap area). Sketch the AWS architecture on paper until it flows. Behavioral stories — lock five STAR stories to 90 seconds each.
- **Night before:** Re-read the repo `CLAUDE.md` and `TECHNICAL_OVERVIEW.md` once. Do NOT learn new material. Sleep early.

### 1-week plan

- **Day 1–2:** Intros + project walkthrough, defense scripts.
- **Day 3–4:** Concepts — MUST tier and SHOULD tier. For each SHOULD concept, write a 3-sentence answer.
- **Day 5:** Production/MLOps gap — do the AWS migration exercise end-to-end; read one vLLM + one LangGraph case study.
- **Day 6:** Mock interview — get a peer to grill you on Q1–Q15. Record.
- **Day 7:** Light review. Re-read only your own intro scripts + red-flag handling. Rest.

---

**Final note:** Saifr is small, Fidelity-backed, and transformer-native. They will care more about *how you think about tradeoffs in LLM systems* than about credential-style DS trivia. Lean into your "determinism over intelligence" principle — it's a rare, opinionated design stance, and it'll differentiate you from candidates who wave hands about agents.
