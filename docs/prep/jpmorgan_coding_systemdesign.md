# JP Morgan Interview — SQL, Python & ML System Design

Companion to `jpmorgan_prep.md` (concepts) and `jpmorgan_intro_scripts.md` (intros). This doc covers the **coding and system-design rounds** — the JD explicitly lists "Strong Python & SQL," and JP Morgan DS loops almost always include one coding round + one ML-system-design round.

---

# PART 1 — SQL (expect a live round)

JP Morgan DS SQL questions are standard analytical — window functions, self-joins, cohort queries, dedup. Banking-data flavor. Practice until these are muscle memory.

## 1.1 Patterns you must know cold

### Window functions

```sql
-- Rank customers by transaction amount within each category
SELECT cust_id, category, tran_amt,
       ROW_NUMBER() OVER (PARTITION BY category ORDER BY tran_amt DESC) AS rn,
       RANK()       OVER (PARTITION BY category ORDER BY tran_amt DESC) AS rk,
       DENSE_RANK() OVER (PARTITION BY category ORDER BY tran_amt DESC) AS drk
FROM transactions;
```

**Know the difference:**
- `ROW_NUMBER` — unique 1,2,3 (ties broken arbitrarily)
- `RANK` — ties share rank, gaps after (1,1,3)
- `DENSE_RANK` — ties share rank, no gaps (1,1,2)

### Running totals / moving averages

```sql
-- 3-month rolling sum of EMI payments per customer
SELECT cust_id, month,
       SUM(emi_amt) OVER (
         PARTITION BY cust_id
         ORDER BY month
         ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS rolling_3m_emi
FROM emi_payments;
```

### Self-join for consecutive events

```sql
-- Days between consecutive transactions per customer
SELECT cust_id, tran_date,
       tran_date - LAG(tran_date) OVER (
         PARTITION BY cust_id ORDER BY tran_date
       ) AS days_since_prev
FROM transactions;
```

### Top-N per group

```sql
-- Top 3 spending categories per customer
WITH ranked AS (
  SELECT cust_id, category, SUM(tran_amt) AS total,
         ROW_NUMBER() OVER (
           PARTITION BY cust_id ORDER BY SUM(tran_amt) DESC
         ) AS rn
  FROM transactions
  WHERE dr_cr_indctor = 'D'
  GROUP BY cust_id, category
)
SELECT cust_id, category, total
FROM ranked
WHERE rn <= 3;
```

### Cohort retention

```sql
-- Month-1 retention by signup cohort
WITH cohorts AS (
  SELECT cust_id, DATE_TRUNC('month', signup_date) AS cohort_month
  FROM customers
),
activity AS (
  SELECT c.cohort_month,
         DATE_TRUNC('month', t.tran_date) AS active_month,
         COUNT(DISTINCT t.cust_id) AS active_users
  FROM cohorts c
  JOIN transactions t USING (cust_id)
  GROUP BY 1, 2
)
SELECT cohort_month, active_month, active_users,
       active_users * 1.0 / FIRST_VALUE(active_users) OVER (
         PARTITION BY cohort_month ORDER BY active_month
       ) AS retention_pct
FROM activity;
```

### Deduplication — keep most recent per key

```sql
-- Latest CIBIL pull per customer
SELECT *
FROM (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY crn ORDER BY pull_date DESC
  ) AS rn
  FROM cibil_pulls
) t
WHERE rn = 1;
```

### Date math — active tradelines by month

```sql
-- Count tradelines active in each of last 24 months (the monthly-exposure pattern in your code)
WITH months AS (
  SELECT GENERATE_SERIES(
    DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '23 months',
    DATE_TRUNC('month', CURRENT_DATE),
    '1 month'
  ) AS month_start
)
SELECT m.month_start, COUNT(t.tradeline_id) AS active_tradelines
FROM months m
LEFT JOIN tradelines t
  ON t.date_opened <= m.month_start + INTERVAL '1 month' - INTERVAL '1 day'
 AND (t.date_closed IS NULL OR t.date_closed >= m.month_start)
GROUP BY m.month_start
ORDER BY m.month_start;
```

