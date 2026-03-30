# Offer Validation & Recommendation — Implementation Plan

> **Scope**: New validation dimensions BEYOND `docs/policy_judgment_plan.md`
> **Principle**: Determinism > Intelligence (same as existing system)
> **Three plans ranked by Ease x Impact**

---

## Context

The existing `policy_judgment_plan.md` covers a PolicyEngine that evaluates offers against a fixed ruleset (pass/fail per rule, aggregate verdict). That is necessary but insufficient. The user wants deeper analysis:

1. **Was the underlying policy followed?** (affluence overrides, model ceiling breaches)
2. **If not, what went wrong?** (code issue? hard threshold? manual override?)
3. **Based on bureau history, is the product + amount valid?** (zero PL history but 10L PL offer)
4. **Based on banking, does the offer match customer behaviour?** (BL history but PL offer)

These are forensic, prescriptive, and forward-looking questions — not addressed by the existing pass/fail policy engine.

---

## Key Discovery: Untapped Data Fields

`tl_features.csv` contains 4 offer-related columns **currently unmapped** in `TradelineFeatures`:

| CSV Column | Meaning | Current Status |
|---|---|---|
| `agr_value` | Approved/agreed loan amount (e.g., 125000) | **NOT in TradelineFeatures** |
| `agr_date` | Agreement date (e.g., 2026-03-03) | **NOT in TradelineFeatures** |
| `min_loan_amt` | Model-computed minimum eligible amount | **NOT in TradelineFeatures** |
| `max_loan_amt` | Model-computed maximum eligible amount | **NOT in TradelineFeatures** |

Also: `affluence_amt_6` (6-month income estimate), `node`, `node_id` (decision tree node from scoring model) are available and mapped.

These fields are the foundation for affluence override detection and amount calibration.

---

## PLAN A: Offer Forensics & Cross-Source Consistency

**Ease: HIGH | Impact: HIGH | Effort: 2-3 days**
**"Catch bad offers with data you already have, using patterns you already use."**

### Dimensions Covered

| # | Dimension | User Example |
|---|---|---|
| 1 | Affluence Override Forensics | "affluence_amt was X but due to policy it got increased to X+t" |
| 2 | Cross-Source Consistency | Banking income vs bureau affluence mismatch |
| 3 | Offer Amount Calibration | agr_value vs model bounds (min_loan_amt, max_loan_amt) |
| 4 | Temporal Risk Gating | Offer made during active DPD / enquiry burst / loan stacking |

### 1. Affluence Override Forensics

**What it detects**: The scoring model computes `affluence_amt_6` (income estimate) and `max_loan_amt` (ceiling). If the approved `agr_value` exceeds these, someone or something overrode the model.

**Logic** (pure threshold, no LLM):
```
IF agr_value > max_loan_amt:
    FLAG "Model ceiling breach" (severity: high_risk)
    detail: "Approved {agr_value} exceeds model max {max_loan_amt} by {delta}%"

IF agr_value > affluence_amt_6 * T.AGR_AFFLUENCE_MULTIPLIER_MAX:
    FLAG "Affluence override" (severity: concern)
    detail: "Approved amount is {ratio}x the 6-month affluence estimate"

IF agr_value < min_loan_amt:
    FLAG "Below model floor" (severity: neutral)
    detail: "Approved {agr_value} is below model minimum {min_loan_amt}"
```

**Why this matters**: An override isn't always wrong — but an *undetected* override is always a risk. This makes every override visible and auditable.

### 2. Cross-Source Consistency Checks

Compares independent data sources to find contradictions:

| Check | Source A | Source B | Flag Condition |
|---|---|---|---|
| Income mismatch | `salary.avg_amount * 12` (banking) | `affluence_amt_6 * 2` (bureau annualized) | >40% divergence |
| Hidden obligations | `len(customer_report.emis)` (banking EMIs) | `executive_inputs.live_tradelines` (bureau) | Bureau shows 2+ more live loans than banking EMIs |
| FOIR divergence | Banking FOIR: `(emi_total + rent) / salary` | Bureau FOIR: `tradeline_features.foir` | >15pp divergence |
| Cashflow vs exposure | `avg_monthly_net_savings` (banking) | `total_outstanding / 12` (bureau monthly burn) | Outstanding burn > 3x net savings |

