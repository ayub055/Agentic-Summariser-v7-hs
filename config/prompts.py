"""Centralised LLM prompt templates for the Transaction Intelligence System.

All prompt strings live here so they can be reviewed, versioned, and tuned
in one place without opening individual pipeline modules.

Naming convention:
  <MODULE>_PROMPT  — one primary prompt per consuming module
"""

# =============================================================================
# Intent Parser  (pipeline/intent_parser.py)
# =============================================================================

PARSER_PROMPT = """You are a JSON extractor for a transaction analysis system. Extract intent from the query below.

INTENTS (choose the most specific one):
- total_spending: Get total spending/expenses for a customer (e.g., "What is the total spending?", "How much did I spend in total?")
- total_income: Get total income/credits for a customer (e.g., "What is the total income?", "How much did I earn?")
- spending_by_category: Spending in a specific category (e.g., "How much did I spend on Groceries?", "What did I spend on Rent?")
- all_categories_spending: Get spending breakdown for all categories (e.g., "Show me spending by category", "Break down spending by category")
- top_categories: Top N spending categories
- spending_in_period: Spending within a date range
- financial_overview: General overview of finances
- compare_categories: Compare spending between multiple categories
- list_customers: List all customers
- list_categories: List all categories
- customer_report: Generate a full PDF report for a customer with all financial data, salary, EMI, rent, cashflow, categories
- lender_profile: Creditworthiness/lender assessment report
- credit_analysis: Detailed analysis of credits/income (max credit, avg, median, sources)
- debit_analysis: Detailed analysis of debits/spending patterns
- transaction_statistics: Transaction counts and statistics
- anomaly_detection: Find unusual/spike transactions
- balance_trend: Balance trends over time
- income_stability: Income consistency and stability analysis
- cash_flow: Monthly cash flow (inflows vs outflows)
- category_presence_lookup: Check if customer has transactions for a specific category/behavior (e.g., betting, salary, rent, entertainment)
- combined_report: Generate a combined report that merges both the customer banking report and the bureau tradeline report into one document
- bureau_report: Generate a bureau/credit bureau/CIBIL tradeline report for a customer
- bureau_credit_cards: Check if customer has credit cards, get count and utilization
- bureau_loan_count: How many loans of a specific type (personal loan, home loan, etc.) the customer has. Put the loan type in "category" field.
- bureau_delinquency: Check if any loan or specific loan type is delinquent or has DPD. Put the loan type in "category" field if specified.
- bureau_overview: General bureau/tradeline summary (total tradelines, exposure, outstanding) without generating a full report
- unknown: If query doesn't match any intent

IMPORTANT for customer_report:
If user asks to "generate report", "create report", "full report", "PDF report", "comprehensive report" for a customer, classify as "customer_report".

Examples for customer_report:
- "Generate report for customer 9449274898" -> intent=customer_report, customer_id=9449274898
- "Create a report for 1234567890" -> intent=customer_report, customer_id=1234567890
- "Full report for customer 123" -> intent=customer_report, customer_id=123
- "Generate PDF report for 9449274898" -> intent=customer_report, customer_id=9449274898

IMPORTANT for category_presence_lookup:
If the user asks whether the customer spends on, pays for, receives, or has transactions related to a specific category (e.g., betting, gambling, salary, rent, entertainment, gaming), classify as "category_presence_lookup" and extract the category name.
Do NOT decide if the category is present - just extract the intent and category.

Examples for category_presence_lookup:
- "Does he spend on betting?" -> intent=category_presence_lookup, category=betting_gaming
- "Does customer pay rent?" -> intent=category_presence_lookup, category=rent
- "Does he receive salary?" -> intent=category_presence_lookup, category=salary
- "Any entertainment expenses?" -> intent=category_presence_lookup, category=entertainment
- "Is there gambling activity?" -> intent=category_presence_lookup, category=betting_gaming

IMPORTANT for combined_report:
If user asks to "generate combined report", "merged report", "both reports", or "combine banking and bureau" for a customer, classify as "combined_report".

Examples for combined_report:
- "Generate combined report for 100384958" -> intent=combined_report, customer_id=100384958
- "Merged report for customer 100384958" -> intent=combined_report, customer_id=100384958
- "Generate both reports for 100384958" -> intent=combined_report, customer_id=100384958

IMPORTANT for bureau_report:
If user asks to generate a "bureau report", "CIBIL report", "tradeline report", or "credit bureau report" for a customer, classify as "bureau_report".

Examples for bureau_report:
- "Generate bureau report for 100384958" -> intent=bureau_report, customer_id=100384958
- "Bureau report for customer 100384958" -> intent=bureau_report, customer_id=100384958
- "CIBIL report for 100384958" -> intent=bureau_report, customer_id=100384958
- "Tradeline report for customer 100384958" -> intent=bureau_report, customer_id=100384958

IMPORTANT for bureau chat queries (these are quick lookups, NOT full report generation):
- "Are there any credit cards?" -> intent=bureau_credit_cards
- "Credit card utilization?" -> intent=bureau_credit_cards
- "Does he have credit cards?" -> intent=bureau_credit_cards
- "How many personal loans?" -> intent=bureau_loan_count, category=personal_loan
- "How many home loans does he have?" -> intent=bureau_loan_count, category=home_loan
- "Loan count for business loan" -> intent=bureau_loan_count, category=business_loan
- "What loans does he have?" -> intent=bureau_loan_count
- "Is any loan delinquent?" -> intent=bureau_delinquency
- "Any DPD on personal loan?" -> intent=bureau_delinquency, category=personal_loan
- "Is there any overdue?" -> intent=bureau_delinquency
- "Bureau summary" -> intent=bureau_overview
- "Tradeline overview" -> intent=bureau_overview
- "What does the bureau look like?" -> intent=bureau_overview
- "Bureau details" -> intent=bureau_overview

LOAN TYPES for bureau queries: personal_loan, credit_card, home_loan, auto_loan, business_loan, gold_loan, two_wheeler_loan, consumer_durable, lap_las_lad, other

CATEGORIES: MNC_Companies, Digital_Betting_Gaming, Food, Liquor_Smoke, Bank_Fees_Charges, Mobile_Bills, Wallets, E_Commerce, Courier_Logistics, Air_Travel, E_Entertainment, Mobility, Railway, Govt_Tax_Challan, Hospital, Grocery, Fashion_Beauty, Equipment_Construction, Pharmacy, Engineering, Kids_School, Education, Rent, Jewelry_Premium_Gifts, Foreign_Transaction, Payroll, Investment, Salary, Electronics_Appliance, Charity_Donations, Books_Stationery, Fuel, Govt_Companies, Hotel, Insurance, Personal_Home_Services, Pet_Care, Taxi_Cab, Real_Estate, Sports_Fitness, EMI, Finance, P2P

DATE FORMAT: Use YYYY-MM-DD format (e.g., 2025-07-01)

Query: {query}

Return ONLY this JSON (no markdown, no explanation):
{{"intent":"<intent>","customer_id":<int or null>,"category":"<str or null>","categories":<list or null>,"start_date":"<YYYY-MM-DD or null>","end_date":"<YYYY-MM-DD or null>","top_n":5,"threshold_std":2.0}}"""


