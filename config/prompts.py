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

CUSTOMER_REVIEW_PROMPT = """Based on the following financial data for customer {customer_id}, write a 4-6 line professional financial review.

IMPORTANT RULES:
- Only mention data that is provided below
- Do NOT mention or reference missing sections
- Be factual and concise
- Do NOT mention numeric scores or classifications (e.g. do NOT write "primary score 35/100" or "conduit account" — instead describe what actually happened)
- Highlight any red flags or positive signals for lending decision

DETECTED EVENTS — CRITICAL PRIORITY:
If a "DETECTED TRANSACTION EVENTS" block is present in the data below:
- Events marked [HIGH] MUST be narrated as facts: describe what the customer did (e.g. "received salary in Jun 2025 and transferred ₹72,000 to own account the next day")
- Do NOT say "a HIGH event was detected" — state the fact directly with the month and amount
- Events marked [POSITIVE] should be acknowledged as financial strengths
- Events marked [MEDIUM] should be included if space allows

Financial Data:
{data_summary}

Write a concise, professional review:"""


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
- Features tagged [HIGH RISK], [MODERATE RISK], or [CONCERN] are red flags — highlight them in the Behavioral Insights paragraph only
- Features tagged [POSITIVE], [CLEAN], or [HEALTHY] are green signals — acknowledge them in the Behavioral Insights paragraph only

STRUCTURE YOUR RESPONSE IN TWO PARAGRAPHS:

1. PORTFOLIO OVERVIEW (6-10 lines): A factual summary of the customer's tradeline portfolio so the reader does not have to look at the raw data. Start with the big picture — total tradelines (how many live, how many closed), which loan products are present, total sanctioned exposure, total outstanding, and unsecured exposure. Then weave in the key highlights that stand out from the behavioral features: credit card utilization percentage, any DPD values above zero, missed payment percentages, enquiry counts, loan acquisition velocity, and any loan product counts that are unusually high. Present these as natural facts within the narrative flow — not as a separate list. NO risk commentary, NO opinions, NO concern flags — just state the portfolio composition and the notable data points together in one cohesive summary.

2. BEHAVIORAL INSIGHTS (4-6 lines): Now provide the risk interpretation. Use the tagged annotations ([HIGH RISK], [POSITIVE], etc.) and the COMPOSITE RISK SIGNALS to narrate the customer's credit behavior — enquiry pressure, repayment discipline, utilization, loan acquisition velocity. CRITICAL: Every inference MUST cite the actual number that backs it (e.g., "utilization is elevated at 65%", "3 new PL trades in 6 months signals loan stacking", "0% missed payments but DPD of 12 days detected"). Never state a risk opinion without the supporting data point.

Bureau Portfolio Summary:
{data_summary}

Write the two-paragraph bureau portfolio review:"""


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
payment behaviour / DPD, and an overall creditworthiness assessment
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

BANKING SUMMARY:
{banking_summary}

BUREAU SUMMARY:
{bureau_summary}

Write the combined executive summary:"""
