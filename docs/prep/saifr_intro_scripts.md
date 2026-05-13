# DS Interview Prep — Introduction Scripts (All 6 Frameworks)

Target: **Saifr.ai** (Fidelity-funded compliance AI startup) | Anchor project: **Kotak Agentic Reader**

---

## FRAMEWORK 1 — Technical Self Introduction

### 30-second version (recruiter / elevator)

> I'm a Data Scientist at Kotak Mahindra Bank, ~22 months in, working at the intersection of transformers, agentic LLM systems, and production ML for 60M+ customers. Most recent work is Kotak Agentic Reader — a LangChain agentic pipeline with 25+ analytics tools that cut a 5-day hindsighting workflow to minutes. I also have an ICCV 2025 paper on Fourier Neural Operator encoders for visual RL. Saifr's transformer-native compliance stack is exactly where I want to go deeper.

### 90-second version (technical screen)

> **Past:** Data Scientist with ~3 years of applied ML experience — started at TCS on insurance pricing with XGBoost, then moved into deep learning and transformers at Kotak Mahindra Bank. Parallel research track gave me an ICCV 2025 paper on Fourier Neural Operators replacing CNN encoders in visual RL.
>
> **Present:** At Kotak since July 2024, on the credit intelligence team. My flagship is **Kotak Agentic Reader** — a LangChain-based 5-stage agentic pipeline for natural-language credit decisioning over banking and CIBIL bureau data, dual-model Ollama orchestration with Mistral and llama3.2, ~400x throughput lift for the hindsighting team. Before that I shipped an **SBERT-based income estimation system** driving ₹180Cr+ monthly disbursals — accuracy 47%→72%, bad rate 1.24%→0.75%. I also fine-tuned **IndicBERT via LoRA** for NER on Indic dialects, cutting wrongful rejections from 20% to 7%.
>
> **Future:** I want to go deeper on custom transformer architectures and LLM workflow design as a product — not as tooling around someone else's model.
>
> **Fit:** Saifr sits on Transformers applied to compliance content — which maps directly to what I've been doing: BERT, SBERT, IndicBERT, and LLM workflows in a regulated domain. My "determinism over intelligence" design principle — numbers from deterministic tools, LLMs only for narration — is exactly the kind of stance compliance AI needs.

---

## FRAMEWORK 2 — Technical Project Introduction (Kotak Agentic Reader)

### 30-second version

> Kotak Agentic Reader collapses a 5-day manual hindsighting review into a single natural-language query. Architecture: 5-stage LangChain pipeline — Mistral parses intent as JSON, a pure-Python planner validates and maps to 25+ deterministic tools, llama3.2 narrates the pre-computed numbers. LLMs never touch numbers — only narration. Result: ~400x throughput lift, zero data egress via on-device Ollama, full JSONL audit log.

### 90-second version

> **Problem:** Kotak's hindsighting team audits loans post-disbursal to catch bad underwriting. Each case took 5+ days of analyst work pulling banking transactions and CIBIL tradelines manually. The KPI was analyst-cases-per-day; the secondary constraint was that regulated data couldn't leave the bank's network.
>
> **Data:** Two tab-separated sources — `rgs.csv` for banking transactions (cust_id, debit/credit flag, narration, amount, category) and `dpd_data.csv` for CIBIL bureau tradelines (99 columns including `dpd_string`, `max_dpd`, `out_standing_balance`, `loan_type_new`) plus `tl_features.csv` with 65+ pre-computed behavioral signals. Challenges were messy narrations, 100+ raw loan-type strings that had to normalize to 13 canonical types via `LOAN_TYPE_NORMALIZATION_MAP`, and heavy NULL fields handled via `_safe_float` / `_safe_optional_int` helpers.
>
> **Approach:** Baseline would have been a ReAct agent loop; I rejected that because audit logs need reproducibility. Instead a **5-stage chain**: `IntentParser` (Mistral, `format="json"`, temp=0, seed=42) → `QueryPlanner` (pure Python, validates customer_id against correct data source, maps via `INTENT_TOOL_MAP`) → `ToolExecutor` (dispatches 25+ tools, fail-soft, returns `ToolResult`) → `TransactionInsights` (llama3.2, conditional on intent) → `Explainer` (llama3.2, streams to Streamlit). Core design principle: **determinism over intelligence** — all risk scoring lives in `key_findings.py` as 40+ threshold rules comparing against named constants in `config/thresholds.py`. Pydantic at stage boundaries, dataclasses internally.
>
> **Results:** ~400x team throughput on a per-day basis. Full JSONL audit log per query in `logs/audit_*.jsonl`. On-device via Ollama — zero data egress, audit-clean for a regulated domain.
>
> **Learnings:** Hardcoded `INTENT_TOOL_MAP` doesn't scale past ~50 tools — v2 I'd migrate to LangGraph with constrained tool selection in a router node. Module-level caches aren't thread-safe — fine for on-prem single-user, would break in a multi-tenant cloud port. No formal eval harness for intent parsing — only the confidence heuristic; I'd add a labeled eval set and retrain a DistilBERT classifier with isotonic calibration. [ASK USER: confirm P50/P95 latency you observed]