## 1.2 Likely SQL interview questions (JP Morgan flavor)

**Q1. From a `loan_payments` table, find customers who missed 2+ consecutive monthly payments in the last 12 months.**

```sql
WITH monthly AS (
  SELECT cust_id, DATE_TRUNC('month', due_date) AS month,
         MAX(CASE WHEN paid_flag = 1 THEN 1 ELSE 0 END) AS paid
  FROM loan_payments
  WHERE due_date >= CURRENT_DATE - INTERVAL '12 months'
  GROUP BY 1, 2
),
flagged AS (
  SELECT cust_id, month, paid,
         SUM(paid) OVER (
           PARTITION BY cust_id ORDER BY month
           ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
         ) AS paid_in_2
  FROM monthly
)
SELECT DISTINCT cust_id
FROM flagged
WHERE paid_in_2 = 0;
```

**Q2. For each loan, compute DPD bucket as of today from a `dpd_monthly` table with one row per (loan, month, dpd_days).**

```sql
SELECT loan_id,
       CASE
         WHEN dpd_days = 0              THEN 'current'
         WHEN dpd_days BETWEEN 1 AND 29 THEN '1-29'
         WHEN dpd_days BETWEEN 30 AND 59 THEN '30-59'
         WHEN dpd_days BETWEEN 60 AND 89 THEN '60-89'
         ELSE '90+'
       END AS dpd_bucket
FROM (
  SELECT loan_id, dpd_days,
         ROW_NUMBER() OVER (PARTITION BY loan_id ORDER BY month DESC) AS rn
  FROM dpd_monthly
) t
WHERE rn = 1;
```

**Q3. Compute 30/60/90-day delinquency rate for each origination vintage (month of origination).**

```sql
SELECT DATE_TRUNC('month', origination_date) AS vintage,
       AVG(CASE WHEN max_dpd_90d >= 30 THEN 1.0 ELSE 0 END) AS rate_30_plus,
       AVG(CASE WHEN max_dpd_90d >= 60 THEN 1.0 ELSE 0 END) AS rate_60_plus,
       AVG(CASE WHEN max_dpd_90d >= 90 THEN 1.0 ELSE 0 END) AS rate_90_plus,
       COUNT(*) AS loans
FROM loans
GROUP BY 1
ORDER BY 1;
```

**Q4. "Given a transactions table, find customers whose average monthly debit in last 3 months is >2× their average over the prior 12 months."** — a typical spend-anomaly flag.

```sql
WITH monthly AS (
  SELECT cust_id, DATE_TRUNC('month', tran_date) AS month,
         SUM(CASE WHEN dr_cr_indctor = 'D' THEN tran_amt ELSE 0 END) AS debit
  FROM transactions
  GROUP BY 1, 2
),
agg AS (
  SELECT cust_id,
         AVG(CASE WHEN month >= CURRENT_DATE - INTERVAL '3 months'
                  THEN debit END) AS recent_3m,
         AVG(CASE WHEN month <  CURRENT_DATE - INTERVAL '3 months'
                   AND month >= CURRENT_DATE - INTERVAL '15 months'
                  THEN debit END) AS prior_12m
  FROM monthly
  GROUP BY cust_id
)
SELECT cust_id, recent_3m, prior_12m,
       recent_3m / NULLIF(prior_12m, 0) AS ratio
FROM agg
WHERE prior_12m > 0 AND recent_3m > 2 * prior_12m;
```

## 1.3 SQL gotchas interviewers probe

- **NULL in aggregates:** `COUNT(col)` skips NULLs, `COUNT(*)` doesn't. `AVG(col)` skips NULLs — bias if NULL isn't random.
- **NULL in joins:** `x = NULL` is never true; use `IS NULL` / `IS NOT DISTINCT FROM`.
- **`HAVING` vs `WHERE`:** `WHERE` filters rows before aggregation, `HAVING` after.
- **`UNION` vs `UNION ALL`:** `UNION` dedupes (slower), `UNION ALL` doesn't — use `UNION ALL` unless you need dedup.
- **Implicit casts:** comparing `VARCHAR` to `INT` — databases vary; be explicit.
- **Division:** `1/2 = 0` in integer division; cast: `1.0 * a / b` or `a::FLOAT / b`.

