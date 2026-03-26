# Sample LLM Prompts — What the Model Actually Sees

> These are realistic reconstructions of the fully rendered prompts sent to Ollama.
> Variable names replaced with plausible data for customer `698167220`.

---

## 1. Banking Customer Review — Full Rendered Prompt

**Model:** `llama3.2` | **Temperature:** 0 | **Seed:** 42

```
You are a senior credit analyst writing a banking transaction review for a loan underwriting committee.

IMPORTANT RULES:
- Only reference numbers and data provided below — do NOT invent figures
- Do NOT mention numeric scores or classifications (e.g. do NOT write "primary score 35/100" or "conduit account" — instead describe what actually happened)
- Do NOT invent or assume values for items listed under "DATA NOT AVAILABLE" — omit them entirely


1. FINANCIAL OVERVIEW (4-6 lines): A factual summary of the customer's banking profile. Cover salary amount, frequency, source, monthly cashflow which is difference between credit and debit (average net, total inflow vs outflow, do not mix with income naming), key spending categories, EMI and rent commitments, and any utility bills. If "Banking FOIR" is present, include the obligation-to-income ratio as a factual observation. Weave these as natural facts in a narrative flow — not as a list. NO risk commentary, NO event mentions, NO merchant details — just the financial picture.

2. MERCHANT BEHAVIOR (2-4 lines): If a "MERCHANT PROFILE" line is present below, write a short paragraph covering: favourite merchants and their interaction frequency, any significant counterparties (share of total flow), two-way merchants (credits AND debits with same entity), spending concentration, and any anomaly merchants. Quote exact figures — names, amounts, percentages, and days apart. If no merchant profile is present, omit this paragraph entirely.

3. TRANSACTION EVENTS (one sentence per event): If a "DETECTED TRANSACTION EVENTS" block is present below, narrate EVERY event listed — [HIGH], [MEDIUM], and [POSITIVE] — as plain facts with the specific month and exact amount. Do NOT omit any event. Do NOT say "an event was detected" — state what the customer actually did (e.g. "In Jun 2025, the customer received ₹72,000 salary and transferred ₹72,000 to their own account the next day"). If no events block is present, omit this paragraph entirely.

Financial Data:
Top spending categories: Transfers: 1,45,000, Loan EMI: 72,500, Food & Dining: 23,400
Monthly cashflow: Avg net -12,340 INR (Total in: 4,85,000, out: 5,22,000)
Salary income: 85,000 INR average from KOTAK MAHINDRA (3 months)
EMI commitments: 36,250 INR average per payment (6 debit transactions)
Rent payments: 15,000 INR (3 transactions)
Banking FOIR (EMI+Rent/Salary): 60.3% [STRETCHED]
Utility bills: 8,500 INR total
Most frequent merchant: SWIGGY (12 transactions, 18,600 INR)
MERCHANT PROFILE: Regular merchants: 5 (SWIGGY, AMAZON, HDFC BANK). Anomaly: PREMIUM MOTORS INR 3,45,000. Concentration: top-1 = 28%, 14 merchants total. Favourite debit merchants: SWIGGY (12 txns, INR 18,600, avg 8 days apart); AMAZON (7 txns, INR 42,300, avg 12 days apart). Favourite credit merchants: KOTAK MAHINDRA (3 txns, INR 2,55,000, avg 30 days apart). Significant counterparties: KOTAK MAHINDRA accounts for 53% of credits. Two-way merchants: HDFC BANK (credit INR 50,000, debit INR 36,250, net inflow INR 13,750, received first then paid, credits Jan-25 to Mar-25, debits Jan-25 to Mar-25). Emerging merchants (new in recent 3 months, absent before): 2 — ZOMATO, UBER
Account shows moderate ATM dependency with 15% of debits routed through cash withdrawals
Primary account with regular salary credits and EMI outflows — stable usage pattern
DETECTED TRANSACTION EVENTS [include in summary with specific dates/amounts]:
  [HIGH    ] Jan 2025: Self-transfer of INR 72,000 within 2 days of salary credit of INR 85,000 to account ending XX4521
  [HIGH    ] Feb 2025: Loan disbursement credit of INR 3,50,000 followed by INR 3,45,000 debit to PREMIUM MOTORS within 3 days
  [MEDIUM  ] Mar 2025: ECS/NACH bounce — HDFC BANK EMI return of INR 36,250
  [POSITIVE] Jan-Mar 2025: Regular SIP investment of INR 5,000/month to HDFC MUTUAL FUND (3 months)
  [POSITIVE] Jan-Mar 2025: Insurance premium of INR 12,000 to LIC OF INDIA (quarterly)

Write the banking review (up to three paragraphs):
```