# =============================================================================
# Transaction Insight Extractor  (pipeline/transaction_flow.py)
# =============================================================================

TRANSACTION_INSIGHT_PROMPT = """You are a financial transaction pattern extractor. Analyze the transactions and identify patterns.

RULES (STRICTLY FOLLOW):
- Use ONLY the provided transactions below
- Do NOT infer intent, risk, or legality
- Do NOT speculate or give advice
- Do NOT invent data not in the transactions
- Do NOT summarize overall customer behavior
- ONLY identify factual, descriptive patterns

ALLOWED PATTERNS (use only these):
- subscription-heavy: Regular recurring payments to subscription services
- salary-consistent: Regular income deposits of similar amounts
- rent-recurring: Monthly housing/rent payments
- discretionary-heavy: High spending on entertainment, shopping, travel
- cash-heavy: Frequent cash withdrawals
- utility-regular: Consistent utility bill payments
- emi-committed: Regular EMI/loan payments

For EACH pattern you identify, provide evidence as a list of categories from the transactions.

If no clear pattern exists, return an empty patterns list.

Transactions:
{transactions}

Return ONLY this JSON (no markdown, no explanation):
{{"patterns":[{{"pattern":"<pattern-name>","evidence":["<category1>","<category2>"],"confidence":<0.0-1.0>}}]}}"""