---

# PART 2 — Python coding (pandas / algorithms)

Expect 1–2 coding problems: usually **pandas data wrangling** or a **small algorithmic problem** tied to a DS use case.

## 2.1 Pandas patterns

### Groupby + transform vs aggregate

```python
# Aggregate: one row per group (collapses)
df.groupby('cust_id')['tran_amt'].sum()

# Transform: broadcast back to original shape (preserves rows)
df['cust_total'] = df.groupby('cust_id')['tran_amt'].transform('sum')
df['pct_of_cust_total'] = df['tran_amt'] / df['cust_total']
```

### Rolling window on panel data

```python
# 3-month rolling mean per customer — sort first
df = df.sort_values(['cust_id', 'tran_date'])
df['rolling_3m'] = (
    df.groupby('cust_id')['tran_amt']
      .rolling(window=3, min_periods=1)
      .mean()
      .reset_index(level=0, drop=True)
)
```

### Merge types — know the asof merge

```python
# asof merge: join each left row to the nearest-previous right row
# Useful for joining transactions to the latest CIBIL pull before the txn date
pd.merge_asof(
    transactions.sort_values('tran_date'),
    cibil_pulls.sort_values('pull_date'),
    left_on='tran_date',
    right_on='pull_date',
    by='cust_id',
    direction='backward',
)
```

### Pivot + melt

```python
# Long → wide
pivot = df.pivot_table(
    index='cust_id', columns='category',
    values='tran_amt', aggfunc='sum', fill_value=0
)

# Wide → long
long = pivot.reset_index().melt(
    id_vars='cust_id', var_name='category', value_name='total'
)
```

### Dealing with large data — chunking

```python
# If the file doesn't fit in memory
chunks = []
for chunk in pd.read_csv('big.csv', chunksize=1_000_000):
    # pre-filter before keeping
    chunk = chunk[chunk['dr_cr_indctor'] == 'D']
    chunks.append(
        chunk.groupby('cust_id')['tran_amt'].sum()
    )
result = pd.concat(chunks).groupby(level=0).sum()
```

## 2.2 Likely Python interview problems

**Q1. Given a list of transactions, find the top-k merchants by total amount per customer.**

```python
from collections import defaultdict
import heapq

def top_k_merchants_per_customer(transactions, k):
    # transactions: list of (cust_id, merchant, amount)
    totals = defaultdict(lambda: defaultdict(float))
    for cust, merch, amt in transactions:
        totals[cust][merch] += amt

    result = {}
    for cust, m_totals in totals.items():
        result[cust] = heapq.nlargest(k, m_totals.items(), key=lambda x: x[1])
    return result
```

**Q2. Implement a simple LRU cache.** (Classic; JP Morgan will ask because your resume cites module-level caching.)

```python
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.cap = capacity
        self.cache: OrderedDict = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return -1
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.cap:
            self.cache.popitem(last=False)
```

**Q3. Given a stream of (timestamp, amount) payment events, detect spikes where amount > 3σ above the trailing-30-event mean.**

```python
from collections import deque
import math

class SpikeDetector:
    def __init__(self, window: int = 30, sigma: float = 3.0):
        self.window = window
        self.sigma = sigma
        self.buf = deque(maxlen=window)

    def is_spike(self, amount: float) -> bool:
        if len(self.buf) < self.window:
            self.buf.append(amount)
            return False
        mean = sum(self.buf) / len(self.buf)
        var = sum((x - mean) ** 2 for x in self.buf) / len(self.buf)
        std = math.sqrt(var)
        spike = amount > mean + self.sigma * std
        self.buf.append(amount)
        return spike
```

**Q4. Write a function that computes cosine similarity between a query embedding and a matrix of doc embeddings, returning top-k.** (RAG retrieval primitive.)

