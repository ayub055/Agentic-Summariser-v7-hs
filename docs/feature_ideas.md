# Feature & Event Ideas — Banking Report

> Reference document for future implementation. Ideas sourced from architecture review session.

---

## 1. Financial Overview — Variables to Add (from Existing Data)

These can be added to `_build_data_summary()` with no new tools.

| Variable | How to Compute | Why Useful |
|---|---|---|
| **FOIR** | `(sum(EMI) + rent) / salary.avg_amount × 100` | #1 lending metric — lender cutoff typically 40–65% |
| **Savings rate** | `(total_inflow - total_outflow) / total_inflow` | Indicates financial discipline |
| **Income months present** | months with a salary credit vs total months analyzed | Salary consistency without a new tool |
| **Negative cashflow months** | count of months where net < 0 | Signals periods of financial stress |
| **Cash withdrawal concentration** | ATM category spend / total debit spend | High ratio = untrackable spending |
| **Betting/gaming exposure** | `category_overview["Digital_Betting_Gaming"]` if present | Direct red flag — surface the rupee amount |
| **P2P volume** | `category_overview["P2P"]` if present | Signals informal money movement |
| **Expense trend** | last 3-month avg outflow vs first 3-month avg outflow | Rising = deteriorating cashflow |
| **Inflow concentration** | salary / total_inflow × 100 | Single-source income = fragile; multi-source = resilient |

---

## 2. New Computed Features (Require New Logic)

High-value for lending scorecard; not yet computed anywhere.

| Feature | Computation | Risk Signal |
|---|---|---|
| **Cheque/NACH bounce count** | Count narrations: `MANDATE RETURN`, `ECS RETURN`, `NACH RETURN`, `CHEQUE BOUNCE`, `DISHONOUR`, `DISHR` | Very high risk — direct delinquency proxy |
| **Income volatility (CV)** | `std(monthly_salary_credits) / mean(monthly_salary_credits)` | CV > 0.3 = unstable income |
| **Salary gap months** | Missing salary months in a run where salary was previously consistent | Job loss / income disruption signal |
| **Salary increment** | Latest 3-month avg salary vs earliest 3-month avg salary (% change) | Positive: career growth |
| **Cumulative balance proxy** | Running sum of monthly_net | Direction: accumulating or depleting savings |
| **Discretionary ratio** | (Food + Fashion + Entertainment + Travel) / total_outflow | >40% = lifestyle-heavy |
| **Essential ratio** | (EMI + Rent + Grocery + Pharmacy + Bills) / total_outflow | Benchmark for financial discipline |
| **Crypto/exchange exposure** | Narration match: `BINANCE`, `WAZIRX`, `COINDCX`, `ZEBPAY`, `UNOCOIN` | Volatile asset speculation risk |

---

## 3. New Events to Detect

### 3a. High Risk (Negative)

| Event | Detection Logic | Significance |
|---|---|---|
| **Cheque/NACH/mandate bounce** | Keywords: `MANDATE RETURN`, `NACH RETURN`, `ECS RETURN`, `CHEQUE BOUNCE`, `DISHONOUR`, `DISHR` — per-occurrence | HIGH |
| **Salary gap** | Salary present 3+ months, then absent 2+ consecutive months | HIGH |
| **High cash withdrawal pattern** | ATM/cash > 30% of salary in 3+ months | MEDIUM |
| **Circular loan repayment** | Loan disbursal followed by same-day or next-day EMI/repayment outflow | HIGH |
| **Crypto/exchange deposits** | `BINANCE`, `WAZIRX`, `COINDCX`, `ZEBPAY` in narrations | MEDIUM |
| **Betting/gaming transactions** | `Digital_Betting_Gaming` category present — surface total per month with narration samples | HIGH |
| **Recurring negative cashflow** | 3+ consecutive months with net < 0 | HIGH |
| **Foreign transactions** | `category_of_txn == Foreign_Transaction` with total amount | MEDIUM |
| **Multiple salary sources** | Credits from 2+ distinct payroll narration patterns in same month | MEDIUM |
| **Overdraft signal** | Large debit immediately after near-zero net in a month | MEDIUM |

### 3b. Positive