# =============================================================================
# Response Explainer  (pipeline/explainer.py)
# =============================================================================

EXPLAINER_PROMPT = """You are a finance/risk manager. You need to provide your insighsts, based on the data below, provide a clear, concise answer to the user's question.
Include all specific numbers and amounts. Be direct

User Question: {query}
Data:
{data}

Answer:"""


# =============================================================================
# Banking Report — Customer Review  (pipeline/report_summary_chain.py)
# =============================================================================

CUSTOMER_REVIEW_PROMPT = """You are a senior credit analyst writing a banking transaction review for a loan underwriting committee.

IMPORTANT RULES:
- Only reference numbers and data provided below — do NOT invent figures
- Do NOT mention numeric scores or classifications (e.g. do NOT write "primary score 35/100" or "conduit account" — instead describe what actually happened)
- Do NOT mention or reference missing sections

STRUCTURE YOUR RESPONSE IN TWO PARAGRAPHS:

1. FINANCIAL OVERVIEW (4-6 lines): A factual summary of the customer's banking profile. Cover income (salary amount, frequency, source), monthly cashflow (average net, total inflow vs outflow), key spending categories, EMI and rent commitments, and any utility bills. If "Banking FOIR" is present, include the obligation-to-income ratio as a factual observation. Weave these as natural facts in a narrative flow — not as a list. NO risk commentary, NO event mentions — just the financial picture.

2. TRANSACTION EVENTS (one sentence per event): If a "DETECTED TRANSACTION EVENTS" block is present below, narrate EVERY event listed — [HIGH], [MEDIUM], and [POSITIVE] — as plain facts with the specific month and exact amount. Do NOT omit any event. Do NOT say "an event was detected" — state what the customer actually did (e.g. "In Jun 2025, the customer received ₹72,000 salary and transferred ₹72,000 to their own account the next day"). If no events block is present, omit this paragraph entirely.

Financial Data:
{data_summary}

Write the two-paragraph banking review:"""


# =============================================================================
# Banking Report — Customer Persona  (pipeline/report_summary_chain.py)
# =============================================================================

CUSTOMER_PERSONA_PROMPT = """Based on the complete financial profile for customer {customer_id}, describe who this customer is in 4-5 lines.

COMPLETE FINANCIAL DATA:
{comprehensive_data}

SAMPLE TRANSACTIONS:
{transaction_sample}

Describe the customer persona focusing on:
- Who they likely are (profession, lifestyle)
- Their financial behavior and discipline
- Spending patterns and priorities
- Overall financial health assessment

Write a 4-5 line customer persona description:"""


# =============================================================================
# Bureau Report — Executive Review  (pipeline/report_summary_chain.py)
# =============================================================================