```python
import numpy as np

def top_k_cosine(query: np.ndarray, docs: np.ndarray, k: int):
    q = query / (np.linalg.norm(query) + 1e-12)
    d = docs / (np.linalg.norm(docs, axis=1, keepdims=True) + 1e-12)
    scores = d @ q
    top_idx = np.argpartition(-scores, k)[:k]
    # Sort the k by score
    top_idx = top_idx[np.argsort(-scores[top_idx])]
    return top_idx, scores[top_idx]
```

## 2.3 Python gotchas

- **Mutable default args:** `def f(x, acc=[])` — `acc` is shared across calls. Use `None` + `acc = acc or []`.
- **`copy` vs `deepcopy`:** `copy` shallow, references to nested objects shared.
- **Generator exhaustion:** iterating a generator twice yields nothing the second time.
- **`is` vs `==`:** `is` is identity, `==` is equality. Use `is` only for `None`, `True`, `False`.
- **GIL:** CPython's GIL limits CPU-bound threading; use multiprocessing or async for IO.

---

# PART 3 — ML System Design (the headline round)

JP Morgan DS system-design rounds follow a pattern:

**Structure to use for every question:**
1. **Clarify** — business goal, constraints, scale, SLAs.
2. **Problem framing** — classification/regression/ranking/generation; online/batch; labels.
3. **Data** — sources, features, labels, leakage concerns, freshness.
4. **Model** — baseline, candidate models, justification.
5. **Evaluation** — metric + offline/online + fair-lending.
6. **Serving** — batch vs real-time, latency, cost, rollout.
7. **Monitoring** — drift, performance, fairness, alerts.
8. **Risk/MRM** — auditability, adverse-action, explainability.

---

## 3.1 Case Study: Design an Early-Warning Model for Home Loan Default (Servicing)

**Ask:** "Design a model to flag Home Lending loans at risk of 90+ DPD in the next 6 months."

**Clarify:**
- Population: active loans only, minimum 6 months seasoned.
- Action: flagged loans routed to the loss-mitigation team for proactive outreach.
- Business metric: reduction in 90+ DPD roll-rate vs control.
- Volume: ~2M active loans; batch daily scoring acceptable.

**Framing:** Binary classification. Label = "loan will reach 90+ DPD within 6 months of scoring date." Temporal labels — use snapshots.

**Data:**
- **Loan-level:** current DPD, LTV, FICO, origination vintage, product type, rate, term, remaining principal.
- **Payment behavior:** months since last missed, number of 30/60-day hits in last 12m, rolling payment ratio, escrow delinquency.
- **Macro:** local HPI trend, unemployment rate by ZIP, interest-rate environment.
- **Customer:** other-account behavior if cross-bank visibility (credit card, deposit), bureau refresh.
- **Snapshots:** one row per (loan, snapshot_month). Label = 90+ DPD in the [t+1, t+6] window. Train on snapshots where t+6 is observable.
- **Leakage guards:** no post-outcome features, no payment data from the label window, embargo period between train and val in time.

**Model:**
- **Baseline:** Logistic regression on 10–15 hand-picked features — cheap to ship, easy to explain.
- **Production candidate:** XGBoost (gradient boosting) — handles interactions, robust to missing, tabular SOTA.
- **Why not deep learning:** tabular, N ~ a few M, features are well-engineered; XGBoost will match or beat with 1/10 the serving cost.
- **Calibration:** Platt scaling or isotonic on a holdout — the score feeds a downstream action threshold.

**Evaluation:**
- **Offline:** PR-AUC primary (imbalanced), AUC secondary, Brier score for calibration. Recall@precision=30% or recall@top-5% — action-oriented operating points.
- **Fair-lending:** disparate impact ratio across protected classes on action rates, adverse-impact testing per OCC/Reg B. Remove direct proxies (ZIP can be a race proxy — evaluate carefully).
- **Backtest:** by vintage and by macro regime (2020 pandemic cohort vs 2023 cohort).
- **Online:** A/B — treatment gets proactive outreach, control doesn't; primary metric 6m-roll-rate difference, secondary NPS/churn.