| Event | Detection Logic | Significance |
|---|---|---|
| **Consistent SIP** | Already partial — refine to extract fund house name and monthly amount | POSITIVE |
| **Salary increment** | 10%+ sustained salary increase in last 3 months vs prior 3 months | POSITIVE |
| **FD creation** | Keywords: `FD CREATED`, `FD BOOKING`, `FIXED DEPOSIT BOOK` | POSITIVE |
| **Zero negative cashflow months** | All analyzed months net positive — mention streak count | POSITIVE |
| **Loan pre-closure** | Keywords: `PRECLOSURE`, `LOAN PRECL`, `PART PAYMENT` | POSITIVE |
| **Regular insurance premium** | Already detected — refine to extract policy/insurer name and exact amount | POSITIVE |
| **Recurring charitable giving** | `Charity_Donations` category across 2+ months | POSITIVE |

---

## 4. Priority Order for Implementation

1. **Cheque/NACH bounce** — highest signal-to-noise, zero false positives, direct delinquency proxy
2. **FOIR** — lenders use as hard cutoff; computable from data already in `CustomerReport`
3. **Salary gap / inconsistency** — second most important income signal after amount
4. **Betting/gaming exposure** — value already in `category_overview`, just needs surfacing in events
5. **Salary increment** — strong positive signal, easy to derive from salary transactions list
6. **Crypto/exchange** — increasingly relevant risk flag

---

## 5. Closing the Gap Between Claude and the Current System

### The Problem

Claude produces richer reports from the same data because it performs two extra steps the current system does not:

| Step | Current System | Claude |
|---|---|---|
| **What happened** | ✅ Event narration | ✅ |
| **What it means** | ❌ Missing | ✅ Interprets each signal |
| **What it implies** | ❌ Missing | ✅ Cross-signal inference |

The fix is to encode domain knowledge deterministically in Python so the LLM only narrates — not reasons.

> **Principle: Every insight Claude produces that the system misses is a hardcoded rule waiting to be written.**

```
Current:  raw data → [annotated features] → LLM (narrate + reason)
Target:   raw data → [annotated features + interaction signals + behavioral classification] → LLM (narrate only)
```

---

### 5a. Richer Bureau Variable Interaction Signals

`_compute_interaction_signals()` in `report_summary_chain.py` already exists but its **interpretation text is too weak** — it states numbers without explaining what the combination means.

**Current (weak):**
```
ELEVATED LEVERAGE: CC utilization at 90.0% and 75.0% PL balance still outstanding
```

**Target (interpretive):**
```
DUAL LEVERAGE — CRITICAL: CC utilization at 90% (maxing revolving credit) while 75% of PL balance remains outstanding. Customer is simultaneously credit-dependent on both revolving and term products — combined repayment pressure far exceeds either metric in isolation.
```

**Missing interaction signals to add:**

| Signal Combination | Interpretation to Encode |
|---|---|
| CC util >75% AND PL remaining >60% | "Dual leverage — revolving and installment burden simultaneously elevated; combined credit stress" |
| Clean DPD (0) AND CC util >75% | "No delinquency but sustained high utilization indicates credit dependency, not disciplined management" |
| New PLs in 6M ≥2 AND PL remaining >70% | "New loan opened while previous is barely repaid — rollover borrowing / debt cycle pattern" |
| Enquiries >8 AND trade-to-enquiry ratio <30% | "High application volume with low approval rate — probable repeated rejections from other lenders" |
| Enquiries high AND new PLs low | "Credit hungry but unable to access — suggests lenders are declining applications" |
| High IPT (slow acquisition) AND clean DPD | "Measured, disciplined borrower — loans taken infrequently and repaid cleanly" |
| 0% missed payments AND DPD >0 | "Technically not missed but consistently paid late — do NOT characterise repayment as clean" |
| PL balance remaining high AND months since last trade low | "Recently opened loan with most balance unpaid — high fresh-credit risk" |

**Implementation:** Extend `_compute_interaction_signals()` with these rules. The text should carry the **interpretation**, not just the numbers, so the LLM narrates rather than infers.

---

### 5b. Banking Account Behavior Classifier

A new deterministic module that classifies the account's **behavioral role** before the LLM sees the data.

**Why:** When the system reports "30% of salary distributed to 2 recipients within 48h," Claude infers "probable non-primary account." This inference should be a rule, not an LLM guess.

**Account type taxonomy:**