### What the `{data_summary}` is built from:

```
_build_data_summary(report, rg_salary_data) produces a list of strings:

1. "Top spending categories: ..."        ← report.category_overview (pandas groupby)
2. "Monthly cashflow: ..."               ← report.monthly_cashflow (month-wise sums)
3. "Salary income: ..."                  ← rg_salary_data.rg_sal OR report.salary
4. "EMI commitments: ..."               ← report.emis (EMIBlock list)
5. "Rent payments: ..."                 ← report.rent (RentBlock)
6. "Banking FOIR (...): XX.X% [TAG]"    ← computed inline: (EMI+Rent)/Salary × 100
7. "Utility bills: ..."                 ← report.bills (BillBlock list)
8. "Most frequent merchant: ..."        ← report.top_merchants[0]
9. "MERCHANT PROFILE: ..."              ← report.merchant_features (multi-part block)
10. <account quality observations>       ← report.account_quality["observations"]
11. "DETECTED TRANSACTION EVENTS ..."   ← format_events_for_prompt(report.events)
12. "DATA NOT AVAILABLE (...): ..."     ← lists absent sections to prevent hallucination

These are joined with "\n" and injected into {data_summary}.
```

---

## 2. Bureau Executive Review — Full Rendered Prompt

**Model:** `llama3.2` (or `deepseek-r1:8b` if thinking model) | **Temperature:** 0 | **Seed:** 42

