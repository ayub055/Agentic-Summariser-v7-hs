# JP Morgan Interview — Introduction Scripts (All 6 Frameworks)

Target: **JP Morgan — Home Lending Data & Analytics** (Origination & Servicing)
Anchor project: **Kotak Agentic Reader** (code in current repo root)
Classical-ML anchor: TCS insurance claim-frequency (XGBoost + SHAP), Kotak SBERT income estimation, IndicBERT-LoRA NER

Companion doc: `docs/prep/jpmorgan_prep.md` (concepts + deep-dives). This file is **scripts only** — speak them out loud, time them.

---

## FRAMEWORK 1 — Technical Self Introduction

### 30-second version (recruiter / elevator)

> I'm a Data Scientist at Kotak Mahindra Bank, ~22 months in, working on credit intelligence for 60M+ customers across origination and servicing. My stack spans classical ML — XGBoost scorecards with SHAP at TCS — plus GenAI and agentic systems at Kotak: a LangChain agentic pipeline for credit decisioning, SBERT income estimation driving ₹180Cr+ monthly disbursals, and IndicBERT fine-tuned via LoRA for applicant address NER. I also have an ICCV 2025 paper on Fourier Neural Operators for visual RL. JP Morgan's Home Lending mandate — classical ML plus GenAI plus agentic — is exactly the mix I've been working in, and the regulated-lending framing maps 1:1 to what I ship today.

### 90-second version (technical screen)

> **Past:** ~3 years of applied ML in regulated finance. Started at TCS on an XGBoost claim-frequency model for insurance pricing — used SHAP for per-feature contribution audits and cut loss ratio by 9%. Parallel research track: ICCV 2025 paper replacing CNN encoders with Fourier Neural Operators in visual RL, integrated with PPO, A2C, and Rainbow on CARLA and Atari.
>
> **Present:** At Kotak Mahindra Bank since July 2024, four shipped projects on the credit intelligence team. (1) **Kotak Agentic Reader** — LangChain-based 5-stage agentic pipeline for natural-language credit decisioning over banking transactions and CIBIL bureau data; dual-model Ollama orchestration (Mistral for intent, llama3.2 for narration), 25+ deterministic analytics tools, ~400x throughput lift for the hindsighting team. Core design principle: **determinism over intelligence** — LLMs never touch numbers, only narration. (2) **Affluence & Income Intelligence** — SBERT hybrid DL stack for salary detection, driving ₹180Cr+ monthly disbursals; accuracy 47%→72%, bad rate 1.24%→0.75%. (3) **Banking Transaction Tagger** — BERT+MLP late-fusion encoder over 1.1B transactions, 25 classes, FAISS retrieval, Alexa-20B few-shot for rare categories; +45% coverage on Bills and e-Tax. (4) **Address Reachability** — IndicBERT fine-tuned via LoRA for NER, 82% token accuracy across Indic dialects; wrongful rejections 20%→7%.
>
> **Future:** I want to go deeper on regulated-domain agentic workflows at enterprise scale — multi-agent document processing, fair-lending-aware scorecards, and the MLOps discipline that comes with a firm at JP Morgan's scale.
>
> **Fit:** Everything JP Morgan Home Lending needs — classical supervised models (XGBoost), fine-tuning (BERT/SBERT/IndicBERT with LoRA), RAG and agentic workflows (LangChain, 25+ tools), regulated-lending audit posture — I've shipped. My Kotak pipeline is auditable by construction; that stance ports directly to OCC/CFPB-governed Home Lending origination and servicing.

---

## FRAMEWORK 2 — Technical Project Introduction (Kotak Agentic Reader)

### 30-second version

> Kotak Agentic Reader is a LangChain agentic pipeline for natural-language credit decisioning over banking transactions and CIBIL bureau data. The hindsighting team used to spend 5+ days per review pulling data by hand; my system produces the same report in minutes. Architecture: 5-stage pipeline — Mistral parses intent as strict JSON, a pure-Python planner validates and maps to 25+ deterministic tools, llama3.2 narrates the pre-computed numbers. Core principle: LLMs never generate numbers — only narration. Result: ~400x team throughput, zero data egress, full JSONL audit log per query.

### 90-second version