---

## FRAMEWORK 3 — Business / Product Introduction (60s)

> Banks do something called "hindsighting" — they look back at loans that went bad to figure out why they ever got approved. At Kotak, this was a bottleneck: every single review took an analyst about a week, because they had to pull and read a customer's banking history and credit bureau data by hand. I built a system where the analyst just types a plain-English question — "show me this customer's credit profile" — and gets back a full report with a written summary in seconds. It behaves like a junior analyst that's always available. The team now works roughly 400 times faster per day, they can catch lending mistakes much earlier, and because the system runs on Kotak's own servers, none of the customer data ever leaves the bank. Same team, far more loans reviewed, much faster corrective action on bad patterns.

---

## FRAMEWORK 4 — "Why X over Y" Defense Scripts

### Q: Why local Ollama instead of OpenAI/Claude?
> **Context:** regulated banking PII. **Options:** cloud APIs (better reasoning, lower latency variance) vs local (privacy, zero data egress, offline). **Decision:** local via Ollama, accepting 5–10s query latency because the business constraint was auditability and no-egress, not LLM reasoning quality. Specifically, the LLM only narrates numbers the deterministic tools have already computed — so GPT-4-class reasoning wouldn't improve correctness, only prose quality. **Tradeoff:** narration is occasionally clunky; I'd revisit if we ran it in a managed cloud with bank-approved private endpoints.

### Q: Why two models (Mistral + llama3.2) instead of one?
> **Context:** intent parsing needs strict JSON; narration needs flowing prose. **Options:** one generalist (compromises both) vs two specialists. **Decision:** Mistral with `format="json"` forces valid JSON structurally — critical because malformed output crashes the Pydantic parser. llama3.2 is better at Hinglish narration. **Tradeoff:** extra ~500MB RAM, negligible on-prem. If I had to single-model I'd use llama3.2 with Outlines for grammar-constrained output.

### Q: Why hardcoded `INTENT_TOOL_MAP` instead of a ReAct tool-calling agent?
> **Context:** 25 tools, regulated lending, audit-log requirement. **Options:** ReAct (flexible, non-deterministic) vs deterministic routing (rigid, reproducible). **Decision:** deterministic — same query must produce the same tool-call sequence so compliance can reproduce any audit-log line. **Tradeoff:** rigidity when adding tools; v2 I'd go to LangGraph with a constrained router node — keep deterministic routing for report generation, allow dynamic selection only for exploratory queries.

### Q: Why pure threshold rules in `key_findings.py` instead of LLM-generated risk summaries?
> **Context:** regulated lending, rules must be reviewable by risk officers. **Options:** LLM risk labels (flexible, non-deterministic, unauditable) vs thresholded rules (rigid, auditable). **Decision:** 40+ threshold rules, every constant named in `config/thresholds.py`, same input always produces the same finding. **Tradeoff:** can't capture subtle composite patterns without adding explicit composite rules — I've already added ~5 (enquiries + new PL + high utilization etc.); further composites require manual engineering rather than model learning.