```
You are a senior credit analyst writing an executive summary for a loan underwriting committee.

IMPORTANT RULES:
- Only reference numbers and risk annotations provided below — do NOT invent figures
- No arithmetic — just narrate the pre-computed values and their tagged interpretations
- NEVER summarise, round, or omit any INR amount or percentage that appears in the data — quote every figure exactly as provided
- Features tagged [HIGH RISK], [MODERATE RISK], or [CONCERN] are red flags — highlight them in the Behavioral Insights paragraph only
- Features tagged [POSITIVE], [CLEAN], or [HEALTHY] are green signals — acknowledge them in the Behavioral Insights paragraph only

STRUCTURE YOUR RESPONSE IN TWO PARAGRAPHS:

1. PORTFOLIO OVERVIEW (6-10 lines): A factual summary of the customer's tradeline portfolio so the reader does not have to look at the raw data. Start with the exact tradeline counts using the data fields as follows: "Total Tradelines" is the total count, "Live Tradelines" is the number of currently active accounts, and "Closed Tradelines" is the number of settled/closed accounts — state it as "N total (M live, P closed)" using those exact values. Do NOT use the Total figure as the live count. Then cover which loan products are present, total sanctioned exposure, total outstanding, and unsecured exposure. Weave in the key highlights that stand out from the behavioral features: credit card utilization percentage, any DPD values above zero, obligation, unsecured obligation, FOIR, missed payment percentages, enquiry counts, loan acquisition velocity, and any loan product counts that are unusually high. If Kotak (On-Us) Exposure data is present, state the exact on-us tradeline count, products, sanctioned and outstanding amounts. If joint loan data is present, state the count and product types. If Defaulted/Delinquent Loan Types data is present, mention each defaulted loan type with its sanctioned amount, outstanding, and max DPD — and flag if it is on-us. Present these as natural facts within the narrative flow — not as a separate list. NO risk commentary, NO opinions, NO concern flags — just state the portfolio composition and the notable data points together in one cohesive summary.

2. BEHAVIORAL INSIGHTS (4-6 lines): Now provide the risk interpretation. Use the tagged annotations ([HIGH RISK], [POSITIVE], etc.) and the COMPOSITE RISK SIGNALS to narrate the customer's credit behavior — enquiry pressure, repayment discipline, utilization, loan acquisition velocity. Give commentery over leverage or exposure trend available. CRITICAL: Every inference MUST cite the actual number that backs it (e.g., "utilization is elevated at 65%", "3 new PL trades in 6 months signals loan stacking", "0% missed payments but DPD of 12 days detected", "Exposure is elevated"). Never state a risk opinion without the supporting data point.

Bureau Portfolio Summary:
Total Tradelines: 18
Live Tradelines: 12
Closed Tradelines: 6
Total Sanction Amount: INR 45,32,000
Total Outstanding: INR 28,15,000
Unsecured Sanction Amount: INR 22,50,000
Unsecured Outstanding: 62% of total outstanding
Max DPD (Days Past Due): 60 (8 months ago, Personal Loan)
Credit Card Utilization: 82.3%

Obligation & FOIR:
  Affluence Income (6M est.): INR 1,02,000
  Total Bureau EMI Obligation (all products): INR 48,500
  Unsecured EMI Obligation: INR 32,000
  FOIR (total): 47.5% [STRETCHED]
  FOIR (unsecured only): 31.4% [COMFORTABLE]

Product-wise Breakdown:
  - Personal Loan: 6 accounts (Live: 4, Closed: 2), Sanctioned: INR 18,00,000, Outstanding: INR 12,40,000
  - Credit Card: 3 accounts (Live: 3, Closed: 0), Sanctioned: INR 4,50,000, Outstanding: INR 3,70,000
  - Home Loan: 1 accounts (Live: 1, Closed: 0), Sanctioned: INR 15,00,000, Outstanding: INR 8,50,000
  - Auto Loan: 2 accounts (Live: 1, Closed: 1), Sanctioned: INR 5,20,000, Outstanding: INR 2,15,000
  - Business Loan: 3 accounts (Live: 1, Closed: 2), Sanctioned: INR 1,80,000, Outstanding: INR 85,000
  - Gold Loan: 2 accounts (Live: 1, Closed: 1), Sanctioned: INR 72,000, Outstanding: INR 45,000
  - Two Wheeler Loan: 1 accounts (Live: 1, Closed: 0), Sanctioned: INR 1,10,000, Outstanding: INR 10,000

Kotak (On-Us) Exposure:
  Tradelines: 3 (2 live)
  Products: Personal Loan, Credit Card
  Sanctioned: INR 8,50,000
  Outstanding: INR 5,20,000
  Max DPD: 30 [CONCERN — delinquency on Kotak product]

Joint Loans: 1 tradeline(s) — Home Loan

Defaulted/Delinquent Loan Types:
  - Personal Loan: Sanctioned INR 4,00,000, Outstanding INR 3,20,000, Max DPD 60
  - Credit Card: Sanctioned INR 1,50,000, Outstanding INR 1,40,000, Max DPD 30 [ON-US / KOTAK]

Behavioral & Risk Features:
  LOAN ACTIVITY:
    New PL Trades in Last 6M: 2 [MODERATE RISK — multiple recent PLs]
    Months Since Last PL Trade: 1.50 [CONCERN — very recent PL activity]
    Months Since Last Unsecured Trade: 1.50 [CONCERN — very recent unsecured activity]
  DPD & DELINQUENCY:
    Max DPD Last 6M (CC): 0 [CLEAN]
    Max DPD Last 6M (PL): 30 [MODERATE RISK — significant DPD]
    Max DPD Last 9M (CC): 0 [CLEAN]
    Months Since Last 0+ DPD (PL): 8.00 [CONCERN — recent PL delinquency]
    Months Since Last 0+ DPD (Unsecured): 8.00 [CONCERN — recent unsecured delinquency]
  PAYMENT BEHAVIOR:
    % Missed Payments Last 18M: 0.00 [NOTE — 0% formally missed but DPD delays detected on some products; payments were late]
    % Trades with 0+ DPD in 24M (All): 5.56 [CONCERN]
    % Trades with 0+ DPD in 24M (PL): 8.33 [CONCERN]
    % Trades with 0+ DPD in 12M (All): 0.00 [CLEAN]
    Ratio Good Closed PL Loans: 100% [POSITIVE — strong closure track record]
  UTILIZATION:
    CC Balance Utilization: 82.30% [HIGH RISK — over-utilized]
    PL Outstanding: 68.90% [HIGH RISK — most PL balance still outstanding]
  ENQUIRY BEHAVIOR:
    Unsecured Enquiries Last 12M: 6 [MODERATE RISK — elevated enquiry pressure]
    Trade-to-Enquiry Ratio (Unsec 24M): 45.00% [CONCERN — low conversion, possible rejections]
  LOAN ACQUISITION VELOCITY:
    Avg Interpurchase Time PL/BL (12M): 2.80 months [CONCERN — frequent acquisitions]
    Avg Interpurchase Time All Loans (24M): 3.50 months [CONCERN — frequent acquisitions]
  COMPOSITE RISK SIGNALS:
    >> CREDIT HUNGRY + LOAN STACKING: High enquiry activity (6x in 12M) combined with 2 new PL trades in 6M
    >> PAYMENT TIMING NUANCE: 0% missed payments in 18M but DPD detected (PL 6M: 30 days) — payments were eventually made but past due date; do NOT describe payment record as clean or positive
    >> ELEVATED LEVERAGE: CC utilization at 82.3% and 68.9% PL balance still outstanding

Sanctioned Exposure Trend:
Sanctioned exposure 12M trend: increased by 22% (INR 37.15 L → INR 45.32 L)
Sanctioned exposure 6M avg trend: increased by 15% (prior 6M avg INR 39.50 L → recent 6M avg INR 45.32 L)

Exposure Commentary: Sanctioned exposure peaked at INR 45.32 L in Mar 2025, driven primarily by Personal Loan and Home Loan products. Current exposure remains at peak levels with Personal Loan, Credit Card, Home Loan, Auto Loan, Business Loan, Gold Loan, and Two Wheeler Loan products active.

# # Write the two-paragraph bureau portfolio review:
```