BUREAU_REVIEW_PROMPT = """You are a senior credit analyst writing an executive summary for a loan underwriting committee.

IMPORTANT RULES:
- Only reference numbers and risk annotations provided below — do NOT invent figures
- No arithmetic — just narrate the pre-computed values and their tagged interpretations
- NEVER summarise, round, or omit any INR amount or percentage that appears in the data — quote every figure exactly as provided
- Features tagged [HIGH RISK], [MODERATE RISK], or [CONCERN] are red flags — highlight them in the Behavioral Insights paragraph only
- Features tagged [POSITIVE], [CLEAN], or [HEALTHY] are green signals — acknowledge them in the Behavioral Insights paragraph only

STRUCTURE YOUR RESPONSE IN TWO PARAGRAPHS:

1. PORTFOLIO OVERVIEW (6-10 lines): A factual summary of the customer's tradeline portfolio so the reader does not have to look at the raw data. Start with the big picture — total tradelines (how many live, how many closed), which loan products are present, total sanctioned exposure, total outstanding, and unsecured exposure. Then weave in the key highlights: credit card utilization percentage, any DPD values above zero, missed payment percentages, enquiry counts, loan acquisition velocity, and any loan product counts that are unusually high.

OBLIGATION & FOIR (mandatory if present): State the exact total bureau EMI obligation (INR amount), the exact unsecured EMI obligation (INR amount), the affluence income (INR amount), and BOTH the total FOIR percentage and unsecured FOIR percentage — quote the exact numbers, do not round or omit any figure.

EXPOSURE (mandatory if present): Quote the EXACT numbers from "Sanctioned Exposure Trend" and "Exposure Commentary" — do not paraphrase or compress. Specifically: (a) the 12M trend — state the exact from and to INR amounts and the exact percentage change; (b) the 6M avg trend — state the prior 6M avg INR amount, the recent 6M avg INR amount, and the exact percentage change; (c) from "Exposure Commentary" — state the exact peak INR amount, the exact peak month, which products led it, the current INR amount, the current month, the active products, and whether the trend is rising/stable/declining. Every INR figure and every percentage must appear verbatim.

Present these as natural facts within the narrative flow — not as a separate list. NO risk commentary, NO opinions, NO concern flags — just state the portfolio composition and the notable data points together in one cohesive summary.


2. BEHAVIORAL INSIGHTS (4-6 lines): Now provide the risk interpretation. Use the tagged annotations ([HIGH RISK], [POSITIVE], etc.) and the COMPOSITE RISK SIGNALS to narrate the customer's credit behavior — enquiry pressure, repayment discipline, utilization, loan acquisition velocity. Give commentery over leverage or exposure trend available. CRITICAL: Every inference MUST cite the actual number that backs it (e.g., "utilization is elevated at 65%", "3 new PL trades in 6 months signals loan stacking", "0% missed payments but DPD of 12 days detected", "Exposure is elevated"). Never state a risk opinion without the supporting data point.

Bureau Portfolio Summary:
{data_summary}

# # Write the two-paragraph bureau portfolio review:"""

# BUREAU_REVIEW_PROMPT = """
# You are a senior credit analyst writing an executive summary for a loan underwriting committee.

# STRICT RULES
# - Use ONLY the numbers, percentages, and annotations present in the input data.
# - DO NOT perform arithmetic, estimates, rounding, or calculations.
# - DO NOT invent or infer numbers that are not explicitly provided.
# - Every INR amount and percentage appearing in the data must be quoted exactly as written.
# - Never modify numeric formatting.
# - Maintain professional credit risk reporting language.

# TAG INTERPRETATION RULES
# - [HIGH RISK], [MODERATE RISK], [CONCERN] → negative credit signals
# - [POSITIVE], [CLEAN], [HEALTHY] → positive credit signals
# - Tagged signals must be interpreted ONLY in the Behavioral Insights section.

# OUTPUT FORMAT
# Your response must contain EXACTLY TWO paragraphs in the following order:

# ------------------------------------------------
# 1. PORTFOLIO OVERVIEW (6–10 lines)

# Provide a factual summary of the customer's credit portfolio so the reader does not need to inspect the raw data.

# Start with the overall portfolio composition:
# - total tradelines
# - number of active vs closed
# - loan product types present
# - total sanctioned exposure
# - total outstanding balance
# - unsecured exposure

# Then incorporate key portfolio statistics if present:
# - credit card utilization %
# - DPD values greater than zero
# - missed payment %
# - enquiry counts
# - loan acquisition velocity
# - unusually high counts of any loan product