**Serving:**
- **Batch:** nightly scoring job (Airflow / SageMaker Pipelines) → writes to loan-level table → servicing UI consumes.
- **Storage:** model in SageMaker Model Registry; feature store (Feast / SageMaker FS) for reproducible features.
- **Shadow first:** 4 weeks shadow before champion-challenger; 10% → 50% → 100% rollout on the action side.

**Monitoring:**
- **Input drift:** per-feature KS test vs training distribution; alert on sustained drift.
- **Performance drift:** rolling 6m-actual 90+ rate by decile.
- **Calibration drift:** reliability diagram, ECE monthly.
- **Fair-lending:** monthly disparate-impact monitoring; part of regulatory filings.
- **Action quality:** flag-to-cure rate, false-positive outreach volume (cost driver).

**Risk/MRM:**
- **Model card:** data lineage, features, training procedure, known limitations.
- **Adverse-action:** flagging isn't a credit-adverse action (no decline), but outreach decisions still need documentation.
- **Explainability:** SHAP top-3 per-loan for case notes; global feature importance for the model card.
- **Retrain cadence:** quarterly, or triggered by drift.

---

## 3.2 Case Study: Design a Multi-Agent System for Loan Document Processing (Origination)

**Ask:** "Design an agentic system that ingests borrower documents (W-2, tax returns, bank statements, pay stubs) and produces a structured underwriting packet."

**Clarify:**
- Volume: ~1000 applications/day.
- SLA: packet ready within 30 min of last doc upload.
- Hard requirement: every extracted field traceable to a document span; human underwriter approves the final packet.
- Accuracy bar: >95% field-level accuracy on income computation (business-critical).

**Framing:** Pipeline with multiple agents, each specialized. Human-in-the-loop on any low-confidence extraction.

**Architecture (use LangGraph — explicit state machine, fits MRM expectations):**

```
┌────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│ Ingest     │───▶│ Classify     │───▶│ Extract      │───▶│ Validate    │───▶│ Underwrite
│ Agent      │    │ Agent        │    │ Agent (per   │    │ Agent       │    │ Agent    
│ (OCR+      │    │ (doc type)   │    │ doc type)    │    │ (cross-doc) │    │ (rules)  │
│  layout)   │    │              │    │              │    │             │    │          │
└────────────┘    └──────────────┘    └──────────────┘    └─────────────┘    └────┬─────┘
                                                                                  │
                                                                          ┌───────▼──────┐
                                                                          │ Critic Agent │
                                                                          │ (audit chain)│
                                                                          └───────┬──────┘
                                                                                  │
                                                                           Human Review
```

**Agents:**

1. **Ingest Agent** — OCR (Textract / Tesseract) + layout parsing (LayoutLMv3). Output: structured text per page with bboxes.
2. **Classify Agent** — LLM classifies each doc: W-2, 1040, paystub, bank stmt, etc. Low-confidence → human queue.
3. **Extract Agent(s)** — One per doc type. W-2 extractor pulls Box 1, Box 3, employer EIN. Bank-statement extractor pulls deposits + running balance. Use constrained JSON output (function calling / Outlines).
4. **Validate Agent** — Cross-document consistency: does stated income on application match W-2 Box 1 within tolerance? Do bank deposits reconcile with pay frequency? **Deterministic rules**, not LLM.
5. **Underwrite Agent** — Applies policy rules (DTI, LTV, reserves). **Deterministic**. LLM not involved in decisioning.
6. **Critic Agent** — LLM reviews the full chain, flags contradictions or low-confidence steps for human review.

**Orchestration:** LangGraph. State object = `ApplicationPacket` (Pydantic). Explicit nodes, conditional edges, checkpoint after each agent so failures are resumable.