**Why this matters**: If banking shows 2 EMIs but bureau shows 7 live tradelines, the customer has hidden obligations the banking analysis doesn't see. The offer may have been sized based on incomplete data.

### 3. Offer Amount Calibration

**Loan-to-Income (LTI) ratio**: `agr_value / (affluence_amt_6 / 6)` — checks if the offer amount is proportionate to monthly income.

**Total exposure check**: `(total_outstanding + agr_value) / (affluence_amt_6 * 2)` — ensures the new loan doesn't push total debt beyond a sustainable ceiling.

**Model bounds check**: `min_loan_amt <= agr_value <= max_loan_amt` — binary check, but the *deviation magnitude* matters.

### 4. Temporal Risk Gating

Checks whether the offer timing was safe by cross-referencing `agr_date` against:
- `months_since_last_0plus_uns` — was there recent delinquency?
- `new_trades_6m_pl` — was the customer actively stacking loans?
- `unsecured_enquiries_12m` — was there an enquiry burst (credit hunger)?
- `max_dpd` + `months_since_max_dpd` — was max DPD still recent at offer time?

### New Files

| File | Purpose |
|---|---|
| `pipeline/offer/offer_forensics.py` | Core forensics engine (4 check functions, ~250 lines) |
| `schemas/offer_forensics.py` | `ForensicsFlag` + `OfferForensicsResult` dataclasses |

### Files to Modify

| File | Change |
|---|---|
| `features/tradeline_features.py` | Add 4 fields: `agr_date`, `agr_value`, `min_loan_amt`, `max_loan_amt` |
| `pipeline/extractors/tradeline_feature_extractor.py` | Add 4 entries to `_COLUMN_MAP` |
| `config/thresholds.py` | Add ~10 thresholds (AGR_AFFLUENCE_MULTIPLIER_MAX, INCOME_MISMATCH_PCT, LTI_MAX_PL, etc.) |

### Output Schema

```python
@dataclass
class ForensicsFlag:
    dimension: str        # "affluence_override" | "cross_source" | "amount_calibration" | "temporal_risk"
    finding: str          # Human-readable finding
    inference: str        # Risk interpretation
    severity: str         # "high_risk" | "concern" | "neutral" | "positive"
    data_points: dict     # Auditable evidence: {"agr_value": X, "affluence_amt": Y}

@dataclass
class OfferForensicsResult:
    customer_id: int
    flags: List[ForensicsFlag]
    affluence_override_detected: bool
    income_mismatch_detected: bool
    amount_within_model_bounds: bool
    temporal_gates_clear: bool
    overall_risk: str     # "CLEAN" | "FLAGS_PRESENT" | "HIGH_RISK"
```

### New Thresholds (`config/thresholds.py`)

```python
# Affluence Override
AGR_AFFLUENCE_MULTIPLIER_MAX = 1.30      # agr_value > 130% of affluence → flag
# Cross-Source
INCOME_MISMATCH_PCT = 40.0               # >40% divergence = flag
EMI_MISMATCH_MIN_GAP = 2                 # bureau live - banking EMIs >= 2 → hidden obligations
FOIR_DIVERGENCE_PP = 15.0                # >15 percentage points divergence
# Amount Calibration
LTI_MAX_PL = 15.0                        # Max loan-to-monthly-income for PL
LTI_MAX_BL = 20.0
TOTAL_EXPOSURE_CEILING_MONTHS = 36
# Temporal
TEMPORAL_DPD_CLEAR_MONTHS = 6
TEMPORAL_STACKING_THRESHOLD = 2
TEMPORAL_ENQUIRY_GATE = 10
```

---

## PLAN B: Bureau Product Affinity & Recommendation Engine

**Ease: MEDIUM | Impact: HIGH | Effort: 4-5 days**
**"Don't just check if the offer was allowed — check if it was the RIGHT product."**