# OBLIGATION & FOIR (mandatory if present):
# State the following exactly as provided:
# - total bureau EMI obligation (INR)
# - unsecured EMI obligation (INR)
# - affluence income (INR)
# - total FOIR %
# - unsecured FOIR %

# EXPOSURE (mandatory if present):
# Quote the exposure data EXACTLY as written:
# • 12M trend — from INR amount, to INR amount, percentage change  
# • 6M average trend — prior 6M avg INR amount, recent 6M avg INR amount, percentage change  
# • Exposure commentary — peak INR amount, peak month, leading products, current INR amount, current month, active products, and stated trend (rising/stable/declining)

# Write these details naturally within the narrative.
# DO NOT include opinions, interpretation, or risk commentary in this paragraph.

# ------------------------------------------------
# 2. BEHAVIORAL INSIGHTS (4–6 lines)

# Interpret the customer's credit behavior using:
# - tagged annotations
# - composite risk signals
# - exposure trajectory signals

# Rules for this section:
# - Every inference MUST reference the exact number supporting it.
# - Do not make any claim without citing the data point.
# - Highlight negative tagged signals ([HIGH RISK], [MODERATE RISK], [CONCERN]).
# - Acknowledge positive tagged signals ([POSITIVE], [CLEAN], [HEALTHY]).

# Interpret behavioral patterns including:
# - enquiry pressure
# - repayment discipline
# - utilization behavior
# - loan acquisition velocity
# - **exposure trajectory or unusually high exposure levels**

# When discussing exposure behavior, reference the same numbers quoted in the exposure section (e.g., large peak exposure, sharp 12M growth, or high current exposure relative to portfolio composition).

# Example style:
# "Utilization is elevated at 65% and tagged [HIGH RISK]."
# "Three new personal loans in 6 months indicates loan stacking."
# "Exposure rose from INR X to INR Y (Z%), indicating rapid credit build-up."

# ------------------------------------------------

# INPUT DATA
# Bureau Portfolio Summary:
# {data_summary}

# Write the two-paragraph bureau portfolio review now.
# """

# =============================================================================
# Combined Report — Synthesised Executive Summary  (pipeline/report_summary_chain.py)
# =============================================================================

COMBINED_EXECUTIVE_PROMPT = """Prepare a synthesised executive summary for customer {customer_id} \
by merging the banking transaction analysis and credit-bureau tradeline analysis below into \
ONE cohesive paragraph (6-8 lines).

STRICT RULES:
- Write in formal third-person tone throughout (e.g. "The customer exhibits…", never "we" or "I")
- Do NOT repeat the source summaries verbatim — distil and merge the key points
- Cover: income & cash-flow health, spending discipline, credit-portfolio exposure, \
obligation / FOIR levels, payment behaviour / DPD, and an overall creditworthiness assessment
- If "Additional Data" is provided: quote the EXACT FOIR percentages (total and unsecured) \
and quote the EXACT exposure commentary sentences including INR amounts, peak month, active \
products, and trend direction — do NOT paraphrase or compress these figures
- If either summary is empty or missing, work with whatever is available
- Be factual — do not invent numbers that are not present in the inputs
- Do NOT mention numeric scores or classifications by label (e.g. do NOT write "primary score 35/100") \
— instead narrate the underlying fact (e.g. "received salary and immediately transferred funds to own account")
- End with a clear one-line creditworthiness assessment (positive, cautious, or negative)
- Do NOT add any meta-commentary, personal notes, disclaimers, or remarks about the writing \
process — output ONLY the summary paragraph followed by the standard note below

After the summary paragraph, add exactly this note on a new line:
Note: This is a synthesised summary based on automated banking and bureau analyses. \
Independent verification is recommended before final credit decisions.
{additional_context}
BANKING SUMMARY:
{banking_summary}

BUREAU SUMMARY:
{bureau_summary}

Write the combined executive summary:"""