**Why these choices (defend in interview):**
- **Multi-agent not mono-agent:** each doc type has different extraction needs; specialization gives higher accuracy + easier per-agent eval. Cost: more latency + coordination; acceptable at 30-min SLA.
- **Deterministic validation and underwriting:** regulated decisioning. LLM proposes, rules dispose.
- **LangGraph over LangChain agent executor:** explicit state = auditable. LangGraph checkpoints = resumable. Conditional edges = clean HITL branching.
- **Human-in-the-loop:** not optional — it's a regulatory gate for origination.

**Evaluation:**
- **Per-agent:** labeled set per doc type, field-level precision/recall.
- **End-to-end:** 500-application gold set with expert-labeled packets; measure field accuracy + cycle time + HITL escalation rate.
- **Regression gate:** every prompt / model change runs the gold set; block deploy if any field drops >2%.
- **Failure modes:** measure (a) extraction errors, (b) validation false-flags (annoy underwriters), (c) validation false-passes (the dangerous one).

**Serving:**
- **Deploy:** each agent as an ECS service or Lambda; LangGraph orchestrator on ECS with state in DynamoDB or Postgres.
- **LLMs:** Bedrock Claude (enterprise PII-safe) or internal JP-Morgan LLM gateway.
- **Observability:** LangSmith / Langfuse tracing every step; per-application audit trail in S3.
- **Cost control:** cache doc-classification results per document hash; semantic cache for repeated extraction patterns.

**Risk/MRM:**
- Every field has a source (doc, page, bbox) — regulators can trace each claim.
- Versioned prompts with change log.
- Adversarial testing: fraudulent-doc corpus, verify the system flags them (or flags for HITL when uncertain).

---

## 3.3 Case Study: Design a RAG System for Servicing-Agent Q&A

**Ask:** "Design a RAG system that answers customer-service agents' questions about loan policies, guidelines, and procedures."

**Clarify:**
- Audience: servicing agents (not customers directly).
- Corpus: ~5k policy docs + FAQ + recent memos; updated weekly.
- Constraints: every answer cited to source; no-answer preferred over wrong answer; no customer PII in queries.

**Framing:** Dense+sparse hybrid retrieval + LLM generation with citations. Guardrails for out-of-scope.

**Pipeline:**

1. **Ingest** — versioned doc store (S3 + metadata: effective date, doc type, deprecated flag).
2. **Chunk** — heading-aware splitter; 300-token chunks, 15% overlap; each chunk carries source metadata.
3. **Embed** — fine-tuned BGE or E5 (domain-adapted on policy corpus). Weekly re-embed of changed docs.
4. **Index** — OpenSearch (BM25 + kNN hybrid) — same system does sparse + dense, simpler ops than separate FAISS + ES.
5. **Retrieve** — top-20 hybrid (RRF), rerank to top-5 with bge-reranker-large.
6. **Generate** — Claude (Bedrock) with a prompt that (a) requires citations to chunk IDs, (b) instructs "I don't know" if context insufficient.
7. **Post-process** — verify each cited chunk ID exists in retrieved set; if not, mark answer unverified.

**Evaluation (the bit that separates senior candidates):**
- **Retrieval gold set:** 300 (question, relevant-doc) pairs labeled by senior agents. Recall@5, Recall@20, MRR.
- **Answer gold set:** 150 (question, reference-answer, citations) triples. Metrics: faithfulness (answer grounded in context? NLI or LLM-judge), answer relevance (does it address the question?), citation precision (are cited chunks actually relevant?).
- **Negative set:** 50 out-of-scope questions; target ≥95% "I don't know" refusal.
- **Stale-content test:** 30 questions whose correct answer changed after a memo update; verify system picks the newer doc.
- **Regression gate:** all four sets in CI; block deploy on ≥2% drop in any metric.