> **Problem:** Kotak's hindsighting team audits disbursed loans post-approval to catch bad underwriting. Each case was 5+ days of analyst time pulling banking transactions and CIBIL tradelines manually. KPI: analyst cases-per-day. Constraints: regulated PII can't leave the bank's network, and every decision must be reproducible for audit.
>
> **Data:** Two tab-separated sources — `data/rgs.csv` (banking transactions: `cust_id`, debit/credit flag, narration, amount, category) and `dpd_data.csv` (CIBIL tradelines: 99 columns including `loan_type_new`, `dpd_string`, `max_dpd`, `out_standing_balance`), plus `tl_features.csv` with 65+ pre-computed behavioral signals. Challenges: 100+ raw loan-type strings normalized to 13 canonical types via `LOAN_TYPE_NORMALIZATION_MAP` in `schemas/loan_type.py`; heavy NULL handling via `_safe_float` and `_safe_optional_int` helpers; noisy narrations.
>
> **Approach:** Baseline would have been a ReAct tool-use agent — rejected because audit logs must be reproducible and a ReAct loop can call different tools on different runs. Instead a 5-stage chain: `IntentParser` (Mistral, `format="json"`, temp=0, seed=42) → `QueryPlanner` (pure Python, validates customer_id against correct data source, maps `IntentType` → tool list via `INTENT_TOOL_MAP`) → `ToolExecutor` (dispatches 25+ tools, fail-soft, returns `ToolResult`) → `TransactionInsights` (llama3.2, conditional on intent, cached) → `Explainer` (llama3.2, streams). Risk logic lives in `pipeline/reports/key_findings.py` — 40+ threshold rules comparing against named constants in `config/thresholds.py`. Pydantic at stage boundaries (`ParsedIntent`, `CustomerReport`, `ToolResult`), dataclasses internally (`BureauLoanFeatureVector`, `TradelineFeatures`) for `asdict()` serialization.
>
> **Results:** ~400x per-day throughput. Full JSONL audit log in `logs/audit_*.jsonl`. Zero data egress via on-device Ollama. Analyst team adopted it as their primary tool.
>
> **Learnings:** Hardcoded `INTENT_TOOL_MAP` doesn't scale past ~50 tools — v2 migration to LangGraph with a constrained router node. Module-level caches aren't thread-safe — fine for single-session on-prem, would break in a multi-tenant port. No formal eval harness for intent parsing — only a confidence heuristic; would add a labeled (query, intent) gold set and train a DistilBERT classifier with isotonic calibration. [ASK USER: confirm P50/P95 latency + intent top-1 accuracy]

---

## FRAMEWORK 3 — Business / Product Introduction (60s, non-technical)

> Home loans that go bad cost banks a lot of money, so banks do what's called "hindsighting" — going back and figuring out why a loan that defaulted ever got approved in the first place. At Kotak, this review was a bottleneck: every single case took an analyst about a week because they had to pull and read the customer's banking history and credit bureau data by hand. I built a system where the analyst types a plain-English question — "show me this customer's credit profile" — and gets back a full written report in minutes. It reads like a senior analyst wrote it, but the numbers come from strict calculations we can audit, not from an AI that might make things up. The team now works about 400 times faster per day, they catch bad lending patterns much sooner, and because the whole system runs on the bank's own servers, no customer data ever leaves. Same team, far more loans reviewed, much faster corrective action. That's exactly the Home Lending origination-and-servicing problem at scale.

---

## FRAMEWORK 4 — "Why X over Y" Defense Scripts

Every major decision in the repo — rehearse these as 30-second answers.

### Q: Why a deterministic chain with `INTENT_TOOL_MAP` instead of a ReAct tool-calling agent?
> **Context:** regulated credit decisioning, per-query audit log is a hard requirement. **Options:** ReAct agent (flexible, non-deterministic, hard to audit) vs fixed intent-to-tool routing (rigid, reproducible). **Decision:** deterministic routing — same query produces the same tool-call sequence, so compliance can replay any audit line. **Tradeoff:** adding new capabilities requires a map edit; v2 I'd migrate to LangGraph with a router node that uses constrained LLM output for ambiguous intents while keeping hard routes for report generation.

### Q: Why Ollama / local models instead of cloud APIs (OpenAI, Claude, Bedrock)?
> **Context:** banking PII under Indian data-localisation rules. **Options:** cloud (better reasoning, lower latency variance) vs on-prem (zero egress, offline, private). **Decision:** local via Ollama, accepting 5–10s per-query latency because the business constraint was no-egress, not reasoning quality. Specifically, the LLM only narrates pre-computed numbers — GPT-4-class reasoning wouldn't improve correctness. **Tradeoff:** narration is sometimes clunky. At JP Morgan I'd use Bedrock Claude or an internal LLM gateway — private VPC endpoints give both quality and data boundary.

### Q: Why two models (Mistral + llama3.2) instead of one?
> **Context:** intent parsing needs strict JSON; narration needs flowing prose. **Options:** one generalist model (compromises both) vs two specialists. **Decision:** Mistral with `format="json"` reliably produces valid JSON — malformed output crashes the Pydantic parser, so reliability > marginal prose quality. llama3.2 is better at Hinglish narration. **Tradeoff:** ~500MB extra RAM, negligible on-prem. If constrained to one model I'd use llama3.2 with Outlines or grammar-constrained decoding.

