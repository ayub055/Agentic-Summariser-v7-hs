# LLM Summary Prompt — Data Flow, Duplication & Optimization Analysis

> **Scope:** All three executive summary LLM prompts (Banking, Bureau, Combined)
> **Purpose:** Map every data point entering each prompt, identify hallucination/duplication risks, and propose optimization strategies.

---

## Table of Contents

1. [Banking Customer Review — Data Point Map](#1-banking-customer-review--data-point-map)
2. [Bureau Executive Review — Data Point Map](#2-bureau-executive-review--data-point-map)
3. [Combined Executive Summary — Data Point Map](#3-combined-executive-summary--data-point-map)
4. [Data Overlap & Duplication Matrix](#4-data-overlap--duplication-matrix)
5. [Hallucination Risk Analysis](#5-hallucination-risk-analysis)
6. [Event Detection — False Positive & Hallucination Audit](#6-event-detection--false-positive--hallucination-audit)
7. [Redundancy in Combined Summary (LLM-on-LLM)](#7-redundancy-in-combined-summary-llm-on-llm)
8. [Prompt Chaining & Optimization Strategies](#8-prompt-chaining--optimization-strategies)
9. [Recommendations Summary](#9-recommendations-summary)

---

## 1. Banking Customer Review — Data Point Map

**Prompt:** `CUSTOMER_REVIEW_PROMPT` (`config/prompts.py:162`)
**Builder function:** `_build_data_summary()` (`pipeline/reports/report_summary_chain.py:98`)
**Input:** `CustomerReport` + optional `rg_salary_data`
**Output sections:** Financial Overview (4-6 lines), Merchant Behavior (2-4 lines), Transaction Events (1 sentence/event)

| # | Data Point | Source / Computation | Variable in `_build_data_summary()` | Hallucination Risk |
|---|------------|---------------------|--------------------------------------|-------------------|
| 1 | Top 3 spending categories (name + amount) | `report.category_overview` — deterministic pandas groupby on `category_of_txn` column | `top_cats` | Low — exact numbers passed |
| 2 | Monthly cashflow (avg net, total inflow, total outflow) | `report.monthly_cashflow` — month-wise sum of credits vs debits | `total_inflow`, `total_outflow`, `avg_net` | Low — arithmetic done in Python |
| 3 | Salary income (amount, merchant, frequency) | **Priority:** `rg_salary_data.rg_sal.salary_amount` → fallback `report.salary.avg_amount` | `_auth_salary_amt`, `_auth_salary_merchant` | **Medium** — merchant name comes from narration parsing, may be truncated or garbled |
| 4 | EMI commitments (avg per payment, debit count) | `report.emis` — list of `EMIBlock` objects from narration keyword matching | `avg_emi`, `emi_count` | **Medium** — EMI detection depends on keyword matching in narrations |
| 5 | Rent payments (amount, frequency) | `report.rent` — `RentBlock` from keyword + recurring pattern detection | `report.rent.amount` | **Medium** — same keyword-matching risk as EMI |
| 6 | Banking FOIR (EMI+Rent / Salary %) | Computed inline: `(_emi_avg + _rent_amt) / _auth_salary_amt * 100` | `_foir` | **High** — compounds errors from items 3, 4, 5. If salary is wrong, FOIR is wrong. Tagged `[OVER-LEVERAGED]`/`[STRETCHED]`/`[COMFORTABLE]` |
| 7 | Utility bills (total) | `report.bills` — list of `BillBlock` objects | `total_bills` | Low |
| 8 | Most frequent merchant (name, count, total) | `report.top_merchants[0]` — sorted by transaction count | `top_merchant` | Low — direct from data |
| 9 | **MERCHANT PROFILE** (block) | `report.merchant_features` from `features/merchant_features.py` — contains sub-features: | | |
| 9a | → Regular merchants (top 3 names) | Merchants with ≥3 transactions, fuzzy-grouped | `regular` | **Medium** — fuzzy grouping can merge distinct merchants |
| 9b | → Anomaly merchants (name, amount) | Single-transaction outlier by amount | `anomalies` | Low — hard threshold |
| 9c | → Concentration (top-1%, total merchants) | Herfindahl-style concentration | `concentration` | Low |
| 9d | → Favourite debit/credit merchants (name, count, total, avg IPT days) | Top merchants by count per direction, with inter-purchase time | `favourites` | **Medium** — IPT calculation on small samples can be misleading |
| 9e | → Significant counterparties (≥25% of flow) | Merchants with ≥25% of total debit or credit volume | `significant` | Low |
| 9f | → Two-way merchants (credit+debit with same entity, net flow, pattern) | Bidirectional flow detection with flow_pattern | `bidir` | **High** — fuzzy name matching can create false bidirectional links |
| 9g | → Emerging merchants (new in recent 3 months) | Merchants absent in earlier months but active recently | `em_list` | Low |
| 10 | **Account quality observations** (list of strings) | `report.account_quality` from `tools/account_quality.py` — detects conduit behavior, ATM dependency, low activity, no obligations | `obs` | **High** — conduit detection uses keyword matching + timing heuristics; false positives directly narrated by LLM |
| 11 | **DETECTED TRANSACTION EVENTS** (block) | `report.events` from `tools/event_detector.py` → `format_events_for_prompt()` | `events_block` | **HIGH** — see Section 6 below |
| 12 | DATA NOT AVAILABLE list | Explicitly lists absent data types | `absent` | **Protective** — reduces hallucination of missing data |

---

## 2. Bureau Executive Review — Data Point Map

**Prompt:** `BUREAU_REVIEW_PROMPT` (`config/prompts.py:207`)
**Builder function:** `_build_bureau_data_summary()` (`pipeline/reports/report_summary_chain.py:762`)
**Input:** `BureauExecutiveSummaryInputs` + `TradelineFeatures` + `monthly_exposure`
**Output sections:** Portfolio Overview (6-10 lines), Behavioral Insights (4-6 lines)

### 2.1 Portfolio Summary (from `BureauExecutiveSummaryInputs`)

| # | Data Point | Source / Computation | Hallucination Risk |
|---|------------|---------------------|-------------------|
| 1 | Total / Live / Closed tradelines | `bureau_feature_aggregator.aggregate_bureau_features()` — count of tradelines by `loan_status` | Low |
| 2 | Total sanction amount (INR) | Sum of `sanction_amount` across all tradelines | Low |
| 3 | Total outstanding (INR) | Sum of `out_standing_balance` across all tradelines | Low |
| 4 | Unsecured sanction amount (INR) | Sum of `sanction_amount` for tradelines where `is_secured(raw_type) = False` | Low |
| 5 | Unsecured outstanding (% of total) | `unsecured_outstanding / total_outstanding * 100` | Low |
| 6 | Max DPD (days, months ago, loan type) | Pre-computed `max_dpd` column + `months_since_max_dpd` from CSV | Low |
| 7 | CC Utilization (%) | `sum(outstanding) / sum(credit_limit)` for live CC tradelines — shown per product if `utilization_ratio is not None` | **Medium** — zero-outstanding closed CC can produce 0.0% that LLM may narrate |

### 2.2 Obligation & FOIR (from `TradelineFeatures`)

| # | Data Point | Source / Computation | Hallucination Risk |
|---|------------|---------------------|-------------------|
| 8 | Affluence income (6M estimate, INR) | `tl_features.csv` → `affluence_amt` | Low — pre-computed |
| 9 | Total bureau EMI obligation (INR) | `tl_features.csv` → `aff_emi` | Low |
| 10 | Unsecured EMI obligation (INR) | `tl_features.csv` → `unsecured_emi` | Low |
| 11 | FOIR total (%) | `tl_features.csv` → `foir`, tagged `[OVER-LEVERAGED]`/`[STRETCHED]`/`[COMFORTABLE]` | Low — number is pre-computed; tag is deterministic |
| 12 | FOIR unsecured (%) | `tl_features.csv` → `foir_unsec`, same tagging | Low |

### 2.3 Product Breakdown (from `feature_vectors` dict)

| # | Data Point | Source / Computation | Hallucination Risk |
|---|------------|---------------------|-------------------|
| 13 | Per loan-type: count, live, closed, sanctioned, outstanding | `BureauLoanFeatureVector` per canonical `LoanType` | Low |

### 2.4 Kotak (On-Us) Exposure (from `BureauExecutiveSummaryInputs`)

| # | Data Point | Source / Computation | Hallucination Risk |
|---|------------|---------------------|-------------------|
| 14 | On-us tradeline count (total, live) | Tradelines with `sector ∈ ON_US_SECTORS` | Low |
| 15 | On-us products | Distinct loan types in on-us tradelines | Low |
| 16 | On-us sanctioned / outstanding (INR) | Sum for on-us tradelines | Low |
| 17 | On-us max DPD | Max DPD among on-us tradelines, flagged `[CONCERN]` if > 0 | Low |

### 2.5 Joint Loans & Defaults

| # | Data Point | Source / Computation | Hallucination Risk |
|---|------------|---------------------|-------------------|
| 18 | Joint loan count + product types | `total_joint_count`, `joint_product_types` | Low |
| 19 | Defaulted loan summaries (type, sanction, outstanding, DPD, on-us flag) | `defaulted_loan_summaries` list | Low |

### 2.6 Behavioral & Risk Features (from `TradelineFeatures` via `_format_tradeline_features_for_prompt()`)

| # | Data Point | Source / Computation | Annotation Tags | Hallucination Risk |
|---|------------|---------------------|-----------------|--------------------|
| 20 | New PL trades in 6M | `tl_features.csv` → `new_trades_6m_pl` | `[HIGH RISK]` if ≥ 3, `[MODERATE RISK]` if ≥ 2 | Low |
| 21 | Months since last PL trade | `months_since_last_trade_pl` | `[CONCERN]` if < threshold | Low |
| 22 | Months since last unsecured trade | `months_since_last_trade_uns` | `[CONCERN]` if < threshold | Low |
| 23 | Max DPD 6M CC / PL / 9M CC | `max_dpd_6m_cc`, `max_dpd_6m_pl`, `max_dpd_9m_cc` | `[HIGH RISK]`/`[MODERATE RISK]`/`[CONCERN]`/`[CLEAN]` | Low |
| 24 | Months since last 0+ DPD (PL / Unsec) | `months_since_last_0p_pl`, `months_since_last_0p_uns` | `[POSITIVE]`/`[CONCERN]` | Low |
| 25 | % Missed payments 18M | `pct_missed_payments_18m` | `[HIGH RISK]`/`[CONCERN]`/`[POSITIVE]`/`[NOTE]` | **Medium** — cross-check with DPD can create contradictory signals (see composite signals) |
| 26 | % Trades with 0+ DPD (24M all, 24M PL, 12M all) | `pct_0plus_24m_all`, `pct_0plus_24m_pl`, `pct_trades_0plus_12m` | `[HIGH RISK]`/`[CONCERN]`/`[CLEAN]` | Low |
| 27 | Good closure ratio (PL) | `ratio_good_closed_pl` | `[POSITIVE]`/`[HIGH RISK]`/`[CONCERN]` | Low |
| 28 | CC balance utilization (%) | `cc_balance_utilization_pct` | `[HIGH RISK]`/`[MODERATE RISK]`/`[HEALTHY]` | **Medium** — can duplicate item #7 from portfolio summary |
| 29 | PL balance remaining (%) | `pl_balance_remaining_pct` | `[HIGH RISK]`/`[MODERATE]`/`[POSITIVE]` | Low |
| 30 | Unsecured enquiries 12M | `unsecured_enquiries_12m` | `[HIGH RISK]`/`[MODERATE RISK]`/`[HEALTHY]` | Low |
| 31 | Trade-to-enquiry ratio (unsec 24M) | `trade_to_enquiry_ratio_uns_24m` | `[POSITIVE]`/`[CONCERN]` | Low |
| 32 | Loan acquisition velocity (IPT) — PL/BL 12M, 6M; All 24M; Consumer 12M; HL/LAP; TWL | `interpurchase_time_*` fields | `[HIGH RISK]`/`[CONCERN]`/`[HEALTHY]` | Low |

### 2.7 Composite Risk Signals (from `_compute_interaction_signals()`)

| # | Signal | Trigger Condition | Hallucination Risk |
|---|--------|-------------------|-------------------|
| 33 | CREDIT HUNGRY + LOAN STACKING | enquiries > threshold AND new_pl_6m ≥ trigger | Low — deterministic |
| 34 | RAPID PL STACKING | IPT_PLBL < concern AND new_pl_6m ≥ trigger | Low |
| 35 | CLEAN REPAYMENT PROFILE | All DPD = 0, missed = 0, pct_0plus = 0 | Low |
| 36 | PAYMENT TIMING NUANCE | missed = 0% but DPD > 0 detected | **Protective** — explicitly tells LLM not to call payment record "clean" |
| 37 | ELEVATED LEVERAGE | CC util > threshold AND PL bal > threshold | Low |
| 38 | LOW CONVERSION | High enquiries but low trade ratio | Low |

### 2.8 Exposure Trend (from `monthly_exposure`)

| # | Data Point | Source / Computation | Hallucination Risk |
|---|------------|---------------------|-------------------|
| 39 | 12M sanctioned exposure trend (direction, %, from→to) | Point-in-time comparison: `totals[-1]` vs `totals[-13]` | Low |
| 40 | 6M avg exposure trend (direction, %, prior→recent) | Average of last 6 months vs prior 6 months | Low |
| 41 | **Exposure Commentary** (2 sentences) | `summarize_exposure_timeline()` — peak month/amount/products + current state/trend | Low — fully deterministic text |

---

## 3. Combined Executive Summary — Data Point Map

**Prompt:** `COMBINED_EXECUTIVE_PROMPT` (`config/prompts.py:359`)
**Caller:** `generate_combined_executive_summary()` (`pipeline/reports/report_summary_chain.py:966`)
**Input:** Banking summary (LLM text), Bureau summary (LLM text), additional structured data
**Output sections:** Income & Credit Profile (4-5 lines), Obligations Risk & Assessment (3-4 lines)

| # | Data Point | Source | Type | Hallucination Risk |
|---|------------|--------|------|--------------------|
| 1 | `banking_summary` | Output of `generate_customer_review()` — **already LLM-generated text** | LLM output | **CRITICAL** — LLM-on-LLM compounding. Any hallucination in banking review propagates here |
| 2 | `bureau_summary` | Output of `generate_bureau_review()` — **already LLM-generated text** | LLM output | **CRITICAL** — same compounding risk |
| 3 | FOIR (total) % | `tradeline_features.foir` — extracted in `combined_report.py:111` | Structured | Low |
| 4 | FOIR (unsecured) % | `tradeline_features.foir_unsec` | Structured | Low |
| 5 | Kotak (On-Us) context | `ei.on_us_total_tradelines`, products, sanctioned, outstanding | Structured | Low |
| 6 | Joint loans | `ei.total_joint_count`, `joint_product_types` | Structured | Low |
| 7 | Largest single loan (INR, type) | `ei.max_single_sanction_amount`, `max_single_sanction_loan_type` | Structured | Low |
| 8 | Exposure commentary (2 sentences) | `summarize_exposure_timeline()` — deterministic | Structured | Low |
| 9 | `customer_id` (masked) | `mask_customer_id()` | Identifier | Low |

---

## 4. Data Overlap & Duplication Matrix

This matrix shows where the **same underlying data point** appears in multiple prompts, creating risk of repeated/contradictory narration.

| Data Point | Banking Prompt | Bureau Prompt | Combined Prompt | Duplication Risk |
|------------|:-------------:|:-------------:|:---------------:|-----------------|
| Salary / Income amount | Direct (item 3) | Indirect via `affluence_amt` | Via banking_summary text | **HIGH** — banking uses banking-detected salary; bureau uses affluence estimate. Combined sees both and may state two different income figures. |
| FOIR | Banking FOIR (EMI+Rent/Salary) | Bureau FOIR (from tl_features) | Both via summaries + explicit `foir_context` | **HIGH** — two independent FOIR calculations (banking vs bureau) with different denominators. Combined prompt receives both and may conflate them. |
| CC Utilization | Not present | Portfolio summary (#7) AND Behavioral features (#28) | Via bureau_summary text | **MEDIUM** — appears twice in bureau prompt data (once from product_breakdown loop, once from tradeline_features). LLM may state it twice. |
| Exposure trend | Not present | Trend lines (#39-40) AND Commentary (#41) | Via bureau_summary text + explicit `exposure_summary` | **HIGH** — combined prompt receives the bureau LLM's narration of exposure AND the raw exposure commentary as `additional_context`. Same info, two forms. |
| Kotak on-us | Not present | On-us block (#14-17) | Via bureau_summary text + explicit `foir_context` | **MEDIUM** — combined prompt gets it from both the bureau LLM narration and the additional data block. |
| EMI / Loan obligations | Banking EMI (item 4) | Bureau EMI obligation (item 9) | Via both summaries | **MEDIUM** — banking counts EMI from narration keywords; bureau has pre-computed bureau EMI. Different numbers for same concept. |
| Max DPD | Not present | Portfolio (#6) + Behavioral features (#23) | Via bureau_summary text | **MEDIUM** — DPD appears in portfolio summary AND in behavioral features section. LLM may narrate twice. |
| Missed payments vs DPD | Not present | Items #25 + #23 + Composite #36 | Via bureau_summary text | **MEDIUM** — the contradiction (0% missed but DPD > 0) is explicitly handled by composite signal, but the LLM may still narrate both positively and negatively. |

---

## 5. Hallucination Risk Analysis

### 5.1 High-Risk Scenarios

| Scenario | Root Cause | Current Mitigation | Gap |
|----------|-----------|-------------------|-----|
| **LLM invents salary employer name** | Prompt receives salary amount but merchant name may be truncated narration text (e.g., "KOTAK" from "KOTAK MAHINDRA BANK LTD") | None — raw narration passed as-is | LLM may expand "KOTAK" to "Kotak Mahindra Bank Ltd" (correct) or invent a company name if narration is garbled |
| **LLM fabricates missing sections** | Bureau prompt has no CC data → LLM's training on financial reports causes it to "fill in" CC utilization | Product-existence guards (`has_cc`, `has_pl`) suppress absent products in behavioral features | Portfolio summary loop (`product_breakdown`) may still include a 0.0% utilization line for a closed CC (None vs 0.0 confusion) |
| **Combined summary double-counts exposure** | Exposure data enters combined prompt via (1) bureau_summary text, (2) explicit exposure_summary | None | LLM receives same data twice in different forms; likely narrates exposure twice |
| **Combined summary creates conflicting FOIR** | Banking FOIR = (EMI+Rent)/Salary, Bureau FOIR = bureau obligation/affluence income. Different denominators, different numerators. | Prompt says "if bureau FOIR is present, quote exact" and "if banking FOIR is present, quote it" | LLM may state "FOIR is 45%" from one source and "FOIR is 62%" from another without clarifying which is which |
| **Account quality conduit label leaks** | Prompt rule says "do NOT mention numeric scores or classifications" but `observations` list may include phrases like "primary account characteristics" | Prompt instruction | LLM follows the instruction inconsistently with local models |
| **Event detector false positives become "facts"** | Event descriptions are passed with `[HIGH]` severity tag, making LLM treat them as confirmed facts | Prompt says "narrate EVERY event" — no filtering by confidence | See Section 6 |

### 5.2 Medium-Risk Scenarios

| Scenario | Root Cause | Impact |
|----------|-----------|--------|
| Merchant fuzzy grouping errors | `fuzzywuzzy` groups "HDFC BANK" and "HDFC LIFE" as same merchant | Inflated transaction counts for merged entity; wrong bidirectional flow detection |
| Bidirectional merchant false links | Same fuzzy issue — credits to "KOTAK MF" and debits to "KOTAK BANK" become a "two-way merchant" | LLM narrates a false round-trip pattern |
| Small-sample IPT (inter-purchase time) | With only 2-3 transactions, IPT of "45 days" is statistically meaningless | LLM presents it as a behavioral pattern |
| Absent data hallucination suppression | `DATA NOT AVAILABLE` list is appended to banking prompt but **not** to bureau prompt | Bureau LLM may invent data for products not in the portfolio |

---

## 6. Event Detection — False Positive & Hallucination Audit

### 6.1 Event Types and Risk Assessment

| Event Type | Detection Method | Significance | False Positive Risk | Recommendation |
|------------|-----------------|-------------|--------------------|----|
| `pf_withdrawal` | Keywords: EPFO, PF SETTL, PF WITHDRAWAL, etc. | HIGH | **Medium** — "EPFO" is fairly specific, but "PF CREDIT" could match "PLATFORM CREDIT" | Add negative keywords |
| `fd_closure` | Keywords: FD CLOSURE, FD MATURITY, PREMATURE CLOSURE | MEDIUM | **High** — "FD CLOSURE INTEREST" matches but is just interest, not an actual closure | Already flagged in `hallucination_fix_plan.md` |
| `salary_advance_bnpl` | Keywords: EARLY SALARY, LAZYPAY, SIMPL, SLICE, KREDITBEE, etc. | HIGH | **Medium** — "SLICE " (with space) is reasonable, but "SIMPL" could match "SIMPLE TRANSFER" | Add word boundary or negative keywords |
| `sip_investment` | Keywords: SIP, MUTUAL FUND, MF, BSE STAR MF | POSITIVE | **High** — "SIP" matches "GOSIPURA", "MSIPS" (substring) | Needs word boundary regex |
| `insurance_premium` | Keywords: LIC, HDFC LIFE, ICICI PRU, etc. | POSITIVE | **High** — "LIC" matches "LICENCE", "PUBLIC" | Needs word boundary regex |
| `govt_benefit` | Keywords: PM KISAN, MNREGA, DBT, SCHOLARSHIP | MEDIUM | **Medium** — "DBT" is very short, matches "DBTL" or similar | Add minimum match length |
| `ecs_bounce` | Keywords from `ECS_BOUNCE_KEYWORDS` | HIGH | **Low** — ECS/NACH bounce narrations are fairly specific | Keep |
| `mandate_emi` | Keywords from `MANDATE_EMI_KEYWORDS`, min_months=2 | MEDIUM | **Low** — requires ≥2 months occurrence | Keep |
| `emi_debit` | Keywords from `EMI_NARRATION_KEYWORDS`, min_months=2 | MEDIUM | **Low** — multi-month requirement reduces false positives | Keep |
| `home_loan_emi` | Keywords from `HOME_LOAN_EMI_KEYWORDS`, min_months=2 | MEDIUM | **Low** | Keep |
| `cc_payment` | Keywords from `CC_PAYMENT_KEYWORDS`, min_months=2 | POSITIVE | **Low** | Keep |
| `land_payment` | Keywords from `LAND_PAYMENT_KEYWORDS` | MEDIUM | **Medium** — depends on keyword specificity | Review keywords |
| `loan_disbursal` | Keywords from `LOAN_DISBURSEMENT_KEYWORDS` | HIGH | **Medium** — common bank narration phrases may match | Review keywords |
| `self_transfer_post_salary` | Custom: debit ≥40% salary within 3 days of salary credit + self-transfer keywords | HIGH | **High** — "SELF" in narration can be "SELF PAY" (bill payment), not actual self-transfer | Needs negative keyword list |
| `post_salary_routing` | Custom: 2+ distinct recipients within 48h of salary | HIGH | **Medium** — legitimate bill payments on payday trigger this | Needs exclusion for known bill merchants |
| `loan_redistribution` | Custom: large credit (>salary) followed by multiple large debits | HIGH | **Medium** — bonus + shopping spree looks like redistribution | Consider minimum debit count threshold |
| `post_disbursement_usage` | Custom: spending spike after loan disbursal credit | HIGH | **Medium** | Requires loan_disbursal to be correctly detected first |
| `round_trips` | Custom: similar credit+debit amounts within window to same counterparty | MEDIUM | **Medium** — refunds and reversals trigger this | Consider excluding known refund narrations |
| `credit_spend_dependency` | Custom: spending spike within days of large credit | MEDIUM | **Medium** | Salary → spending is normal behavior |
| `inflow_spike` | Custom: monthly inflow > 2x average | MEDIUM | **Low** — statistical threshold | Keep |
| `large_single_credit` | Custom: single credit > 3x salary | HIGH | **Low** — clear threshold | Keep |
| `atm_withdrawals` | Custom: ATM trend analysis + address extraction | MEDIUM | **Low** — ATM narrations are distinctive | Keep |

### 6.2 Event Detection Verdict

**Is event detection worth including in the banking prompt?**

**Partially.** The keyword-based events with `min_months ≥ 2` (SIP, insurance, EMI, CC payments) are relatively reliable positive signals. The custom multi-step detectors (post-salary routing, self-transfer, round-trips) have **unacceptably high false positive rates** for direct LLM narration.

**Problem:** The prompt says `"narrate EVERY event listed"` — this means ONE false positive event becomes a fabricated fact in the summary. Unlike other data points (which are numbers the LLM quotes), events are qualitative descriptions that the LLM embellishes further.

**Current pipeline:**
```
Raw narrations → keyword match → event dict with description → format_events_for_prompt() → LLM narrates as fact
```

**There is no confidence scoring, no validation layer, and no filtering by reliability.**

---

## 7. Redundancy in Combined Summary (LLM-on-LLM)

### The Core Issue

```
Banking data → LLM₁ → banking_summary (text)  ──┐
                                                   ├─→ LLM₃ → combined_summary
Bureau data  → LLM₂ → bureau_summary (text)   ──┘
                       + additional structured data
```

LLM₃ receives **two LLM-generated texts** as its primary input. This creates three problems:

1. **Hallucination compounding**: If LLM₁ invents a salary employer name, LLM₃ treats it as fact and may elaborate further.
2. **Information loss**: LLM₁ and LLM₂ summarize 30+ data points each into 2 paragraphs. LLM₃ then summarizes those summaries into 2 paragraphs. Key data points get dropped.
3. **Duplication with structured data**: The `additional_context` block passes FOIR, exposure, and on-us data that was ALREADY narrated by LLM₂ in `bureau_summary`. LLM₃ sees the same facts twice.

### Specific Duplication Paths in Combined

| Data Point | Path 1 (via LLM summary) | Path 2 (via additional_context) | Result |
|------------|--------------------------|--------------------------------|--------|
| FOIR | Bureau LLM narrates FOIR from data summary | `foir_context` passes exact FOIR% | LLM₃ may state FOIR twice |
| Exposure trend | Bureau LLM narrates exposure from trend data | `exposure_summary` passes same 2-sentence commentary | LLM₃ may narrate exposure trend twice |
| On-us exposure | Bureau LLM includes on-us section | `foir_context` includes "Kotak (On-Us): X tradelines..." | Duplicated |
| Joint loans | Bureau LLM may mention joint loans | `foir_context` includes "Joint Loans: X tradeline(s)..." | Duplicated |
| Banking FOIR | Banking LLM narrates banking FOIR | Not in additional_context (but bureau FOIR IS) | Two different FOIR values from different sources — confusing |

---

## 8. Prompt Chaining & Optimization Strategies

### 8.1 Strategy A — Eliminate LLM-on-LLM for Combined Summary

**Current:** LLM₁ → text, LLM₂ → text → LLM₃ merges texts
**Proposed:** Feed structured data directly to LLM₃ instead of LLM-generated text

```python
# Instead of:
generate_combined_executive_summary(
    banking_summary=banking_text,    # LLM output
    bureau_summary=bureau_text,      # LLM output
    ...
)

# Do:
generate_combined_executive_summary(
    banking_data=_build_data_summary(customer_report),  # structured data
    bureau_data=_build_bureau_data_summary(executive_inputs, tradeline_features),  # structured data
    ...
)
```

**Pros:** Eliminates hallucination compounding. LLM₃ works from the same deterministic data as LLM₁ and LLM₂.
**Cons:** Longer prompt (more tokens). May lose the "narrative flow" that LLM₁/LLM₂ produce.
**Effort:** Medium — need new prompt template, pass data builders to combined flow.

### 8.2 Strategy B — Confidence-Gated Event Injection

Add a confidence field to events and filter before injecting into the prompt:

```python
def format_events_for_prompt(events, min_confidence="medium"):
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    filtered = [e for e in events
                if confidence_order.get(e.get("confidence", "low"), 2)
                <= confidence_order[min_confidence]]
    ...
```

**Classification rules:**
- `high confidence`: Keyword events with `min_months ≥ 2` + specific keywords (ECS bounce, NACH EMI)
- `medium confidence`: Single-occurrence keyword events with specific keywords (PF, loan disbursal)
- `low confidence`: Custom multi-step detectors (post-salary routing, round-trips, self-transfer) + short substring keywords (SIP, LIC, DBT)

### 8.3 Strategy C — Deduplication in Bureau Prompt Data

Remove CC utilization from the `product_breakdown` loop since it's already covered in behavioral features:

```python
# In _build_bureau_data_summary(), line 807-812:
# Remove the CC utilization from the product_breakdown iteration
# It's already covered in _format_tradeline_features_for_prompt() item #28
```

Similarly, consider suppressing max DPD from the portfolio summary header when it's covered in detail in the behavioral features section with per-product breakdown.

### 8.4 Strategy D — Two-Pass Summary with Self-Correction

Use a chained prompt pattern where the first pass generates, and the second pass verifies:

```
Pass 1: Generate summary from structured data (same as current)
Pass 2: "Verify the following summary against the source data.
         Flag any claim not directly supported by the data.
         Remove or correct flagged claims."
```

**Pros:** Catches fabricated claims.
**Cons:** Doubles latency and LLM cost. Local models (llama3.2) may not reliably catch their own errors.
**Verdict:** Not practical with current local model quality.

### 8.5 Strategy E — Structured Output with Post-Hoc Assembly

Instead of asking the LLM to write a free-form paragraph, ask for structured JSON:

```json
{
    "income_summary": "...",
    "cashflow_summary": "...",
    "credit_portfolio": "...",
    "risk_assessment": "...",
    "overall_verdict": "positive|cautious|negative"
}
```

Then assemble the final narrative from these structured sections in Python. This prevents:
- Information reordering that causes repetition
- The LLM adding context not in its assigned section
- Risk assessments appearing multiple times

**Pros:** More control over output structure. Easier to validate per-section.
**Cons:** Less natural prose. Requires post-hoc stitching logic.
**Effort:** Medium.

### 8.6 Strategy F — Prompt Segmentation (Section-wise Generation)

Instead of one monolithic prompt producing 2 paragraphs, use separate prompts for each section:

```
Prompt 1 (Portfolio Overview): structured data → LLM → paragraph 1
Prompt 2 (Behavioral Insights): behavioral features only → LLM → paragraph 2
```

**Pros:** Each prompt sees only the data it needs — reduces cross-contamination. Easier to debug which prompt causes which hallucination.
**Cons:** More LLM calls (latency). Paragraphs may not flow together naturally.
**Best for:** Bureau prompt, which already has a clear 2-paragraph structure.

---

## 9. Recommendations Summary

### Priority 1 — Quick Wins (Low effort, High impact)

| # | Action | Impact | File(s) |
|---|--------|--------|---------|
| 1 | **Add `DATA NOT AVAILABLE` block to bureau prompt** (same pattern as banking) | Prevents LLM from inventing absent product data | `report_summary_chain.py` |
| 2 | **Remove CC utilization from product_breakdown loop** (deduplicate with behavioral features) | Prevents LLM from narrating CC util twice | `report_summary_chain.py:807-812` |
| 3 | **Add confidence scoring to events** and filter `low` confidence events from prompt | Reduces false positive events entering LLM narration | `event_detector.py`, `report_summary_chain.py` |
| 4 | **Add word-boundary enforcement to SIP, LIC, DBT keywords** | Eliminates substring false positives like GOSIPURA, LICENCE | `config/keywords.py` or `event_detector.py:_kw_to_regex()` |

### Priority 2 — Structural Fixes (Medium effort, High impact)

| # | Action | Impact | File(s) |
|---|--------|--------|---------|
| 5 | **Feed structured data (not LLM text) to combined summary prompt** | Eliminates LLM-on-LLM hallucination compounding | `combined_report.py`, `report_summary_chain.py`, `config/prompts.py` |
| 6 | **Remove duplicate data paths in combined prompt** (exposure, FOIR, on-us from both summary text AND additional_context) | Prevents double-narration of same data points | `combined_report.py:96-147` |
| 7 | **Differentiate banking FOIR from bureau FOIR explicitly** in combined prompt with labels | Prevents conflation of two different FOIR calculations | `config/prompts.py` (combined prompt), `combined_report.py` |

### Priority 3 — Prompt Engineering (Medium effort, Medium impact)

| # | Action | Impact | File(s) |
|---|--------|--------|---------|
| 8 | **Switch to structured JSON output** for bureau and combined prompts with post-hoc assembly | More controlled output, easier validation | `config/prompts.py`, `report_summary_chain.py` |
| 9 | **Section-wise prompt generation** for bureau summary (separate portfolio vs behavioral) | Isolates data per section, reduces cross-contamination | `report_summary_chain.py` |
| 10 | **Post-generation regex validation** — check that key numbers in the summary match source data | Catches number fabrication before rendering | New module or addition to `report_summary_chain.py` |

### Not Recommended

| Action | Why Not |
|--------|---------|
| Two-pass self-correction (Strategy D) | Local models (llama3.2) lack the meta-reasoning to reliably catch their own errors. Doubles latency for marginal gain. |
| Removing event detection entirely | Legitimate high-confidence events (ECS bounce, PF withdrawal, loan disbursal) are valuable signals. The solution is filtering, not removal. |
| Removing LLM narration entirely (pure template) | Narration is a core product requirement. The goal is to make narration more reliable, not to eliminate it. |

---

*Last updated: 2026-03-25*
*Derived from code analysis of: `pipeline/reports/report_summary_chain.py`, `config/prompts.py`, `tools/event_detector.py`, `tools/account_quality.py`, `tools/combined_report.py`, `config/keywords.py`*