| Type | Detection Rule | What to Tell the LLM |
|---|---|---|
| **PRIMARY** | Salary received AND accumulates (positive net most months) AND spending spread over time | "Account shows characteristics of a primary operating account — salary received and retained" |
| **CONDUIT** | Salary in → single large self-transfer out within 1–3 days (≥60% of salary) | "Account functions as a conduit — salary credited then routed to another account; this may not be the customer's main account" |
| **DISTRIBUTION HUB** | Salary in → 2+ distinct recipients within 72h (>50% of salary) across 2+ months | "Account used as a distribution hub — salary consistently redistributed to multiple parties; primary account likely elsewhere" |
| **SECONDARY / EXPENSE** | No salary; irregular credits; predominantly debit activity | "Account appears to be a secondary expense account — no salary inflow, used primarily for spending" |
| **SAVINGS-ORIENTED** | Consistent positive net; FD/SIP activity; low discretionary ratio | "Account exhibits savings-oriented behavior — consistent surplus retained and invested" |

**Computed metrics needed:**
- `distribution_ratio` = total debits within 72h of salary / salary amount (avg across months)
- `self_transfer_ratio` = self-transfers within 72h of salary / salary amount
- `accumulation_score` = months with positive net / total months
- `recipient_diversity_post_salary` = avg unique recipients of post-salary debits

**Output to LLM prompt:**
```
ACCOUNT BEHAVIOR CLASSIFICATION: DISTRIBUTION HUB
Evidence: In 4 of 6 months, 55–70% of salary was redistributed to 2–3 recipients within 48h.
Implication: This is likely not the customer's primary account. Income and expenses of the actual primary account are not visible here.
```

---

### 5c. Event → Implication Mapping

Currently events describe what happened. They should also carry what it **implies** for lending.

| Event Type | Current Description | Implication to Add |
|---|---|---|
| `self_transfer_post_salary` | "₹72,000 transferred to own account next day" | "Salary not retained here — account may be a routing step, not where the customer actually lives financially" |
| `post_salary_routing` | "₹X distributed to 2 recipients within 48h" | "Probable non-primary account — actual spending patterns not visible" |
| `salary_advance_bnpl` | "EarlySalary credit of ₹15,000" | "Customer bridging income gaps with high-cost credit — indicates cashflow stress between paydays" |
| `pf_withdrawal` | "EPFO credit of ₹X" | "Withdrawal of long-term retirement savings suggests acute financial stress — should not be treated as income" |
| `loan_redistribution_suspect` | "₹X from lender, redistributed" | "Loan proceeds immediately redistributed — funds may be servicing other obligations or being channeled; actual utilization unverifiable" |
| `cheque_bounce` | "NACH RETURN on date X" | "Failed repayment mandate — direct evidence of payment default; lenders typically treat this as a delinquency signal" |

**Implementation:** Add an `implication` field to each event dict. `format_events_for_prompt()` appends it after the description so the LLM narrates the implication without needing to derive it.

---

### 5d. Priority Order for Gap-Closing Implementation

1. **Richer interaction signal text** — lowest effort, highest immediate impact on report quality; just edit string templates in `_compute_interaction_signals()`
2. **Account behavior classifier** — medium effort, high impact; new function `classify_account_behavior()` called in `detect_events()` or `customer_report_builder.py`, output added to prompt
3. **Event implication field** — low effort; add `implication` key to each event dict in `event_detector.py`, render it in `format_events_for_prompt()`
4. **Missing bureau interactions** (clean DPD + high util, rejection pattern, rollover borrowing) — medium effort; extend `_compute_interaction_signals()`

---

## 6. How to Build a Reasoner Like Claude

### What Makes Claude Better

Claude outperforms the current system because it brings three things the system lacks:

| Capability | Claude | Current System |
|---|---|---|
| **Domain knowledge** | Trained on credit risk literature, RBI guidelines, CIBIL docs, thousands of credit reports | Only what is explicitly encoded in Python rules |
| **Cross-signal reasoning** | Sees all features simultaneously, finds non-obvious connections | Features annotated independently, no cross-feature synthesis |
| **Communication** | Writes professional prose naturally | LLM narrates pre-labelled observations |

Points 1 and 2 can be replicated deterministically in Python. Point 3 is where the LLM earns its place.

---

### Path 1 — Encode Domain Knowledge Explicitly (Already Started)

The `_compute_interaction_signals()` pattern is correct. Every rule Claude applies can be written as Python — it is more reliable because it is deterministic and auditable.

**Gap today:** ~20 interaction rules encoded; credit risk literature contains ~200+. Systematically working through RBI guidelines, CIBIL scoring documentation, and bank credit policy documents and encoding them as Python rules closes this gap entirely.

**Ceiling:** Novel or unusual customer profiles not covered by any rule will still be handled weakly.

---

### Path 2 — Structured Reasoning Trace (Highest Leverage)