### Dimensions Covered

| # | Dimension | User Example |
|---|---|---|
| 5 | Product Affinity Score | "Zero PL history but offered 10L PL" — score how well the product fits |
| 6 | Product Recommendation | "Multiple BLs in history but offered PL" — recommend BL instead |
| 7 | Portfolio Concentration Risk | Adding another unsecured when already 80% unsecured |
| 8 | Repayment Capacity Stress Test | Can the customer handle the EMI if income drops 20%? |

### 1. Product Affinity Scoring

Uses existing `BureauLoanFeatureVector` per loan type to compute a 3-axis score:

**Experience Score (0-100)**: Does the customer have history with this product?
- `offered_product in feature_vectors` → base 50
- `+ loan_count * 5` (capped at 30) — more experience = higher score
- `+ 20` if `avg_vintage_months > 24` — long track record
- `= 0` if product type not in feature_vectors at all (the "zero PL history" case)

**Performance Score (0-100)**: How clean is their track record on this product?
- Start at 100, deduct:
  - `-40` if `delinquency_flag` is True
  - `-20` if `forced_event_flags` present (write-off, settlement)
  - `-15` if `max_dpd > 30`
  - `+10` if `ratio_good_closed_pl > 0.8` (good closure history)

**Concentration Score (0-100)**: Inverse of how much MORE concentration this adds.
- Current unsecured % from `executive_inputs`
- Post-offer unsecured % = `(unsecured_outstanding + offer_amt) / (total_outstanding + offer_amt)`
- If delta > 10pp, penalize. If already > 80% and adding more, heavy penalty.

**Composite** = `0.40 * experience + 0.35 * performance + 0.25 * concentration`

If composite < 40 → **product-history mismatch flag**.

### 2. Product Recommendation Engine

Scores ALL loan types the customer has history with:

```
For each LoanType in feature_vectors:
    score = compute_affinity(loan_type, feature_vectors, tradeline_features)
    if score > offered_product_score AND loan_type != offered_product:
        add to recommendations

Also consider ADJACENT products:
    BL customer → can be recommended PL (business→personal overlap)
    HL customer → can be recommended LAP (home→property overlap)
    PL customer → can be recommended CC (unsecured→revolving overlap)

Sort by score, return top 3 with rationale
```

Handles user's example directly: Customer with 4 BLs (experience=85, performance=90) offered PL (experience=0) → recommends BL with "Customer has 4 BLs with avg vintage 36 months and zero DPD. BL affinity score 87 vs PL affinity score 12."

### 3. Repayment Capacity Stress Test

Standard EMI formula: `EMI = P * r * (1+r)^n / ((1+r)^n - 1)`

Three scenarios:
| Scenario | Modification | Pass if |
|---|---|---|
| Base | Current income, proposed EMI | FOIR < 65% |
| Income stress | Income * 0.80 | FOIR < 75% |
| Rate stress | Rate + 200bps, recalc EMI | FOIR < 75% |
| Combined | Both | FOIR < 85% |

Uses `monthly_cashflow` from CustomerReport for real disposable income (more accurate than just salary).

### 4. Portfolio Concentration Risk

**Herfindahl-Hirschman Index (HHI)** across product types:
```
HHI = sum((product_outstanding / total_outstanding)^2 for each product)
```
Pre-offer vs post-offer HHI. If HHI increases AND already > 0.50, flag concentration risk.