**Guardrails:**
- **Prompt injection:** sanitize retrieved content (it's malicious-unfriendly since source is internal docs, but still wrap retrieved chunks in explicit delimiters and instruct LLM to treat them as data).
- **PII in queries:** pre-query PII scanner; reject or mask before LLM.
- **Output filtering:** block outputs containing account numbers or SSN patterns.
- **Scope:** LLM refuses to give loan-advice beyond policy lookup — system-prompt constraint + eval tests.

**Serving:**
- **Stack:** Bedrock for LLM, OpenSearch for retrieval, ECS for the orchestration API, Redis for semantic cache.
- **Latency budget:** 3s P95 (agent typing into a tool). Budget: 200ms retrieval + 300ms rerank + 2s generation + 500ms slack.
- **Cost:** semantic cache on common questions (repeat-rate is high in servicing) — can cut LLM costs 40–60%.

**Monitoring:**
- **Retrieval quality:** daily replay of gold set; alert on Recall@5 drop.
- **Answer quality:** LLM-as-judge on 1% sampled production answers, human-reviewed weekly.
- **Refusal rate:** out-of-scope refusal rate over time.
- **Doc freshness:** % of top-k results from docs updated in last 90d.

---

# PART 4 — Generic System Design Cheat-Sheet (memorize)

For any ML system design question, walk this list out loud:

| Phase | What to say |
|---|---|
| **Clarify** | Business objective? Success metric? Scale (QPS, data volume)? Latency SLA? Regulated? |
| **Problem** | Classification / regression / ranking / retrieval / generation? Online / batch? |
| **Data** | Sources, features, labels, leakage, freshness, volume, split strategy |
| **Baseline** | Simplest thing that works (LogReg / BM25 / heuristic) — establishes floor |
| **Model** | Candidate models, why this not that, capacity-vs-data fit |
| **Metric** | Offline (PR-AUC, Recall@k, faithfulness…) + online (A/B primary metric) + fairness |
| **Serving** | Batch / real-time, infra (SageMaker / ECS / Lambda), model registry, feature store |
| **Rollout** | Shadow → champion-challenger → A/B → full; ramp strategy |
| **Monitor** | Input drift, output drift, performance, fairness, cost |
| **MRM** | Model card, explainability, adverse-action, retrain cadence, audit trail |
| **Failure modes** | What breaks it? Adversarial inputs, data drift, concept drift, dependency outage |

**If you stall:** say "let me think about failure modes" or "what does regulator feedback look like?" — both reframe you as someone who thinks beyond the happy path.

---

# PART 5 — Quick Self-Test (do this 24 hours before interview)

Check each of these — if you can't answer in 30 seconds, revise.

**Classical ML:**
- [ ] Explain Logistic Regression + why it's used in credit origination
- [ ] XGBoost vs Random Forest tradeoff, one sentence each
- [ ] K-Means failure modes + at least one alternative
- [ ] PCA mechanics + when to scale
- [ ] Isolation Forest intuition
- [ ] PR-AUC vs ROC-AUC on imbalanced data

**LLM / GenAI:**
- [ ] Scaled dot-product attention formula
- [ ] LoRA: r, α, target_modules — what each means
- [ ] RAG pipeline 7 steps
- [ ] How to evaluate RAG (retrieval + generation + end-to-end)
- [ ] Prompt injection direct vs indirect, defenses

**Agentic:**
- [ ] Chain vs single-agent vs multi-agent — when each
- [ ] Tool-description quality checklist
- [ ] Agent cost/loop controls (max_iterations, token budget, timeout)
- [ ] LangGraph vs CrewAI vs AutoGen — one sentence each
- [ ] Agent evals vs classifier evals — why they differ

**SQL:**
- [ ] Difference between ROW_NUMBER / RANK / DENSE_RANK
- [ ] Rolling window syntax (`ROWS BETWEEN … PRECEDING …`)
- [ ] Top-N per group query pattern
- [ ] Cohort retention query pattern

**Domain / behavioral:**
- [ ] Your "determinism over intelligence" principle in one sentence
- [ ] How your Kotak design maps to JP Morgan Home Lending
- [ ] One regulated-domain STAR story, <90s
- [ ] Three smart questions to ask the interviewer

---

**Final:** JP Morgan will interview you across **three buckets** — ML depth (Part 1 + concepts doc), production thinking (Part 3 system design), and coding (Parts 1 + 2 of this doc). Don't over-index on any one. The candidate who clears all three is the one who gets the offer.