### Q: Why late fusion (BERT + MLP) for the transaction tagger, not a single multimodal transformer?
> **Context:** raw narration strings + structured numerics (amount, balance, flags). **Options:** early fusion (tokenize numerics — loses magnitude), unified multimodal transformer (needs paired pretraining data we didn't have), late fusion (reuse pretrained BERT, train only fusion head). **Decision:** late fusion — BERT CLS embedding concatenated with MLP-projected numerics, 10× less training data than a unified model. **Tradeoff:** no cross-modal attention. With more data I'd try FT-Transformer or TabTransformer.

### Q: Why LoRA on IndicBERT instead of full fine-tune for NER?
> **Context:** ~10k labeled NER spans across Indian dialects. **Options:** full FT (risks catastrophic forgetting of pretrained multilingual knowledge), LoRA (updates <1% of params, preserves Indic grounding). **Decision:** LoRA targeting q_proj/v_proj, rank 8, alpha 16 — standard config from the LoRA paper's ablations, trains in ~1 hour on a single GPU. **Tradeoff:** small performance ceiling vs full FT; 82% token accuracy was above the business threshold so the ceiling wasn't a blocker. [ASK USER: confirm actual rank/alpha]

### Q: Why SBERT over heuristic keywords for salary detection?
> **Context:** salary narrations vary wildly — "SAL CR", "SALARY APR24", merchant-style strings. **Options:** keep keyword heuristics (47% accuracy — known ceiling), SBERT embeddings + classifier (semantic clustering). **Decision:** SBERT because heuristics missed semantically-similar-but-lexically-different narrations. **Tradeoff:** inference cost vs regex — worth it because at ₹180Cr monthly disbursal, every 10bp of bad-rate improvement matters (1.24%→0.75%).

### Q: Why FPDF + Jinja2 rendering instead of a BI tool?
> **Context:** reports needed to be self-contained PDFs auditors could file. **Options:** BI tool (Tableau/PowerBI — online, dynamic), FPDF + Jinja2 (offline artifacts, reproducible). **Decision:** static PDFs because audit trails require frozen artifacts — a dashboard that can be re-filtered later is not an audit record. **Tradeoff:** no interactivity; mitigated by also producing HTML with Chart.js for analyst exploration.

---

## FRAMEWORK 5 — STAR Behavioral Stories

### Story 1 — "Tell me about a time you disagreed with a stakeholder on metrics."
- **Situation:** Hindsighting team at Kotak asked me to have the LLM output a numeric "risk score" as part of the report.
- **Task:** Decide whether LLM-generated scoring was appropriate for a regulated lending audit workflow.
- **Action:** (1) Pulled the compliance requirement — every score must be reproducible and signed off. (2) Showed two A/B runs of the same prompt producing different scores on identical input. (3) Proposed the alternative: `key_findings.py` with 40+ threshold rules, LLM narrates but doesn't score.
- **Result:** Team accepted the redesign; reports shipped with rule-based scoring and LLM narration, zero compliance pushback post-launch.

### Story 2 — "Time your offline eval disagreed with production."
- **Situation:** First SBERT baseline for salary detection — val F1 looked strong.
- **Task:** Diagnose the gap when early production signals were worse than val.
- **Action:** Audited the data split, found random split leaked future months into train. Reran with strict temporal split (T-12..T-3 train, T-3..T-1 val, T test). Val dropped, prod matched.
- **Result:** Correct eval produced 47%→72% accuracy claim honestly; downstream bad rate 1.24%→0.75% validated it was real.

### Story 3 — "Time you had to learn something new fast."
- **Situation:** Kotak leadership asked for an agentic reader v0 in ~3 weeks; I hadn't shipped LangChain before.
- **Task:** Go from zero to production-grade 5-stage agentic pipeline.
- **Action:** Read LCEL + Ollama docs in 2 days, prototyped on synthetic data in week 1, iterated the Pydantic contracts with the team in week 2, ran integration tests with real cases in week 3.
- **Result:** Shipped v1 with 5-stage chain, Mistral+llama3.2 dual-model, 25+ tools. Same architecture still in production.

### Story 4 — "Time you found a bug late and handled it."
- **Situation:** Discovered during a demo that `_REPORT_CACHE` was a process-global dict with no TTL — stale reports could be served if upstream data refreshed mid-session.
- **Task:** Decide between patching ad-hoc and raising visibility.
- **Action:** Raised it with the team as a known limitation, added `invalidate_customer_cache()` for manual purge, documented in `CLAUDE.md` that the system is single-session safe only, tagged it for v2 Redis migration.
- **Result:** No stale-data incidents in the restricted deployment; explicit tech-debt entry for the cloud port.

### Story 5 — "Time you communicated uncertainty to leadership."
- **Situation:** The "400x throughput" number needed to go into a leadership deck.
- **Task:** Present honestly without overclaiming.
- **Action:** Framed it as workflow throughput (days → minutes), not a latency benchmark; provided the per-query P50/P95 separately; flagged that single-user on-prem scaling assumptions don't hold for multi-tenant.
- **Result:** Leadership got the headline number + the caveats, no surprise when infra questions came up later.

---

## FRAMEWORK 6 — Opening Hook (Panel Version)

> **Hook:** "Banks lose money on loans that should never have been approved — and figuring out *why* a loan went bad is a multi-day manual job for every single case. At Kotak, that one workflow was the bottleneck in how fast we could react to bad lending patterns."
>
> **Anchor:** "I built Kotak Agentic Reader — an on-device LLM-powered system that turns that multi-day review into a single natural-language query. It's a 5-stage chain where LLMs never touch numbers; they only narrate results that deterministic tools have computed. I'll walk you through the architecture, the reasoning behind the key design choices, and what I'd rebuild if I did it again."
>
> **Handoff:** "I'll start with the business context, then go as deep as you want on the pipeline, the fine-tuned BERT/SBERT/IndicBERT work, or the production tradeoffs — whichever interests this group most."

---

### Missing numbers to nail down before interview

- [ASK USER] Kotak Agentic Reader: **P50/P95 latency** (per-query, end-to-end)
- [ASK USER] Intent parser: **held-out top-1 accuracy** on a labeled set
- [ASK USER] IndicBERT LoRA: **actual rank, alpha, target_modules, LR, warmup**
- [ASK USER] SBERT salary detection: **macro-F1 on temporal test set**
- [ASK USER] Transaction tagger: **macro-F1 across 25 classes on the 50k eval set**

Fill these in before the interview — interviewers at a transformer-native startup will ask for specifics.
