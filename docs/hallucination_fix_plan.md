# Hallucination Elimination & Summary Quality Plan

> **Classification:** Implementation Plan — Anti-Hallucination Hardening
> **Priority:** Critical
> **Scope:** LLM summary generation, event detection, prompt engineering, post-generation validation

---

## Table of Contents

1. [Root Cause Analysis](#1-root-cause-analysis)
2. [Vulnerability Inventory](#2-vulnerability-inventory)
3. [Section A — Prompt-Level Fixes](#3-section-a--prompt-level-fixes)
4. [Section B — Data Pipeline Hardening](#4-section-b--data-pipeline-hardening)
5. [Section C — Post-Generation Validation](#5-section-c--post-generation-validation)
6. [Section D — Event Detector False Positive Elimination](#6-section-d--event-detector-false-positive-elimination)
7. [Section E — Redundancy Removal](#7-section-e--redundancy-removal)
8. [Section F — Tone & Style Consistency](#8-section-f--tone--style-consistency)
9. [Implementation Order](#9-implementation-order)

---

## 1. Root Cause Analysis

### Why Hallucinations Occur

The system has three categories of hallucination sources:

**Category A — Prompt Example Leakage (Banking Summary)**
The `CUSTOMER_PERSONA_PROMPT` asks the LLM to describe "who this customer is" with open-ended instructions. The `CUSTOMER_REVIEW_PROMPT` itself is clean, but the LLM sometimes copies phrasing from the prompt's structural instructions into the output. For example, if the prompt says "e.g. received salary and immediately transferred funds", the LLM may generate that exact phrase even when the customer didn't do this.

**Root cause:** Prompts contain example phrases that the LLM treats as factual data rather than format guidance.

**Category B — Absent Data Hallucination (Bureau Summary)**
When CC utilization is absent (customer has no credit cards), the `_format_tradeline_features_for_prompt()` function correctly guards against including CC metrics via `has_cc` check. However, the `_build_bureau_data_summary()` function iterates `product_breakdown` and includes utilization for any product that has a `utilization_ratio` field set. The problem: `utilization_ratio` in `BureauLoanFeatureVector` defaults to `None`, but if the extractor computes it as `0.0` (zero outstanding on a closed CC), it passes the `is not None` check and gets included as "CC Utilization: 0.0%". The LLM then narrates this as if CC utilization data exists.

More critically: even when data IS correctly omitted from the data summary, the LLM's training on financial reports causes it to "fill in" expected sections. A bureau summary without CC utilization looks "incomplete" to the model, so it invents a number.

**Root cause:** (1) Zero vs None confusion in feature extraction. (2) No explicit "absent product" signals in the prompt data. (3) LLM trained on financial report patterns fills gaps.

**Category C — Event Detector False Positives**
The event detector fires on keyword matches without sufficient contextual validation. For example:
- "SIP" keyword matches "GOSIPURA" or "MSIPS" (substring false positive)
- "LIC" matches "LICENCE FEE" or "PUBLIC WORKS"
- "FD CLOSURE" matches "FD CLOSURE INTEREST" (which is just interest payment, not an actual FD closure)
- Self-transfer detection fires on any debit with "SELF" in narration within 3 days of salary, even if it's a legitimate bill payment labeled "SELF PAY"

**Root cause:** Keyword matching uses `str.contains()` without word boundary enforcement. No negative keyword lists. No contextual validation beyond keyword presence.

---

## 2. Vulnerability Inventory

### V1 — Bureau CC Utilization Hallucination (CRITICAL)
- **File:** `pipeline/reports/report_summary_chain.py` lines 683-689
- **Issue:** `_build_bureau_data_summary()` iterates product_breakdown and includes utilization for any product with `utilization_ratio is not None`. But `0.0` passes this check. Also, even when correctly omitted, the LLM invents a CC utilization number because financial report patterns expect it.
- **Impact:** Bureau summary contains fabricated CC utilization percentages

### V2 — Prompt Example Echo in Banking Summary (CRITICAL)
- **File:** `config/prompts.py` lines 162-177 (CUSTOMER_REVIEW_PROMPT)
- **Issue:** The prompt contains instructional examples like "e.g. received salary and immediately transferred funds to own account". The LLM sometimes echoes these examples as facts about the customer.
- **Impact:** Banking summary contains events/behaviors that didn't actually occur

### V3 — Event Detector Keyword False Positives (HIGH)
- **File:** `tools/event_detector.py` lines 69-137 (KEYWORD_RULES)
- **Issue:** Keywords like "SIP", "LIC", "FD" use substring matching via `str.contains()`. No word boundary enforcement. No negative keyword exclusion list.
- **Impact:** Events reported for customers who have no such events (false positives in report)

### V4 — Self-Transfer Detection Over-Fires (HIGH)
- **File:** `tools/event_detector.py` lines 412-476
- **Issue:** `_is_self()` checks for "SELF" keyword in narration. Many banking narrations contain "SELF" in legitimate contexts: "SELF PAY INSURANCE", "SELF ASSESSMENT TAX". The 40% threshold is too low — a ₹50K salary with a ₹20K rent payment labeled "SELF PAY RENT" would trigger.
- **Impact:** False self-transfer events, especially for customers who pay their own bills

### V5 — Persona Prompt Over-Speculation (MEDIUM)
- **File:** `config/prompts.py` lines 184-198 (CUSTOMER_PERSONA_PROMPT)
- **Issue:** Prompt asks to describe "Who they likely are (profession, lifestyle)" — this explicitly invites speculation. The LLM invents employer names, professions, and lifestyle details not in the data.
- **Impact:** Customer persona contains fabricated personal details

### V6 — Combined Summary Double-Narration (MEDIUM)
- **File:** `config/prompts.py` lines 357-400 (COMBINED_EXECUTIVE_PROMPT)
- **Issue:** The combined summary receives `banking_summary` and `bureau_summary` which are themselves LLM-generated text. The combined LLM re-narrates already-narrated content, compounding any hallucinations from the source summaries. If banking summary hallucinated a CC utilization, the combined summary inherits it.
- **Impact:** Hallucinations propagate and sometimes amplify through the chain

### V7 — Explainer Prompt Too Loose (MEDIUM)
- **File:** `config/prompts.py` lines 148-155 (EXPLAINER_PROMPT)
- **Issue:** The explainer prompt says "provide your insights" — this word invites the LLM to add its own interpretive layer. No "do not invent" guardrail exists in this prompt.
- **Impact:** Query responses may include fabricated insights or advice

### V8 — Missing "Not Present" Signals in Data (MEDIUM)
- **File:** `pipeline/reports/report_summary_chain.py` lines 639-775
- **Issue:** When a product type (CC, HL, etc.) is absent from the portfolio, `_build_bureau_data_summary()` simply omits related lines. But the LLM doesn't know the omission is intentional — it may assume data was accidentally dropped and "helpfully" fill it in.
- **Impact:** LLM generates metrics for products that don't exist in the portfolio

### V9 — Round-Trip Detection Name Matching Too Loose (LOW)
- **File:** `tools/event_detector.py` lines 479-536
- **Issue:** Name matching uses `d_name.lower()[:6] != c_name.lower()[:6]` — first 6 chars. "RAJESH KUMAR" and "RAJESH PATEL" would match as same person. Common Indian name prefixes (RAJESH, SURESH, RAMESH) create false matches.
- **Impact:** False round-trip events between different people with similar names

### V10 — Loan Redistribution Threshold Too Sensitive (LOW)
- **File:** `tools/event_detector.py` lines 357-409
- **Issue:** Any credit ≥ ₹1.5L from a known lender followed by 2+ debits ≥ ₹5K totaling ≥30% triggers "loan redistribution suspect". A home loan disbursal followed by normal bill payments would trigger this. The 30% threshold is too low and ₹5K debit minimum too low.
- **Impact:** Normal post-disbursal spending flagged as suspicious redistribution

### V11 — Redundant LLM Calls in Combined Report (EFFICIENCY)
- **File:** `pipeline/reports/report_summary_chain.py` lines 820-867
- **Issue:** Combined report calls `generate_combined_executive_summary()` which feeds LLM-generated `banking_summary` and `bureau_summary` into another LLM call. This is an LLM-on-LLM-output pattern that (a) compounds hallucinations and (b) wastes inference time.
- **Alternative:** The combined summary could be generated from the same structured data used to generate the individual summaries, not from their LLM outputs.

### V12 — No Output Validation Layer (SYSTEMIC)
- **File:** None — doesn't exist
- **Issue:** LLM outputs are stripped of `<think>` blocks and returned directly. No validation checks:
  - No check that INR amounts in output exist in input data
  - No check that product types mentioned in output exist in portfolio
  - No check for hallucinated entity names (employers, lenders)
  - No check for prompt example phrases appearing verbatim in output
- **Impact:** All hallucination types pass through uncaught

---

## 3. Section A — Prompt-Level Fixes

### A1. Remove All In-Prompt Examples That Could Be Echoed

**File:** `config/prompts.py`

**Current problem in CUSTOMER_REVIEW_PROMPT (line 166):**
```
"do NOT write "primary score 35/100" or "conduit account" — instead describe what actually happened"
```
This contains the phrase "primary score 35/100" which the LLM sometimes echoes.

**Current problem in CUSTOMER_REVIEW_PROMPT (line 172):**
```
"e.g. In Jun 2025, the customer received ₹72,000 salary and transferred ₹72,000 to their own account the next day"
```
This is a specific example with a specific amount. The LLM sometimes generates this exact sentence even for customers who didn't have this pattern.

**Fix:** Replace all in-prompt examples with abstract format descriptions:

```python
CUSTOMER_REVIEW_PROMPT = """You are a senior credit analyst writing a banking transaction review for a loan underwriting committee.

STRICT FACTUAL RULES:
- ONLY use numbers, amounts, dates, and facts that appear in the Financial Data section below
- If a data point is not in the Financial Data, do NOT mention it — do NOT estimate, infer, or fill gaps
- Do NOT echo or paraphrase any instruction text — only narrate the data
- Do NOT use any specific amounts, dates, or events unless they appear verbatim in the data below
- Do NOT mention account classification labels, numeric scores, or internal system terms

PARAGRAPH 1 — FINANCIAL OVERVIEW (4-6 lines):
Factual summary of the customer's banking profile. Cover only the data points present below: salary amount and frequency, monthly cashflow (average net = inflow minus outflow), key spending categories, EMI and rent commitments, utility bills. If Banking FOIR is present, state it as a factual observation. Write as flowing prose, not a list. No risk commentary, no event mentions.

PARAGRAPH 2 — TRANSACTION EVENTS:
If a "DETECTED TRANSACTION EVENTS" block is present below, narrate EVERY listed event as a plain fact with the exact month, amount, and description from the data. Do NOT omit any event. Do NOT add events not listed. Do NOT editorialize — state what happened, not what it means.
If no events block is present, omit this paragraph entirely — do NOT write "no events were detected" or similar.

Financial Data:
{data_summary}

Write the review using ONLY the data above:"""
```

Key changes:
- Removed all concrete examples (₹72,000, Jun 2025, "primary score 35/100")
- Replaced "e.g." patterns with abstract instructions
- Added explicit "do NOT echo instruction text" rule
- Added "do NOT add events not listed" to prevent invented events
- Removed "conduit account" reference (was being echoed)

### A2. Harden Bureau Review Prompt Against Missing-Product Hallucination

**File:** `config/prompts.py`

Add an explicit "product absence" section to BUREAU_REVIEW_PROMPT:

```python
BUREAU_REVIEW_PROMPT = """You are a senior credit analyst writing an executive summary for a loan underwriting committee.

ABSOLUTE RULES — VIOLATION IS A CRITICAL ERROR:
- You may ONLY reference numbers, amounts, percentages, and product types that appear in the Bureau Portfolio Summary below
- If Credit Card data is not present in the summary, do NOT mention CC utilization, CC balance, or any CC metric — not even to say "no CC data"
- If Personal Loan data is not present, do NOT mention PL balance remaining or PL metrics
- NEVER generate, estimate, or round any number — quote exactly as written
- NEVER state a percentage or amount that does not appear word-for-word in the data below
- If a metric section header exists but contains no data lines, treat that entire section as absent

STRUCTURE — EXACTLY TWO PARAGRAPHS:

1. PORTFOLIO OVERVIEW (6-10 lines):
Factual portfolio composition. Start with exact tradeline counts: "N total (M live, P closed)" using the exact Total/Live/Closed values from the data. Then cover: loan products present (ONLY those listed in Product-wise Breakdown), total sanctioned, total outstanding, unsecured exposure. Include CC utilization ONLY if a "CC Utilization" or "Credit Card Utilization" line exists in the data — otherwise skip entirely. Include FOIR and obligation figures ONLY if present. Include exposure trend ONLY if present. No risk commentary — pure facts.

2. BEHAVIORAL INSIGHTS (4-6 lines):
Risk interpretation using ONLY the tagged annotations and composite signals from the data. Every claim MUST cite the exact number backing it. Do NOT state any risk opinion without the supporting data point from the summary below.

PRODUCTS NOT IN THE DATA DO NOT EXIST IN THE PORTFOLIO — DO NOT MENTION THEM.

Bureau Portfolio Summary:
{data_summary}

Write the two-paragraph review using ONLY the data above:"""
```

Key changes:
- Explicit per-product "if not present, do NOT mention" rules
- "word-for-word" requirement for all numbers
- "PRODUCTS NOT IN THE DATA DO NOT EXIST" explicit footer rule
- Removed the example "utilization is elevated at 65%" which was being echoed

### A3. Constrain Persona Prompt to Observed Facts Only

**File:** `config/prompts.py`

**Current (speculative):**
```python
CUSTOMER_PERSONA_PROMPT = """Based on the complete financial profile for customer {customer_id}, describe who this customer is in 4-5 lines.
...
- Who they likely are (profession, lifestyle)
```

**Fix:**
```python
CUSTOMER_PERSONA_PROMPT = """Based on the financial data below for customer {customer_id}, write a 4-5 line factual profile.

RULES:
- Describe ONLY what the data shows — spending patterns, income regularity, financial commitments
- Do NOT guess or infer: profession, employer name, company name, age, gender, family status, or lifestyle
- Do NOT name any employer or company unless that exact name appears in the data below
- If salary source narration shows a company name, you may reference it — otherwise say "salaried" or "income source" without naming

COMPLETE FINANCIAL DATA:
{comprehensive_data}

SAMPLE TRANSACTIONS:
{transaction_sample}

Write a 4-5 line factual customer profile based only on the data:"""
```

### A4. Add Guardrails to Explainer Prompt

**File:** `config/prompts.py`

**Current (too open):**
```python
EXPLAINER_PROMPT = """You are a finance/risk manager. You need to provide your insighsts, based on the data below, provide a clear, concise answer to the user's question.
Include all specific numbers and amounts. Be direct
```

**Fix:**
```python
EXPLAINER_PROMPT = """Answer the user's question using ONLY the data provided below.
Include all specific numbers and amounts from the data. Be direct and factual.
Do NOT add analysis, advice, or insights beyond what the data shows.
Do NOT invent any numbers, percentages, or facts not present in the data.

User Question: {query}
Data:
{data}

Answer (using only the data above):"""
```

### A5. Fix Combined Executive Summary Prompt to Use Structured Data

**File:** `config/prompts.py`

Add a stronger anti-propagation rule:

```python
# Add to COMBINED_EXECUTIVE_PROMPT STRICT RULES section:
"- The BANKING SUMMARY and BUREAU SUMMARY below are pre-written narratives — if either contains a number or claim, verify it appears in the Additional Data section before repeating it. If Additional Data contradicts a summary claim, use the Additional Data figure."
```

---

## 4. Section B — Data Pipeline Hardening

### B1. Add Explicit "Absent Product" Markers to Bureau Data Summary

**File:** `pipeline/reports/report_summary_chain.py`

**Current behavior:** If CC is absent, CC utilization line is simply not included. The LLM doesn't know it's intentionally absent.

**Fix:** After the product breakdown section in `_build_bureau_data_summary()`, add explicit absence markers:

```python
# After the product breakdown loop (around line 726)
# Add explicit absence markers for key products
all_product_types = set(product_breakdown.keys()) if product_breakdown else set()
if LoanType.CC not in all_product_types and "CC" not in str(all_product_types):
    lines.append("\n[NO CREDIT CARD PRODUCTS IN PORTFOLIO — do not mention CC utilization]")
if LoanType.PL not in all_product_types and "PL" not in str(all_product_types):
    lines.append("[NO PERSONAL LOAN PRODUCTS IN PORTFOLIO — do not mention PL metrics]")
if LoanType.HL not in all_product_types and "HL" not in str(all_product_types):
    lines.append("[NO HOME LOAN PRODUCTS IN PORTFOLIO]")
```

### B2. Fix Zero vs None Confusion in Utilization

**File:** `pipeline/reports/report_summary_chain.py` lines 683-689

**Current:**
```python
for loan_type_key, vec in product_breakdown.items():
    vec_data = asdict(vec) if not isinstance(vec, dict) else vec
    util = vec_data.get("utilization_ratio")
    if util is not None:
        lt_display = get_loan_type_display_name(loan_type_key)
        lines.append(f"{lt_display} Utilization: {util * 100:.1f}%")
```

**Fix:** Only include utilization if it's meaningful (product is CC AND has live accounts AND utilization > 0):

```python
for loan_type_key, vec in product_breakdown.items():
    vec_data = asdict(vec) if not isinstance(vec, dict) else vec
    util = vec_data.get("utilization_ratio")
    live_count = vec_data.get("live_count", 0)
    # Only show utilization for CC/revolving products with live accounts and meaningful utilization
    if util is not None and util > 0 and live_count > 0:
        lt_display = get_loan_type_display_name(loan_type_key)
        lines.append(f"{lt_display} Utilization: {util * 100:.1f}%")
```

### B3. Guard Tradeline Features Against Absent Products

**File:** `pipeline/reports/report_summary_chain.py` in `_format_tradeline_features_for_prompt()`

The function already has `has_cc` and `has_pl` guards. But the CC utilization line (line 508-513) uses the tradeline_features value `cc_balance_utilization_pct` which may be set even when no CC exists in the product_breakdown (because tl_features.csv is pre-computed externally).

**Fix:** Add a cross-check: only include CC utilization from tradeline features if CC exists in the product_types AND the product_breakdown has at least one live CC:

```python
# In _format_tradeline_features_for_prompt, before the utilization section:
# Strengthen has_cc to require live CC accounts, not just existence
has_cc_live = has_cc and any(
    (asdict(v) if not isinstance(v, dict) else v).get("live_count", 0) > 0
    for k, v in (product_breakdown or {}).items()
    if k == LoanType.CC or str(k) == "CC"
)
```

Then use `has_cc_live` instead of `has_cc` for the utilization block.

Note: This requires passing `product_breakdown` into the function or adding it as context.

### B4. Sanitize Data Summary Before LLM Invocation

**File:** `pipeline/reports/report_summary_chain.py`

Add a validation step in `generate_customer_review()` and `generate_bureau_review()` that scans the data_summary for known problematic patterns:

```python
def _sanitize_data_summary(data_summary: str) -> str:
    """Remove any lines that have N/A or empty values to prevent LLM fill-in."""
    lines = data_summary.split("\n")
    cleaned = []
    for line in lines:
        # Skip lines that are just headers with no data
        stripped = line.strip()
        if stripped.endswith(":") and not any(c.isdigit() for c in stripped):
            # This is a section header — keep only if next line has data
            cleaned.append(line)
            continue
        # Skip lines with only N/A values
        if stripped and stripped != "N/A" and not stripped.endswith("N/A"):
            cleaned.append(line)
    return "\n".join(cleaned)
```

---

## 5. Section C — Post-Generation Validation

### C1. Create Output Validation Module

**New file:** `utils/output_validator.py`

This module validates LLM-generated text against the input data to catch hallucinations before they reach the user.

```python
"""Post-generation validation for LLM outputs.

Catches hallucinations by cross-referencing generated text against input data.
Returns (validated_text, warnings) — warnings are logged but text is still returned.
If a critical hallucination is detected, the text is replaced with a fallback.
"""

import re
import logging
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)


def validate_bureau_review(
    generated_text: str,
    data_summary: str,
    product_types: set,
) -> Tuple[str, List[str]]:
    """Validate bureau review against input data.

    Checks:
    1. Any CC utilization mentioned matches the input data (or CC exists in portfolio)
    2. Any INR amount mentioned exists in the input data
    3. Tradeline counts match input data
    4. No product types mentioned that don't exist in portfolio

    Returns:
        (text, warnings) — text may be modified if critical issues found
    """
    warnings = []
    text = generated_text

    # Check 1: CC utilization mentioned but no CC in portfolio
    cc_util_pattern = r'(?:CC|credit card|Credit Card)\s*(?:utilization|utilisation|util)\w*\s*(?:of|at|is|:)?\s*(\d+\.?\d*)%'
    cc_matches = re.findall(cc_util_pattern, text, re.IGNORECASE)

    has_cc_in_portfolio = any("CC" in str(pt) or "Credit Card" in str(pt) for pt in product_types)
    has_cc_in_data = "CC Utilization" in data_summary or "Credit Card Utilization" in data_summary

    if cc_matches and not has_cc_in_data:
        warnings.append(f"HALLUCINATION: CC utilization {cc_matches[0]}% mentioned but not in input data")
        # Remove the hallucinated CC utilization sentence
        text = re.sub(
            r'[^.]*(?:CC|credit card|Credit Card)\s*(?:utilization|utilisation)\s*[^.]*\.\s*',
            '',
            text,
            flags=re.IGNORECASE
        )

    # Check 2: Verify INR amounts in output exist in input
    output_amounts = set(re.findall(r'(?:₹|INR\s*)(\d[\d,]*(?:\.\d+)?)\s*(?:Cr|L|Lakh|crore)?', text))
    input_amounts = set(re.findall(r'(?:₹|INR\s*)(\d[\d,]*(?:\.\d+)?)\s*(?:Cr|L|Lakh|crore)?', data_summary))

    fabricated_amounts = output_amounts - input_amounts
    if fabricated_amounts:
        # Only warn for large amounts (small amounts may be formatting variations)
        large_fabricated = [a for a in fabricated_amounts if float(a.replace(',', '')) > 1000]
        if large_fabricated:
            warnings.append(f"POSSIBLE HALLUCINATION: Amounts {large_fabricated} in output but not in input")

    # Check 3: Tradeline count consistency
    total_tl_input = re.search(r'Total Tradelines:\s*(\d+)', data_summary)
    if total_tl_input:
        expected_total = total_tl_input.group(1)
        total_tl_output = re.findall(r'(\d+)\s*(?:total\s*)?tradeline', text, re.IGNORECASE)
        for found in total_tl_output:
            if found != expected_total:
                warnings.append(f"MISMATCH: Output says {found} tradelines but input says {expected_total}")

    for w in warnings:
        logger.warning("output_validator: %s", w)

    return text, warnings


def validate_banking_review(
    generated_text: str,
    data_summary: str,
) -> Tuple[str, List[str]]:
    """Validate banking review against input data summary.

    Checks:
    1. Salary amount matches input
    2. No events mentioned that aren't in the DETECTED EVENTS block
    3. No prompt example phrases echoed
    """
    warnings = []
    text = generated_text

    # Check 1: Prompt example echo detection
    KNOWN_EXAMPLES = [
        "primary score 35/100",
        "conduit account",
        "primary score",
        "secondary account",
        "distribution hub",
    ]
    for example in KNOWN_EXAMPLES:
        if example.lower() in text.lower():
            warnings.append(f"PROMPT ECHO: '{example}' found in output — likely echoed from prompt instructions")
            # Remove the sentence containing the echoed phrase
            text = re.sub(
                rf'[^.]*{re.escape(example)}[^.]*\.\s*',
                '',
                text,
                flags=re.IGNORECASE
            )

    # Check 2: If no DETECTED EVENTS in data but events mentioned in output
    has_events_in_data = "DETECTED TRANSACTION EVENTS" in data_summary
    event_phrases = ["PF withdrawal", "self-transfer", "post-salary routing",
                     "loan redistribution", "round-trip", "FD closure",
                     "salary advance", "BNPL"]

    if not has_events_in_data:
        for phrase in event_phrases:
            if phrase.lower() in text.lower():
                warnings.append(f"HALLUCINATION: '{phrase}' mentioned but no events in input data")

    for w in warnings:
        logger.warning("output_validator: %s", w)

    return text, warnings
```

### C2. Integrate Validator into Summary Chain

**File:** `pipeline/reports/report_summary_chain.py`

In `generate_customer_review()`, after `strip_think()`:

```python
from utils.output_validator import validate_banking_review

# After line 91:
review = strip_think(raw, label="CustomerReview")
if review:
    review, warnings = validate_banking_review(review, data_summary)
    if warnings:
        logger.warning("Banking review validation warnings for %s: %s",
                       report.meta.customer_id, warnings)
return review.strip() if review else None
```

In `generate_bureau_review()`, after `strip_think()`:

```python
from utils.output_validator import validate_bureau_review

# After line 808:
review = strip_think(raw, label="BureauReview")
if review:
    product_types = set(product_breakdown.keys()) if product_breakdown else set()
    review, warnings = validate_bureau_review(review, data_summary, product_types)
    if warnings:
        logger.warning("Bureau review validation warnings: %s", warnings)
return review.strip() if review else None
```

### C3. Implement Deterministic Fallback Summaries

For cases where the LLM produces critically hallucinated output (detected by validator), provide a deterministic template-based fallback:

**File:** `pipeline/reports/report_summary_chain.py` (new function)

```python
def _build_deterministic_banking_summary(report: CustomerReport, rg_salary_data: dict = None) -> str:
    """Generate a deterministic banking summary without LLM.

    Used as fallback when LLM output fails validation.
    Template-based, zero hallucination risk.
    """
    parts = []

    # Salary
    _rg_sal = (rg_salary_data or {}).get("rg_sal") if rg_salary_data else None
    sal_amt = (_rg_sal.get("salary_amount") if _rg_sal else None) or \
              (report.salary.avg_amount if report.salary else None)
    if sal_amt:
        parts.append(f"The customer receives an average monthly salary of ₹{sal_amt:,.0f}")

    # Cashflow
    if report.monthly_cashflow:
        total_in = sum(m.get('inflow', 0) for m in report.monthly_cashflow)
        total_out = sum(m.get('outflow', 0) for m in report.monthly_cashflow)
        n_months = len(report.monthly_cashflow)
        avg_net = (total_in - total_out) / max(1, n_months)
        parts.append(f"with an average monthly net cashflow of ₹{avg_net:,.0f} "
                    f"over {n_months} months (total inflow ₹{total_in:,.0f}, "
                    f"outflow ₹{total_out:,.0f})")

    # Categories
    if report.category_overview:
        top = sorted(report.category_overview.items(), key=lambda x: x[1], reverse=True)[:3]
        cats = ", ".join(f"{k} (₹{v:,.0f})" for k, v in top)
        parts.append(f"Top spending categories are {cats}")

    # EMI + Rent
    emi_str = ""
    if report.emis:
        total_emi = sum(e.amount for e in report.emis)
        emi_str = f"₹{total_emi:,.0f} in EMI"
    rent_str = ""
    if report.rent:
        rent_str = f"₹{report.rent.amount:,.0f} in rent"

    obligations = [x for x in [emi_str, rent_str] if x]
    if obligations:
        parts.append(f"Monthly obligations include {' and '.join(obligations)}")

    paragraph1 = ". ".join(parts) + "."

    # Events paragraph
    paragraph2 = ""
    if report.events:
        event_sentences = []
        for e in report.events:
            event_sentences.append(e["description"])
        paragraph2 = "\n\n" + " ".join(event_sentences)

    return paragraph1 + paragraph2
```

---

## 6. Section D — Event Detector False Positive Elimination

### D1. Add Word Boundary Enforcement to Keyword Matching

**File:** `tools/event_detector.py`

**Current (line 220-221):**
```python
pattern = "|".join(re.escape(kw) for kw in keywords)
matched = subset[narrations.str.contains(pattern, na=False, regex=True)].copy()
```

**Fix:** Add word boundary markers for short keywords that are prone to substring matching:

```python
def _build_keyword_pattern(keywords: list) -> str:
    """Build regex pattern with word boundaries for short keywords."""
    parts = []
    for kw in keywords:
        escaped = re.escape(kw)
        # Short keywords (≤4 chars) need word boundaries to avoid substring matches
        # e.g., "SIP" should not match "GOSIPURA", "LIC" should not match "LICENCE"
        if len(kw.strip()) <= 4:
            parts.append(rf'\b{escaped}\b')
        else:
            parts.append(escaped)
    return "|".join(parts)

# Replace line 220-221 with:
pattern = _build_keyword_pattern(keywords)
matched = subset[narrations.str.contains(pattern, na=False, regex=True)].copy()
```

### D2. Add Negative Keyword Exclusion Lists

**File:** `tools/event_detector.py`

Add a `negative_keywords` field to KEYWORD_RULES to exclude known false positive patterns:

```python
KEYWORD_RULES = [
    {
        "type": "pf_withdrawal",
        "direction": "C",
        "keywords": ["EPFO", "PF SETTL", "PF FINAL", "PF WITHDRAWAL", "PROVIDENT FUND", "PPF CLOSURE", "PF CREDIT"],
        "negative_keywords": ["PF INTEREST", "PFC ", "PLATFORM"],  # False positives
        "significance": "high",
        "label": "PF/Provident Fund withdrawal",
    },
    {
        "type": "fd_closure",
        "direction": "C",
        "keywords": ["FD CLOSURE", "FIXED DEPOSIT CLO", "FD MATURITY", "PREMATURE CLOSURE", "FD PREMATURE"],
        "negative_keywords": ["FD CLOSURE INTEREST", "FD INT ", "FD INTEREST"],  # Interest payments, not closures
        "significance": "medium",
        "label": "FD premature/maturity closure",
    },
    {
        "type": "salary_advance_bnpl",
        "direction": "C",
        "keywords": ["EARLY SALARY", "LAZYPAY", "SIMPL", "SLICE ", "KREDITBEE", "MONEYVIEW", "FIBE ", "NIRO", "STASHFIN", "MPOKKET", "FREO", "SALARY ADVANCE"],
        "negative_keywords": ["SIMPLE", "SIMPLY"],  # "SIMPL" matches "SIMPLE"
        "significance": "high",
        "label": "Salary advance / BNPL credit",
    },
    {
        "type": "sip_investment",
        "direction": "D",
        "keywords": ["BSE STAR MF", "NSE MFUND", "CAMS ", "KARVY ", "MUTUAL FUND", "SIP INSTAL", "SIP/"],
        "negative_keywords": ["SIPPY", "GOSIP", "MSIP"],  # Substring false positives
        "significance": "positive",
        "min_months": 2,
        "label": "SIP / Mutual Fund investment",
    },
    {
        "type": "insurance_premium",
        "direction": "D",
        "keywords": ["LIC PREM", "HDFC LIFE", "ICICI PRU", "MAX LIFE", "SBI LIFE", "TERM INSURANCE", "INSURANCE PREM", "LIFE INS", "BAJAJ ALLIANZ", "KOTAK LIFE", "LIC/"],
        "negative_keywords": ["LICENCE", "LICENSE", "PUBLIC"],  # "LIC " matches "LICENCE FEE"
        "significance": "positive",
        "min_months": 2,
        "label": "Life / term insurance premium",
    },
    {
        "type": "govt_benefit",
        "direction": "C",
        "keywords": ["PM KISAN", "MNREGA", "DBT ", "GOVT BENEFIT", "SCHOLARSHIP", "PENSION CREDIT", "JANDHAN"],
        "negative_keywords": [],
        "significance": "medium",
        "label": "Government benefit / pension credit",
    },
]
```

Then in `_apply_keyword_rules()`, add the exclusion check after matching:

```python
# After line 221 (matched = subset[...]):
negative_kws = rule.get("negative_keywords", [])
if negative_kws and not matched.empty:
    neg_pattern = "|".join(re.escape(nk) for nk in negative_kws)
    neg_mask = matched["tran_partclr"].fillna("").str.upper().str.contains(neg_pattern, na=False, regex=True)
    matched = matched[~neg_mask]
```

### D3. Tighten Self-Transfer Detection

**File:** `tools/event_detector.py`

**Current `_is_self()` (line 183-187):**
```python
def _is_self(narration: str, name_prefix: Optional[str]) -> bool:
    upper = narration.upper()
    if any(kw in upper for kw in _SELF_KEYWORDS):
        return True
    return bool(name_prefix and len(name_prefix) >= 3 and name_prefix in upper)
```

**Fix:** Add negative patterns and require "SELF" to be in transfer context:

```python
_SELF_NEGATIVE_PATTERNS = [
    "SELF PAY", "SELF ASSESSMENT", "SELF EMPLOYED",
    "SELF SERVICE", "SELF HELP", "SELF CARE",
]

def _is_self(narration: str, name_prefix: Optional[str]) -> bool:
    upper = narration.upper()

    # Negative check first — these contain "SELF" but aren't self-transfers
    if any(neg in upper for neg in _SELF_NEGATIVE_PATTERNS):
        return False

    # Check self_transfer keywords in transfer context
    if any(kw in upper for kw in _SELF_KEYWORDS):
        return True

    # Name prefix match (requires at least 4 chars for safety)
    return bool(name_prefix and len(name_prefix) >= 4 and name_prefix in upper)
```

Also raise the self-transfer threshold from 40% to 50% to reduce false positives:

```python
# In _detect_self_transfer_post_salary, line 449:
# Change from 0.40 to 0.50
(debits["tran_amt_in_ac"] >= sal_amt * 0.50)
```

### D4. Tighten Round-Trip Name Matching

**File:** `tools/event_detector.py`

**Current (line 510):**
```python
if d_name.lower()[:6] != c_name.lower()[:6]:
```

**Fix:** Use more characters and require matching on a longer prefix to reduce false positives from common Indian name prefixes:

```python
# Require at least 8 character match, and both names must be at least 8 chars
if len(d_name) < 8 or len(c_name) < 8:
    continue
if d_name.lower()[:10] != c_name.lower()[:10]:
    continue
```

### D5. Tighten Loan Redistribution Thresholds

**File:** `tools/event_detector.py`

**Current thresholds:**
- Credit ≥ ₹1.5L (too low — normal car insurance claim refund)
- Debit ≥ ₹5K (too low — normal daily transactions)
- Total outflow ≥ 30% (too low — normal spending patterns)

**Fix:**
```python
# Line 361:
threshold = max(300000, salary_amount * 3.0) if salary_amount > 0 else 300000  # Was 150K/2x

# Line 380:
(debits["tran_amt_in_ac"] >= 15000)  # Was 5000

# Line 388:
if pct_out < 50:  # Was 30%
    continue
```

### D6. Add Minimum Transaction Count Guard to Keyword Events

Some customers have only 1-2 transactions matching a keyword, which shouldn't be reported as a significant event. Add a minimum count for per-occurrence events:

```python
# In _apply_keyword_rules(), after building the per-occurrence events list,
# add a minimum significance check:

# For HIGH significance per-occurrence events: keep all (even 1 transaction matters)
# For MEDIUM per-occurrence events: require at least 1 transaction (already true)
# For POSITIVE per-occurrence events: shouldn't happen (positive events all have min_months)
```

This is already handled — positive events require `min_months >= 2`. No change needed here.

### D7. Add Event Confidence Scoring

Add a confidence field to each event to allow the report renderer to filter low-confidence events:

```python
# In each event dict, add:
"confidence": "high"  # or "medium" or "low"

# Confidence rules:
# - Keyword match with negative exclusion passed + word boundary = "high"
# - Multi-step detector with all thresholds met = "high"
# - Keyword match without word boundary on short keyword = "medium"
# - Name-based detection (round-trip, routing) = "medium" (names can be wrong)
```

Then in `format_events_for_prompt()`, optionally filter out low-confidence events:

```python
def format_events_for_prompt(events: list, min_confidence: str = "medium") -> str:
    """Format event list, filtering out low-confidence events."""
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    min_level = confidence_order.get(min_confidence, 1)

    filtered = [e for e in events if confidence_order.get(e.get("confidence", "medium"), 1) <= min_level]

    if not filtered:
        return ""
    # ... rest of function
```

---

## 7. Section E — Redundancy Removal

### E1. Redundant LLM-on-LLM in Combined Report

**Issue:** `generate_combined_executive_summary()` takes `banking_summary` (LLM output) and `bureau_summary` (LLM output) and feeds them to another LLM. This compounds hallucinations.

**Fix (Two Options):**

**Option A (Conservative):** Keep the LLM call but add the structured data as primary source, demoting the narratives to secondary context:

```python
def generate_combined_executive_summary(
    banking_summary: str,
    bureau_summary: str,
    customer_id: str,
    # NEW: structured data as primary source
    banking_data_summary: str = "",  # The same data_summary used for banking review
    bureau_data_summary: str = "",   # The same data_summary used for bureau review
    exposure_summary: str = "",
    foir_context: str = "",
    model_name: str = _SUMMARY_MODEL,
) -> Optional[str]:
```

The prompt would then include:
```
PRIMARY DATA (use these numbers):
{banking_data_summary}
{bureau_data_summary}

REFERENCE NARRATIVES (for tone only — verify all numbers against PRIMARY DATA):
Banking: {banking_summary}
Bureau: {bureau_summary}
```

**Option B (Aggressive):** Generate the combined summary directly from structured data, bypassing the individual summaries entirely. Build a `_build_combined_data_summary()` that merges banking and bureau structured data into one block.

**Recommendation:** Option A — it preserves the current architecture while reducing hallucination propagation.

### E2. Redundant Utilization Computation

**Issue:** CC utilization is computed in two places:
1. `bureau_feature_extractor.py` computes `utilization_ratio` per loan type
2. `tradeline_feature_extractor.py` loads `cc_balance_utilization_pct` from CSV

These can disagree. The data summary includes BOTH — the product breakdown utilization AND the behavioral features utilization — potentially confusing the LLM.

**Fix:** Use only ONE authoritative utilization value. Prefer the product_breakdown computation (it's from live data) and suppress the tradeline_features CC utilization if product_breakdown already provides it:

```python
# In _format_tradeline_features_for_prompt(), utilization section:
# Skip cc_balance_utilization_pct if product_breakdown already has CC utilization
# (This requires a flag or checking if CC util was already added in _build_bureau_data_summary)
```

### E3. Duplicate Data in Combined Report Inputs

The combined executive summary receives `banking_summary` which already contains salary, cashflow, EMI data. It also receives `additional_context` which may contain FOIR and exposure data. But the banking_summary ALSO mentions FOIR if it was in the banking review.

**Fix:** Structure the combined prompt to clearly separate "banking facts" from "bureau facts" from "cross-report metrics" to prevent double-counting:

```
SECTION 1 — BANKING FACTS (from transaction data):
[structured banking data — not the narrative]

SECTION 2 — BUREAU FACTS (from tradeline data):
[structured bureau data — not the narrative]

SECTION 3 — CROSS-REPORT METRICS:
[FOIR, exposure, combined signals]
```

---

## 8. Section F — Tone & Style Consistency

### F1. Enforce Formal Analyst Tone

**Issue:** Different models (llama3.2 vs deepseek-r1:14b) produce different tones. llama3.2 tends to be more conversational; deepseek-r1 is more formal. When both are used in the same report (banking review vs persona), the tone shifts are jarring.

**Fix:** Add explicit tone instructions to ALL prompts:

```
TONE: Write in formal third-person credit analyst language. Use "The customer" not "they/he/she".
Do not use conversational language, hedging phrases ("it seems", "appears to"), or disclaimers.
State facts directly: "The customer maintains..." not "It appears the customer maintains..."
```

### F2. Remove Subjective Language Patterns

**Issue:** LLM outputs sometimes include subjective qualifiers like "impressive", "concerning", "notable". These don't belong in a factual credit report.

**Fix:** Add to all review prompts:

```
Do NOT use subjective qualifiers: "impressive", "notable", "concerning", "significant", "healthy",
"strong", "weak", "good", "bad". Instead, state the fact and the tagged annotation.
Write: "CC utilization at 90% [HIGH RISK]" not "CC utilization is alarmingly high at 90%"
```

### F3. Standardize Number Formatting Instructions

**Issue:** LLM outputs inconsistently format numbers — sometimes "₹1.5L", sometimes "₹1,50,000", sometimes "1.5 lakhs".

**Fix:** Add to all prompts:

```
NUMBER FORMAT: Use the exact format from the data. Do not convert between formats.
If the data says "INR 1.5L", write "INR 1.5L". If it says "₹1,50,000", write "₹1,50,000".
```

---

## 9. Implementation Order

### Phase 1 — Critical Hallucination Fixes (Days 1-2)
1. **A1** — Remove in-prompt examples from CUSTOMER_REVIEW_PROMPT
2. **A2** — Harden BUREAU_REVIEW_PROMPT against missing products
3. **B1** — Add absent product markers to bureau data summary
4. **B2** — Fix zero vs None utilization confusion
5. **D1** — Word boundary enforcement in keyword matching
6. **D2** — Negative keyword exclusion lists

### Phase 2 — Event Detector Hardening (Days 2-3)
7. **D3** — Tighten self-transfer detection
8. **D4** — Tighten round-trip name matching
9. **D5** — Raise loan redistribution thresholds
10. **D7** — Event confidence scoring

### Phase 3 — Post-Generation Validation (Days 3-4)
11. **C1** — Create output validation module
12. **C2** — Integrate validator into summary chain
13. **C3** — Deterministic fallback summaries

### Phase 4 — Prompt Refinement & Tone (Days 4-5)
14. **A3** — Constrain persona prompt
15. **A4** — Guardrail explainer prompt
16. **A5** — Fix combined executive prompt
17. **F1-F3** — Tone and formatting standardization

### Phase 5 — Redundancy Cleanup (Day 5)
18. **E1** — Fix LLM-on-LLM in combined report
19. **E2** — Deduplicate utilization sources
20. **E3** — Structure combined report inputs

---

## Testing Strategy

For each fix, validate against these test cases:

1. **Customer with NO credit cards** — bureau summary should NOT mention CC utilization
2. **Customer with NO events** — banking summary should NOT mention any events
3. **Customer with salary but no EMI** — should NOT hallucinate EMI commitments
4. **Customer whose narrations contain "SIMPLE" (not "SIMPL")** — should NOT flag BNPL
5. **Customer with "LICENCE FEE" transaction** — should NOT flag insurance premium
6. **Customer with common name prefix** — round-trip detection should NOT false-match different people
7. **Customer with normal post-loan spending** — should NOT flag loan redistribution
8. **Customer with "SELF PAY" rent** — should NOT flag self-transfer

Create a test harness that generates reports for 10 diverse customers and runs the output validator against each, logging all warnings. Target: zero critical hallucination warnings.

---

*Plan generated from full codebase analysis — 2026-03*