Also: on-us share (Kotak's own lending concentration) from `on_us_sanctioned / total_sanctioned`.

### New Files

| File | Purpose |
|---|---|
| `pipeline/offer/product_affinity.py` | Affinity scoring + recommendation engine (~300 lines) |
| `pipeline/offer/stress_test.py` | EMI stress test under 3 scenarios (~150 lines) |
| `pipeline/offer/concentration_risk.py` | HHI + unsecured % + on-us concentration (~120 lines) |
| `schemas/product_recommendation.py` | `ProductAffinityResult`, `ProductRecommendation`, `StressTestResult`, `ConcentrationRiskResult` |

### Files to Modify

| File | Change |
|---|---|
| `config/thresholds.py` | Add ~12 thresholds (affinity weights, stress params, HHI limits) |

### New Thresholds

```python
# Product Affinity
AFFINITY_MISMATCH_THRESHOLD = 40.0
AFFINITY_EXPERIENCE_WEIGHT = 0.40
AFFINITY_PERFORMANCE_WEIGHT = 0.35
AFFINITY_CONCENTRATION_WEIGHT = 0.25
# Stress Test
STRESS_INCOME_DROP_PCT = 20.0
STRESS_RATE_HIKE_BPS = 200
STRESS_FOIR_CEILING = 75.0
STRESS_COMBINED_CEILING = 85.0
# Concentration
HERFINDAHL_CONCENTRATED = 0.50
SINGLE_LENDER_MAX_PCT = 60.0
POST_OFFER_UNSECURED_MAX_PCT = 85.0
```

---

## PLAN C: LLM Reasoning Agent + Decision Viz + Counterfactuals

**Ease: LOWER | Impact: VERY HIGH | Effort: 7-10 days (requires A + B first)**
**"Let the LLM reason over ALL evidence, show the decision tree, answer what-if questions."**

### Dimensions Covered

| # | Dimension | Description |
|---|---|---|
| 9 | Multi-step LLM reasoning | Chain of thought over forensics + affinity + policy results |
| 10 | Counterfactual analysis | "What if affluence was 20% lower?" — re-run with modified params |
| 11 | Decision tree visualization | D3.js collapsible tree showing exactly why the offer passed/failed |
| 12 | Offer Channel Risk | DSA/digital/branch have different risk profiles and threshold adjustments |
| 13 | Semantic policy citation | Embed policy docs, retrieve relevant clauses for each finding |

### 1. LLM Reasoning Agent

NOT a general-purpose agent — a structured LCEL chain that receives ALL pre-computed results and produces a reasoning chain:

```
Input: {
    forensics: OfferForensicsResult,     # From Plan A
    affinity: ProductAffinityResult,      # From Plan B
    stress_test: StressTestResult,        # From Plan B
    policy_judgment: PolicyJudgment,      # From existing plan
    key_findings: List[KeyFinding],       # Existing
    scorecard: dict                       # Existing
}

LLM Output (forced JSON):
{
    "reasoning_steps": [
        {
            "step": 1,
            "premise": "Affluence was overridden by 1.8x",
            "evidence": "agr_value=125000, affluence_amt=70000",
            "implication": "Offer amount may be inflated beyond genuine capacity"
        },
        {
            "step": 2,
            "premise": "Customer has zero PL history",
            "evidence": "PL not in feature_vectors, experience_score=0",
            "implication": "Product-history mismatch — no evidence customer can service PL"
        },
        ...
    ],
    "conclusion": "UNJUSTIFIED — affluence override + product mismatch + FOIR stress failure",
    "confidence": 0.88
}
```

The LLM synthesizes — it doesn't compute. Every number comes from the deterministic layers below.

### 2. Counterfactual Engine

Automated what-if analysis:

```python
scenarios = [
    {"param": "affluence_amt", "delta_pct": -20, "label": "Affluence -20%"},
    {"param": "affluence_amt", "delta_pct": -40, "label": "Affluence -40%"},
    {"param": "agr_value", "delta_pct": -30, "label": "Offer amount -30%"},
    {"param": "foir", "override": 55.0, "label": "FOIR capped at 55%"},
]

For each scenario:
    1. Clone tradeline_features with modified value
    2. Re-run forensics (Plan A) + policy engine
    3. Compare: did the verdict change? Which flags appeared/disappeared?
    4. Record: "tipping_point = True" if verdict flipped
```

Output: "If affluence_amt was 20% lower, 2 additional forensics flags trigger and the verdict flips from PARTIALLY_JUSTIFIED to UNJUSTIFIED."

This directly answers: "the affluence_amt originally was X but due to some policy it got increased to X+t — should that override have happened?" by showing what would have happened WITHOUT the override.

### 3. Decision Tree Visualization

Nested dict → D3.js collapsible tree in the HTML template:

```
Offer Validation
├── Policy Rules (3/12 failed)
│   ├── [FAIL] PL_002: FOIR 72% > max 65%
│   ├── [FAIL] PL_011: LTI ratio 18x > max 10x
│   └── [PASS] PL_001: Income 45k > min 25k
├── Forensics (2 flags)
│   ├── [HIGH] Affluence override: 1.8x multiplier
│   └── [CONCERN] Income mismatch: banking 45k vs bureau 28k
├── Product Fit (score: 22/100)
│   ├── Experience: 0 (no PL history)
│   ├── Performance: N/A
│   └── Concentration: 35 (already 75% unsecured)
└── Stress Test
    ├── [PASS] Base FOIR: 58%
    ├── [FAIL] Income stress FOIR: 78%
    └── [FAIL] Combined stress FOIR: 92%
```

Uses D3.js CDN (same approach as existing Chart.js charts — no server dependency).

### 4. Channel Risk Profiling

Different origination channels warrant different scrutiny:

| Channel | FOIR Ceiling | LTI Max | Extra Checks |
|---|---|---|---|
| Branch | 65% | 15x | Standard |
| Digital | 60% | 12x | Auto-decision audit trail required |
| DSA | 55% | 10x | Mandatory affluence verification, tighter temporal gates |

Implemented as a threshold multiplier per channel that tightens the forensics and policy thresholds.

### 5. Semantic Policy Citation

Uses Ollama's `nomic-embed-text` model (local, no cloud) to embed policy document chunks:

```
policy_docs/*.md → chunk (500 tokens) → embed → FAISS index (local)

When a forensics flag fires:
    query = flag.finding + flag.inference
    top_3_chunks = faiss_index.search(embed(query), k=3)
    flag.cited_policies = top_3_chunks
```

Not for rule extraction (that's in the existing plan's Tier 2). This is for **citation** — every finding links back to the specific policy clause it relates to.

### New Files

| File | Purpose |
|---|---|
| `pipeline/offer/offer_reasoning_agent.py` | LCEL chain: structured evidence → reasoning chain → narrative |
| `pipeline/offer/counterfactual_engine.py` | What-if scenario runner (~200 lines) |
| `pipeline/offer/decision_tree.py` | Build nested dict for D3.js visualization (~150 lines) |
| `pipeline/offer/channel_risk.py` | Channel-aware threshold adjustment (~100 lines) |
| `pipeline/offer/policy_search.py` | Embedding + FAISS index for policy citation (~200 lines) |
| `schemas/offer_validation.py` | Master `OfferValidationReport` combining all dimensions |

### Dependencies
- `faiss-cpu` (for local vector search — pip installable, no GPU needed)
- `nomic-embed-text` Ollama model (local embeddings)
- D3.js CDN (for decision tree visualization in HTML template)

---

## Comparison Matrix

| Dimension | Plan A | Plan B | Plan C |
|---|---|---|---|
| Affluence override detection | **Primary** | - | Via A |
| Cross-source consistency | **Primary** | - | Via A |
| Offer amount calibration | **Primary** | - | Via A |
| Temporal risk gating | **Primary** | - | Via A |
| Product affinity scoring | - | **Primary** | Via B |
| Product recommendation | - | **Primary** | Via B |
| Stress test | - | **Primary** | Via B |
| Concentration risk | - | **Primary** | Via B |
| LLM reasoning chain | - | - | **Primary** |
| Counterfactual analysis | - | - | **Primary** |
| Decision tree viz | - | - | **Primary** |
| Channel risk | - | - | **Primary** |
| Policy citation | - | - | **Primary** |
| **New modules** | 2 | 4 | 6 |
| **LLM required** | No | No | Yes |
| **Effort** | 2-3 days | 4-5 days | 7-10 days |

---

## Recommended Implementation Order

```
Week 1: Plan A (Forensics)
    → Immediate value, catches override/mismatch issues
    → Prerequisite: map agr_value/min/max_loan_amt into TradelineFeatures

Week 2: Plan B (Product Fit)
    → Uses existing BureauLoanFeatureVector per-type data
    → Stress test uses existing monthly_cashflow

Week 3-4: Plan C (LLM Reasoning + Viz)
    → Only after A+B are validated
    → Counterfactuals re-run A's forensics with modified params
    → Decision tree aggregates all results
```

---

## Verification Plan

After implementation, validate end-to-end with test customer `698167220`:

1. **Map new fields**: Confirm `agr_value`, `min_loan_amt`, `max_loan_amt` are populated from tl_features.csv
2. **Run forensics**: `from pipeline.offer.offer_forensics import run_offer_forensics` — verify flags fire correctly
3. **Run affinity**: `from pipeline.offer.product_affinity import compute_product_affinity_score` — verify scoring against known bureau history
4. **Run stress test**: Verify EMI calculation matches standard amortization formula
5. **Regenerate combined report**: Confirm forensics/affinity results flow into the report template
6. **Check generated HTML**: Grep for forensics flags in `reports/combined_report_html_version/`

---

## Critical Files Reference

| File | Role in Implementation |
|---|---|
| `features/tradeline_features.py` | Add 4 new fields for offer data |
| `pipeline/extractors/tradeline_feature_extractor.py` | Extend `_COLUMN_MAP` for new CSV columns |
| `config/thresholds.py` | Add ~25 new thresholds across all plans |
| `pipeline/reports/key_findings.py` | Pattern to follow: `KeyFinding` + threshold logic |
| `tools/scorecard.py` | Pattern to follow: signal aggregation + verdict |
| `features/bureau_features.py` | `BureauLoanFeatureVector` — input for product affinity |
| `pipeline/extractors/bureau_feature_aggregator.py` | `BureauExecutiveSummaryInputs` — portfolio-level data |
| `pipeline/reports/report_summary_chain.py` | Pattern for LLM narrative generation |

---

## Implementation Instructions for Claude

When you are ready to implement, give Claude the following instructions per plan:

### To implement Plan A (Offer Forensics):

```
Implement Plan A from docs/offer_validation_recommendation_plan.md.

Steps:
1. Add 4 new Optional fields to the TradelineFeatures dataclass in features/tradeline_features.py:
   - agr_date: Optional[str]
   - agr_value: Optional[float]
   - min_loan_amt: Optional[float]
   - max_loan_amt: Optional[float]

2. Add corresponding entries in _COLUMN_MAP in pipeline/extractors/tradeline_feature_extractor.py
   to map CSV columns → dataclass fields.

3. Add the ~10 new thresholds to config/thresholds.py under a new
   "# ─── Offer Forensics Thresholds ───" section.

4. Create schemas/offer_forensics.py with ForensicsFlag and OfferForensicsResult dataclasses.

5. Create pipeline/offer/__init__.py (empty) and pipeline/offer/offer_forensics.py with:
   - run_offer_forensics(customer_id, customer_report, bureau_report, tradeline_features) -> OfferForensicsResult
   - _check_affluence_override(tradeline_features) -> List[ForensicsFlag]
   - _check_cross_source_consistency(customer_report, bureau_report, tradeline_features) -> List[ForensicsFlag]
   - _check_offer_amount_calibration(tradeline_features, bureau_report) -> List[ForensicsFlag]
   - _check_temporal_risk_gates(tradeline_features, bureau_report) -> List[ForensicsFlag]
   Follow the exact pattern from pipeline/reports/key_findings.py (import thresholds as T, threshold comparisons, ForensicsFlag instead of KeyFinding).

6. Test: Run extract_tradeline_features(698167220) and confirm agr_value/min_loan_amt/max_loan_amt are populated.
   Then run run_offer_forensics() and verify flags are generated.

Do NOT modify templates or renderers — this is logic-only.
```

### To implement Plan B (Product Affinity):

```
Implement Plan B from docs/offer_validation_recommendation_plan.md.
Plan A must already be implemented.

Steps:
1. Add the ~12 new thresholds to config/thresholds.py under a new
   "# ─── Product Affinity & Stress Test Thresholds ───" section.

2. Create schemas/product_recommendation.py with:
   - ProductAffinityResult (experience_score, performance_score, concentration_score, composite_score, mismatch_flag, rationale)
   - ProductRecommendation (product_type, affinity_score, rationale, advantage_over_offered)
   - StressTestResult (base_emi, base_foir, income_stress_foir, rate_stress_emi, combined_stress_foir, passes_*)
   - ConcentrationRiskResult (current_unsecured_pct, post_offer_unsecured_pct, herfindahl pre/post, on_us_share_pct)

3. Create pipeline/offer/product_affinity.py with:
   - compute_product_affinity_score(offered_product, feature_vectors, tradeline_features) -> ProductAffinityResult
   - recommend_product(feature_vectors, tradeline_features, customer_report) -> List[ProductRecommendation]
   Use BureauLoanFeatureVector fields: loan_count, delinquency_flag, forced_event_flags, avg_vintage_months, max_dpd.
   Use LoanType enum from schemas/loan_type.py.
   Define ADJACENT_PRODUCTS map for cross-product recommendations.

4. Create pipeline/offer/stress_test.py with:
   - stress_test_repayment(offer_amt, tenure_months, annual_rate, monthly_income, existing_obligations) -> StressTestResult
   - Use standard amortization: EMI = P * r * (1+r)^n / ((1+r)^n - 1) where r = annual_rate/12/100

5. Create pipeline/offer/concentration_risk.py with:
   - compute_concentration_risk(offered_product, offer_amt, executive_inputs, feature_vectors) -> ConcentrationRiskResult
   - Compute HHI = sum((product_outstanding/total_outstanding)^2)
   - Use is_secured() from schemas/loan_type.py for secured/unsecured classification

6. Test: Run all three modules against customer 698167220 bureau data and verify scores are reasonable.

Do NOT modify templates or renderers — this is logic-only.
```

### To implement Plan C (LLM Reasoning + Viz + Counterfactuals):

```
Implement Plan C from docs/offer_validation_recommendation_plan.md.
Plans A and B must already be implemented.

Steps:
1. Create schemas/offer_validation.py with the master OfferValidationReport dataclass
   that combines OfferForensicsResult + ProductAffinityResult + StressTestResult +
   ConcentrationRiskResult + reasoning chain + counterfactual results.

2. Create pipeline/offer/counterfactual_engine.py:
   - run_counterfactuals(tradeline_features, customer_report, bureau_report, scenarios) -> List[CounterfactualResult]
   - Each scenario: clone tradeline_features via dataclasses.replace(), modify one param, re-run forensics
   - Default scenarios: affluence -20%, affluence -40%, agr_value -30%, foir capped at 55%

3. Create pipeline/offer/decision_tree.py:
   - build_decision_tree(forensics, affinity, stress, policy_judgment) -> dict
   - Nested dict suitable for D3.js rendering: {label, value, status, children}

4. Create pipeline/offer/channel_risk.py:
   - assess_channel_risk(channel, offer_amt, customer_segment, foir) -> ChannelRiskResult
   - Channel threshold multipliers: DSA tighter, Branch standard, Digital mid

5. Create pipeline/offer/offer_reasoning_agent.py:
   - LCEL chain: gather all structured evidence → format as prompt → LLM (llama3.2) → JSON reasoning steps
   - Follow the pattern from pipeline/reports/report_summary_chain.py
   - Add OFFER_REASONING_PROMPT to config/prompts.py
   - LLM NEVER computes — only synthesizes pre-computed results into reasoning chain

6. (Optional) Create pipeline/offer/policy_search.py:
   - Load policy markdown docs, chunk, embed via OllamaEmbeddings(model="nomic-embed-text")
   - Build FAISS index for semantic search
   - When a flag fires, retrieve top-3 relevant policy clauses as citations

7. Test: Run full pipeline for customer 698167220 — forensics → affinity → stress → counterfactuals → reasoning.
   Verify counterfactual correctly shows verdict changes when affluence is reduced.

Do NOT modify templates — this is logic-only.
```