Instead of sending annotated features to the LLM and hoping it reasons well, generate a full reasoning document first — then the LLM only writes sentences.

```
Step 1: Feature extraction        → raw numbers
Step 2: Individual annotation     → [HIGH RISK], [CLEAN] tags  (already done)
Step 3: Interaction signals        → cross-feature interpretations  (partially done)
Step 4: Behavioral classification  → account type, income stability class
Step 5: Risk verdict               → deterministic rule-based overall assessment
Step 6: LLM                       → converts Step 5 output to professional prose
```

This is what Claude is doing internally — except it does steps 1–5 in its weights. Moving those steps into Python produces a more reliable, auditable, and reproducible system.

**This is the highest-leverage change possible without touching the model.**

---

### Path 3 — Fine-Tune a Small Model on Domain Data

Once the pipeline generates reports at scale, build a training flywheel:

1. Generate reports for 500–1000 customers
2. Domain expert annotates / corrects them
3. Fine-tune a 7B–14B model (Llama 3.1 or Mistral) on `(structured_input → expert_report)` pairs
4. The fine-tuned model learns expert-quality financial report language for Indian banking context
5. It now **outperforms Claude on this specific task** because it is specialised

**What is needed:** ~500 high-quality labelled examples. Fine-tuning takes a few hours on an A100.

**Why better than Claude directly:** Reproducible, auditable, local, faster, cheaper at scale, no data privacy concerns with customer data leaving the organisation.

Paths 1 and 2 are prerequisites — the pipeline must generate good reports before fine-tuning is worthwhile.

---

### Path 4 — Agentic Reasoning Loop

Give the LLM tools and let it reason iteratively across multiple calls:

```
LLM: "I see high CC utilization. What is the PL balance?"
Tool: compute_pl_balance() → 75%
LLM: "Combined with 90% CC util, this is dual leverage. Let me check enquiries..."
Tool: get_enquiry_count() → 11
LLM: "High enquiries + dual leverage = distressed borrower."
→ Final report
```

This is how GPT-4 with function calling works, and what `TransactionPipeline` partially implements. Extended to bureau data it would catch interactions not yet hardcoded.

**Problem:** 5–10 LLM calls per report, non-deterministic, hard to audit. Useful for exploration and finding new rules to encode — not for production report generation.

---

### Path 5 — Retrieval-Augmented Reasoning (RAR)

Build a knowledge base of financial reasoning rules stored as text documents:

```
Rule ID: CC_UTIL_HIGH__PL_BALANCE_HIGH
Trigger: CC utilization > 75% AND PL balance remaining > 60%
Interpretation: Dual leverage — customer is simultaneously maxing revolving credit
  while carrying high installment burden. Combined repayment pressure exceeds
  either metric in isolation.
Source: RBI Circular 2021-45, Credit Risk Management Guidelines
```

At report generation time, retrieve the 5–10 most relevant rules based on the customer's feature vector and inject them into the LLM prompt. The LLM narrates retrieved interpretations rather than deriving them.

**Advantage over hardcoded rules:** Rules stored as text are easier to update and version. A credit risk analyst (non-engineer) can add rules without touching code. Also scales to hundreds of rules without growing the Python codebase.

---

### Recommended Implementation Sequence

| Phase | Action | Effort | Impact |
|---|---|---|---|
| **Now** | Richer interaction signal text — edit string templates in `_compute_interaction_signals()` | Low | High |
| **Now** | Event implication field — add `implication` key to each event dict | Low | Medium |
| **Next sprint** | Account behavior classifier (`classify_account_behavior()`) | Medium | High |
| **Next sprint** | Complete structured reasoning trace (Path 2) | Medium | Very High |
| **After Path 2** | RAR knowledge base for domain rules (Path 5) | Medium | High |
| **After 500+ reports** | Fine-tune 7B–14B model on expert-labelled reports (Path 3) | High | Very High |
| **Exploration only** | Agentic reasoning loop to discover new rules (Path 4) | High | Medium |

### The Honest Ceiling

**80% of Claude's quality** is achievable through Paths 1 and 2 alone — encoding domain knowledge as Python rules and building a complete reasoning trace before the LLM sees data.

The remaining 20% (novel patterns, unusual customers, naturally varied prose) requires either a larger/fine-tuned model or the agentic loop.

Fine-tuning (Path 3) is the only way to **surpass** Claude on this specific task, because a model trained on Indian banking data will outperform a general model in that domain.

---

*Last updated: 2026-03*
