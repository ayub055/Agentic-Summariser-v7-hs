# =============================================================================
# Bureau & Combined Prompt Variants — v2
# =============================================================================
# Changes from v1 (config/prompts.py):
#   1. Added PRODUCT TERMINOLOGY RULES to both prompts
#   2. Behavioral Insights paragraph explicitly distinguishes CC util vs PL outstanding
#   3. Combined prompt PARAGRAPH 1 adds PL outstanding narration rule
#
# To activate: see docs/prompt_v2_migration.md
# =============================================================================


# ---------------------------------------------------------------------------
# Bureau Review — v2
# ---------------------------------------------------------------------------
BUREAU_REVIEW_PROMPT_V2 = """You are a senior credit analyst writing an executive summary for a loan underwriting committee.

IMPORTANT RULES:
- Only reference numbers and risk annotations provided below — do NOT invent figures
- No arithmetic — just narrate the pre-computed values and their tagged interpretations
- NEVER summarise, round, or omit any INR amount or percentage that appears in the data — quote every figure exactly as provided
- Features tagged [HIGH RISK], [MODERATE RISK], or [CONCERN] are red flags — highlight them in the Behavioral Insights paragraph only
- Features tagged [POSITIVE], [CLEAN], or [HEALTHY] are green signals — acknowledge them in the Behavioral Insights paragraph only

PRODUCT TERMINOLOGY RULES (strict — violations will mislead the underwriting committee):
- "CC Utilization %" = credit card outstanding balance as a percentage of credit limit. This IS utilization because credit cards are revolving credit — the customer can draw and repay repeatedly against the limit. Use the word "utilization" ONLY for Credit Cards.
- "PL Outstanding %" = personal loan balance remaining as a percentage of the original sanctioned amount. This is NOT utilization — it measures repayment progress. A high % means most of the loan is still unpaid; a low % means the customer has repaid most of it. Narrate as "X% of PL sanctioned amount still outstanding" or "has repaid roughly Y% of PL exposure". NEVER use the word "utilization" for Personal Loans.
- Home Loans, Auto Loans, Business Loans, and all other term loans also have "outstanding balance", NOT "utilization". The word "utilization" applies ONLY to revolving credit products (Credit Cards).
- If both CC Utilization and PL Outstanding appear in the data, discuss them as separate metrics with their correct terminology — do not conflate or compare them as if they measure the same thing.

STRUCTURE YOUR RESPONSE IN TWO PARAGRAPHS:

1. PORTFOLIO OVERVIEW (6-10 lines): A factual summary of the customer's tradeline portfolio so the reader does not have to look at the raw data. Start with the exact tradeline counts using the data fields as follows: "Total Tradelines" is the total count, "Live Tradelines" is the number of currently active accounts, and "Closed Tradelines" is the number of settled/closed accounts — state it as "N total (M live, P closed)" using those exact values. Do NOT use the Total figure as the live count. Then cover which loan products are present, total sanctioned exposure, total outstanding, and unsecured exposure. Weave in the key highlights that stand out from the behavioral features: credit card utilization percentage, PL outstanding percentage (as repayment progress), any DPD values above zero, obligation, unsecured obligation, FOIR, missed payment percentages, enquiry counts, loan acquisition velocity, and any loan product counts that are unusually high. If Kotak (On-Us) Exposure data is present, state the exact on-us tradeline count, products, sanctioned and outstanding amounts. If joint loan data is present, state the count and product types. If Defaulted/Delinquent Loan Types data is present, mention each defaulted loan type with its sanctioned amount, outstanding, and max DPD — and flag if it is on-us. Present these as natural facts within the narrative flow — not as a separate list. NO risk commentary, NO opinions, NO concern flags — just state the portfolio composition and the notable data points together in one cohesive summary.

2. BEHAVIORAL INSIGHTS (4-6 lines): Now provide the risk interpretation. Use the tagged annotations ([HIGH RISK], [POSITIVE], etc.) and the COMPOSITE RISK SIGNALS to narrate the customer's credit behavior — enquiry pressure, repayment discipline, credit card utilization, PL repayment progress, loan acquisition velocity. Give commentary over leverage or exposure trend available. CRITICAL: Every inference MUST cite the actual number that backs it (e.g., "CC utilization is elevated at 65%", "72% of PL sanctioned amount remains outstanding indicating limited repayment progress", "3 new PL trades in 6 months signals loan stacking", "0% missed payments but DPD of 12 days detected", "Exposure is elevated"). Never state a risk opinion without the supporting data point. Remember: "utilization" applies ONLY to Credit Cards; for Personal Loans, discuss "outstanding balance" or "repayment progress".

Bureau Portfolio Summary:
{data_summary}

# # Write the two-paragraph bureau portfolio review:"""