### Q: Why pure-threshold rules in `key_findings.py` instead of LLM-generated risk scores?
> **Context:** regulated lending; every score must be reviewable by risk/MRM. **Options:** LLM risk labels (flexible, non-deterministic, unauditable) vs threshold rules (rigid, auditable). **Decision:** 40+ threshold rules, every constant named in `config/thresholds.py`; same input always produces the same finding. **Tradeoff:** can't capture subtle composite patterns without explicit composite rules — I've added ~5 composites (enquiries + new PL + high utilization, etc.). For JP Morgan Home Lending this is the right stance — adverse-action notices under Reg B require reason codes a regulator can audit.

### Q: Why late fusion (BERT + MLP) for the transaction tagger and not a single multimodal transformer?
> **Context:** raw narration strings + structured numerics (amount, balance, flags). **Options:** early fusion (tokenize numerics — loses magnitude), unified multimodal transformer (needs paired pretraining we didn't have), late fusion (reuse pretrained BERT, train fusion head). **Decision:** late fusion — BERT CLS embedding concatenated with MLP-projected numerics, ~10× less training data than a unified model. **Tradeoff:** no cross-modal attention; with more data I'd try FT-Transformer or TabTransformer.

### Q: Why LoRA on IndicBERT instead of full fine-tune for NER?
> **Context:** ~10k labeled NER spans across Indic dialects. **Options:** full FT (risks catastrophic forgetting of pretrained multilingual knowledge), LoRA (updates <1% of params, preserves pretrained grounding). **Decision:** LoRA targeting q_proj and v_proj, rank 8, alpha 16 — standard from the LoRA paper ablations, trains in ~1 hour on a single GPU. **Tradeoff:** small performance ceiling vs full FT; 82% token accuracy cleared the business threshold so the ceiling wasn't binding. [ASK USER: confirm actual r / α / target_modules]

### Q: Why SBERT over heuristic keywords for salary detection?
> **Context:** salary narrations vary widely ("SAL CR", "SALARY APR24", merchant-style strings). **Options:** keep heuristics (47% accuracy ceiling), SBERT embeddings + classifier. **Decision:** SBERT — heuristics miss semantically-similar-lexically-different narrations. **Tradeoff:** inference cost vs regex — worth it because at ₹180Cr monthly disbursal every 10bp of bad-rate improvement matters (1.24%→0.75%).

### Q: Why XGBoost for the TCS claim-frequency model, not Logistic Regression or a GLM (Poisson/Tweedie)?
> **Context:** heavy-tailed claim distributions, non-linear feature interactions, no strict Reg B-style adverse-action requirement on that portfolio. **Options:** GLM Poisson/Tweedie (interpretable, industry-standard for frequency), XGBoost (non-linear, better accuracy). **Decision:** XGBoost for accuracy lift, with SHAP for per-feature attribution to keep actuarial review comfortable. **Tradeoff:** loses the closed-form interpretability of a GLM; SHAP + feature-by-feature PDP plots gave enough transparency to pass internal review. For a regulated US mortgage origination scorecard I'd reconsider and lead with Logistic Regression / scorecard for adverse-action compliance.

### Q: Why FPDF + Jinja2 for rendering instead of a BI dashboard (Tableau/PowerBI)?
> **Context:** reports needed to be self-contained audit artifacts. **Options:** BI dashboard (online, dynamic, re-filterable) vs static PDF + HTML (frozen, reproducible). **Decision:** static PDFs — audit trails require frozen artifacts a regulator can file; a dashboard that can be re-filtered later isn't an audit record. **Tradeoff:** no interactivity; mitigated by also producing HTML with Chart.js for analyst exploration.

### Q: Why random split on early SBERT salary experiments — and why did you switch?
> **Context:** early iteration, temporal dynamics not top-of-mind. **Options:** random vs temporal. **Decision (initial):** random — convenient but wrong for temporal data. Val F1 looked strong, production underperformed. Root-caused to temporal leakage and switched to a strict time-series split (T-12..T-3 train, T-3..T-1 val, T test). **Tradeoff:** honest 47%→72% metric against temporal test; learning was "always temporal split for transactional data," and that's now my default.

---

## FRAMEWORK 5 — STAR Behavioral Stories (JP Morgan lens)

### Story 1 — "Tell me about a time you worked on a regulated/audited ML project."
- **S:** Kotak credit decisioning; regulated banking PII; audit log per-query was required.
- **T:** Design an agentic system whose every output was reproducible by compliance.
- **A:** Separated LLM (narration) from decision logic (deterministic threshold rules); Pydantic-typed contracts at each stage so every intermediate was inspectable; JSONL audit log per query capturing intent, plan, tool calls, outputs, final narration; fail-soft so partial failures never produce silent wrong answers.
- **R:** Zero compliance escalations in the operating period; analyst team adopted as primary tool; ~400x throughput.

### Story 2 — "A model you built was failing in production. Walk me through it."
- **S:** First SBERT salary-detection baseline; val F1 inflated; production signal was worse than expected.
- **T:** Root-cause and fix before broader rollout.
- **A:** Audited the data pipeline, found random train/test split leaked future months into train. Re-ran with strict temporal split. Trained on T-12..T-3, validated T-3..T-1, tested T. Metrics dropped on val but prod matched. Documented the leakage pattern as a team-level rule.
- **R:** Honest 47%→72% accuracy claim; downstream bad rate 1.24%→0.75%; no production incidents during the ₹180Cr/month-disbursal cutover.

### Story 3 — "Describe a time you balanced model performance with business constraints."
- **S:** Stakeholder asked for an LLM-generated numeric "risk score" on the hindsighting report.
- **T:** Ship something useful without violating audit requirements.
- **A:** Showed two consecutive prompt runs producing different scores on identical input; translated into compliance language; proposed `key_findings.py` with 40+ threshold rules as the scoring layer, LLM restricted to narration.
- **R:** Team aligned; shipped; no MRM/audit pushback; pattern is now the template for any LLM-touched decisioning work internally.

### Story 4 — "Describe a cross-functional delivery under a tight deadline."
- **S:** Leadership asked for an agentic reader v0 in ~3 weeks; I hadn't shipped LangChain before.
- **T:** Go from zero to a production-grade 5-stage pipeline without cutting audit corners.
- **A:** Read LCEL + Ollama docs in 2 days; prototyped on synthetic data in week 1; iterated Pydantic contracts with analyst users in week 2; ran integration tests on real cases in week 3; socialized the "determinism over intelligence" principle explicitly with risk.
- **R:** Shipped v1 on time with full audit logging; same architecture still in production.

### Story 5 — "Time you communicated uncertainty to leadership."
- **S:** "400x throughput" number needed to go into a leadership deck.
- **T:** Present honestly without overclaiming.
- **A:** Framed it as workflow throughput (days → minutes), not query QPS; provided per-query P50/P95 separately; explicitly flagged that single-user on-prem scaling assumptions don't hold for multi-tenant.
- **R:** Leadership got the headline number + the caveats; no surprise when infra questions came up later.

---

## FRAMEWORK 6 — Opening Hook (Panel Version)

> **Hook:** "Banks lose money on loans that should never have been approved. And figuring out *why* a loan went bad — that's a multi-day manual review for every single case. At Kotak, that one workflow was the biggest bottleneck in how fast the bank could react to bad lending patterns."
>
> **Anchor:** "I built Kotak Agentic Reader — a LangChain agentic pipeline where an analyst types a plain-English question and gets an audit-clean credit report in minutes. It's a 5-stage chain where LLMs never touch numbers; numbers come from deterministic tools, LLMs only narrate. The guiding principle is **determinism over intelligence**, and it exists specifically because regulated lending needs reproducible outputs. I'll walk you through the architecture, the key design tradeoffs, and what I'd change for a JP Morgan-scale port."
>
> **Handoff:** "I'll start with the business context, then go deep on whichever layer interests this panel most — the agentic pipeline, the fine-tuned BERT/SBERT/IndicBERT work, or the production tradeoffs."

---

## NUMBERS TO NAIL DOWN BEFORE INTERVIEW

- [ASK USER] Kotak Agentic Reader: **P50/P95 end-to-end query latency**
- [ASK USER] Intent parser: **held-out top-1 accuracy** on a labeled set (and fallback-trigger rate)
- [ASK USER] IndicBERT LoRA: **actual r, α, target_modules, LR, warmup ratio**
- [ASK USER] SBERT salary detection: **macro-F1 on temporal test**, class imbalance ratio
- [ASK USER] Transaction tagger: **macro-F1 across 25 classes on the 50k stratified eval set**, confusion-matrix top-3 confused pairs
- [ASK USER] TCS claim-frequency: **Gini / deviance vs GLM baseline**, SHAP top-5 features

---

**Key JP Morgan framing to lean on in every answer:**

1. **"Determinism over intelligence"** — your shipped design principle. Cite it explicitly. Regulated-bank interviewers will remember it.
2. **"Auditable by construction"** — every stage has a typed contract, full JSONL log, reproducible outputs. Maps directly to OCC/CFPB/Reg B expectations.
3. **"LLMs narrate, they don't decide"** — the correct stance for Home Lending origination. Anchors you as someone who already thinks like a regulated-bank data scientist.