### What the `{data_summary}` is built from:

```
_build_bureau_data_summary(executive_inputs, tradeline_features, monthly_exposure)
produces a single "\n".join(lines) string with these blocks:

BLOCK 1 — Portfolio Summary (8 lines):
  ← executive_inputs: total/live/closed tradelines, sanctioned, outstanding,
     unsecured, max DPD with timing

BLOCK 2 — CC Utilization (per product):
  ← product_breakdown[LoanType].utilization_ratio (CC only typically)

BLOCK 3 — Obligation & FOIR:
  ← tradeline_features: affluence_amt, aff_emi, unsecured_emi, foir, foir_unsec
  ← Tags: [OVER-LEVERAGED] >65% | [STRETCHED] >40% | [COMFORTABLE] ≤40%

BLOCK 4 — Product-wise Breakdown:
  ← product_breakdown dict: per LoanType count/live/closed/sanctioned/outstanding

BLOCK 5 — Kotak (On-Us) Exposure:
  ← executive_inputs: on_us_total_tradelines, on_us_live, products, sanctioned,
     outstanding, max DPD

BLOCK 6 — Joint Loans:
  ← executive_inputs: total_joint_count, joint_product_types

BLOCK 7 — Defaulted Loans:
  ← executive_inputs: defaulted_loan_summaries (type, sanction, outstanding, dpd, on_us)

BLOCK 8 — Behavioral & Risk Features (~30 lines):
  ← _format_tradeline_features_for_prompt(tradeline_features)
  ← 6 sub-sections: Loan Activity, DPD & Delinquency, Payment Behavior,
     Utilization, Enquiry Behavior, Loan Acquisition Velocity
  ← Each value annotated with [HIGH RISK], [CONCERN], [POSITIVE], etc.
  ← Thresholds from config/thresholds.py

BLOCK 9 — Composite Risk Signals:
  ← _compute_interaction_signals(tf_dict)
  ← Multi-feature combinations: credit hungry, rapid stacking, clean profile,
     payment timing nuance, elevated leverage, low conversion

BLOCK 10 — Exposure Trend:
  ← monthly_exposure: 12M point-in-time + 6M avg comparison
  ← summarize_exposure_timeline(): deterministic 2-sentence commentary
```

---

## Key Observations for Prompt Improvement

### Banking Prompt
1. **`{data_summary}` is a flat list of lines** — no structure, no headers, no grouping. The LLM has to parse what belongs to "Financial Overview" vs "Merchant Behavior" vs "Events" by recognizing keywords.
2. **Account quality observations are injected as bare strings** — no label, no section header. They blend into the data and the LLM may treat them as financial facts.
3. **Events block uses `[HIGH    ]` with padding spaces** — minor formatting inconsistency.
4. **Merchant profile is a single massive line** — ~500 chars of period-separated facts. Hard for the LLM to parse distinct merchant features.

### Bureau Prompt
1. **Data summary is well-structured** — clear sections with headers (`\nObligation & FOIR:`, `\nProduct-wise Breakdown:`, etc.).
2. **Risk annotations are inline** — `[HIGH RISK — over-utilized]` directly after the value. This is good — the LLM sees the interpretation alongside the number.
3. **Composite signals are the strongest part** — they tell the LLM how to interpret multi-feature combinations, preventing the LLM from doing its own (potentially wrong) cross-feature analysis.
4. **No "DATA NOT AVAILABLE" block** — unlike banking, bureau prompt doesn't tell the LLM what's missing. If a customer has no CC, the CC lines are simply absent, but the LLM might hallucinate CC data from its training.
5. **Exposure data appears twice** — once as trend numbers, once as "Exposure Commentary" sentence. The LLM may narrate the same trend twice.
6. **CC utilization appears twice** — once in the top-level portfolio summary (Block 2) and again in Behavioral Features > UTILIZATION (Block 8). Different values possible if computed differently.