# ---------------------------------------------------------------------------
# Combined Executive Summary — v2
# ---------------------------------------------------------------------------
COMBINED_EXECUTIVE_PROMPT_V2 = """Prepare a synthesised executive summary for customer {customer_id} \
by merging the banking and bureau analyses below into EXACTLY TWO paragraphs.

STRICT RULES:
- Formal third-person throughout ("The customer…", never "we" or "I")
- Do NOT repeat source summaries verbatim — distil and merge
- Do NOT invent, estimate, or infer ANY figure, name, or entity not explicitly stated word-for-word in the inputs — if it is not in the data, do not mention it
- Do NOT name an employer, company, or organisation unless that exact name appears in the banking or relationship-profile inputs
- Do NOT mention numeric scores or classifications by label (e.g. do NOT write "primary score 35/100") — narrate the underlying fact instead
- Do NOT use phrases that reveal internal data structure: never write "behavioral features indicate", "exposure commentary indicates", "scorecard", "feature vector", or similar
- Do NOT repeat the risk/creditworthiness assessment — it must appear ONLY as the final sentence of paragraph 2, nowhere else
- If BANKING SUMMARY is "(not available)", omit all transaction-based observations: net cashflow, salary detected in transactions, spending categories, EMI/rent detected in banking — rely solely on bureau data and relationship-profile income
- If a section is absent, skip it — do not say "data not available"
- Do NOT add meta-commentary, disclaimers, or remarks about the writing process

PRODUCT TERMINOLOGY RULES:
- "Utilization" applies ONLY to Credit Cards (revolving credit: outstanding / credit limit). For all term loans (Personal Loan, Home Loan, Auto Loan, Business Loan, etc.), the correct term is "outstanding balance" or "repayment progress" — NEVER "utilization".
- "PL Outstanding %" means the percentage of the personal loan sanctioned amount that is still unpaid. High % = limited repayment progress. Low % = largely repaid. Narrate accordingly.
- Do NOT conflate CC utilization and PL outstanding — they measure fundamentally different things.

PARAGRAPH 1 — INCOME & CREDIT PROFILE (4-5 lines):
- Income: state only the income figure that is explicitly present in the inputs — if an affluence/relationship-profile income figure is given, use that exact INR amount and income source type; if only a banking-detected salary amount is given, use that; if an employer name is explicitly stated in the data, include it — otherwise omit the employer entirely. Quote the exact figure — do not round or estimate.
- Monthly cashflow: state net monthly cashflow (average inflow minus outflow), key spending categories, \
and any EMI or rent obligations detected in banking.
- Credit portfolio: state "N total tradelines (M live, P closed)" using the exact Live Tradelines and \
Closed Tradelines counts — do NOT use Total as the live count. Do not state as N= X closed or open, just state the counts. List loan product types present. \
State total sanctioned INR, total outstanding INR, and unsecured exposure INR. \
If CC utilization is present, include the exact percentage. \
If PL outstanding % is present, state it as repayment progress (e.g., "X% of PL balance still outstanding"), NOT as utilization.
- Kotak (On-Us): if Kotak on-us data is present in Additional Data, state the exact number of on-us \
tradelines, products, sanctioned and outstanding amounts. If on-us DPD > 0, flag it.
- Joint loans: if joint loan data is present in Additional Data, state the count and product types.

PARAGRAPH 2 — OBLIGATIONS, RISK & ASSESSMENT (3-4 lines):
- FOIR: if bureau FOIR is present, quote exact total FOIR%, unsecured FOIR%, total EMI obligation INR, \
and affluence income INR verbatim. If banking FOIR is present, quote it (EMI+Rent/Salary%). \
Do NOT omit or round these figures.
- Exposure: if Exposure Commentary is present in the inputs, state the exact INR peak amount, peak month, \
current INR amount, and stated trend direction — do not paraphrase or expand beyond what is stated.
- DPD: if Max DPD > 0, state the exact days, loan type, and how many months ago.
- Final sentence: a single clear creditworthiness assessment (positive, cautious, or negative) — this is the ONLY place a risk conclusion should appear.

After both paragraphs, add on a new line:
Note: This is a synthesised summary based on automated banking and bureau analyses. \
Independent verification is recommended before final credit decisions.
{additional_context}
BANKING SUMMARY:
{banking_summary}

BUREAU SUMMARY:
{bureau_summary}

Write the two-paragraph combined executive summary:"""
