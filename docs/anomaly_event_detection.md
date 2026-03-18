# Anomaly-Based Event Detection — Risk Manager's Playbook

> Statistical and behavioral anomaly detections for bank statement analysis.
> These are NOT keyword matches — they detect **patterns that need explanation**.
>
> Principle: If something deviates sharply from the customer's own baseline, it is an event.
> The job is to find the specific transaction(s) that caused the deviation and surface them.

---

## 1. Inflow Anomalies

### 1a. Monthly Inflow Spike (>2× Median) — IMPLEMENTED

**Status:** Implemented in `tools/event_detector.py` → `_detect_inflow_spike()`

**What:** A month's total inflow exceeds 2× the median monthly inflow.

**Why it matters:** The excess credit needs sourcing. It could be a loan disbursal, asset sale, one-time bonus, insurance claim, or informal borrowing. A lender must know which — because loan disbursal inflates apparent income, while a bonus is genuinely positive.

**Implementation details:**
- Uses `_compute_monthly_credit_stats()` for median baseline (requires ≥3 months, median ≥₹1,000)
- Identifies top 3 contributing credits per spike month
- Each credit classified via `_classify_credit_source()`: lender, employer, government, individual, or raw narration
- Event type: `inflow_spike`, significance: `high`
- One event per spike month; flows to LLM via `format_events_for_prompt()`

**Example output:**
```
[HIGH    ] Sep 2025: Monthly inflow ₹3,20,000 is 5.0× the median (₹64,000) — top credits: ₹2,00,000 (possible loan disbursal), ₹50,000 (salary/employer credit)
```

---

### 1b. Single Credit > 100% of Monthly Median — IMPLEMENTED

**Status:** Implemented in `tools/event_detector.py` → `_detect_large_single_credit()`

**What:** Any single credit transaction exceeding 110% of the median monthly credit total (with 10% buffer to avoid borderline noise), excluding routine salary.

**Why it matters:** Large one-off credits distort average income calculations. A risk manager needs to know if a ₹3L credit in a ₹80k salary account is a PF withdrawal, a personal loan, a property sale, or money received from family. Each has completely different risk implications.

**Implementation details:**
- Uses same `_compute_monthly_credit_stats()` baseline as 1a
- Threshold: `amount > median × 1.10` (10% buffer avoids flagging marginal cases)
- **Salary skip:** Credits matching salary keywords (SALARY, SAL, PAYROLL) are excluded; when `salary_amount` is known, also checks ±30% amount range
- Groups qualifying credits by month → one event per month listing top 3
- Capped at 5 events total (keeps months with largest credits)
- Event type: `large_single_credit`, significance: `high`

**Example output:**
```
[HIGH    ] Sep 2025: Single credit exceeding monthly median (₹64,000) — ₹2,00,000 (4.0× median, possible loan disbursal)
[HIGH    ] Oct 2025: 2 credit(s) exceeding monthly median (₹64,000) — ₹1,30,000 (2.6× median, transfer from Rajesh Kumar), ₹80,000 (1.6× median, individual transfer)
```

**Shared helpers (also new):**
- `_compute_monthly_credit_stats(df)` — returns `(credits_df, monthly_totals, median)` or `(None, None, None)`
- `_classify_credit_source(narration)` — classifies into: possible loan disbursal, credit from bank/NBFC, salary/employer credit, government credit, transfer from {name}, individual transfer, or raw narration

**Significance:** HIGH

---

### 1c. Non-Salary Income Volatility

**What:** After removing salary credits, the remaining inflow swings wildly month to month (CV > 0.5).

**Why it matters:** High non-salary income volatility suggests the customer relies on irregular income sources — freelance work, rental, business receipts, or informal transfers. Lenders cannot rely on this income for EMI capacity.

**Detection:**
```
non_salary_inflow_per_month = total_credits - salary_credits (per month)
cv = std(non_salary_inflow_per_month) / mean(non_salary_inflow_per_month)
flag if cv > 0.5
```

**What to report:** Monthly non-salary inflow chart, the most volatile months, and the transactions causing the spikes.

**Significance:** MEDIUM

---

## 2. Outflow Anomalies

### 2a. Monthly Outflow Spike (>2× Median)

**What:** A month's total outflow exceeds 2× the median monthly outflow.

**Why it matters:** A sudden spending spike could indicate an emergency (medical), a large purchase (property down payment), debt repayment, or financial distress (paying off informal loans). The specific debit(s) that caused the spike tell the story.

**Detection:**
```
monthly_outflows = group debits by month → sum
median_outflow = median(monthly_outflows)
flag months where monthly_outflow > 2 × median_outflow
```

**What to report:** The top 3-5 debit transactions that contributed most to the excess. Show narration, amount, recipient.

**Significance:** MEDIUM

---

### 2b. New Large Recurring Debit Appears

**What:** A debit of ₹5,000+ to the same payee/pattern starts appearing monthly when it wasn't there before.

**Why it matters:** This is almost certainly a new EMI, a new rent obligation, or a new subscription. If the customer recently took a loan that doesn't yet show on the bureau, this catches it. It directly impacts FOIR.

**Detection:**
```
for each month M from month 4 onwards:
    find debits in M that match a payee seen in M-1 but NOT in months 1 to M-3
    if amount is consistent (±15%) across M and M-1 → new recurring debit
```

**What to report:** Payee/narration pattern, monthly amount, start month. Flag explicitly: "Possible new EMI obligation not yet reflected in bureau."

**Significance:** HIGH

---

### 2c. Recurring Debit Disappears

**What:** A debit that appeared monthly for 3+ months suddenly stops.

**Why it matters:** If it's an EMI that stops, either the loan was closed (positive) or the customer defaulted/bounced (negative). If it's a rent payment that stops, the customer may have moved. The absence itself is the signal — what stopped and why?

**Detection:**
```
find debit patterns (same payee ±15% amount) present in 3+ consecutive months
flag if pattern is absent in the most recent 2 months
```

**What to report:** The recurring debit that disappeared — payee, usual amount, last seen month. Cross-reference with NACH/bounce keywords to determine if it stopped cleanly or via default.

**Significance:** MEDIUM (needs context)

---

### 2d. Same-Day Pass-Through

**What:** A large credit is received and a debit of ≥70% of that credit goes out on the same day or next business day.

**Why it matters:** Money that enters and exits immediately is not the customer's money — it's passing through. This is the classic conduit/mule account signal. Even if not malicious, it means the visible balance and inflow don't represent the customer's actual financial position.

**Detection:**
```
for each credit C where amount > 0.3 × salary:
    find debits on same day or next day where sum ≥ 0.7 × C.amount
    if found → pass-through event
```

**What to report:** The credit (source, amount) and the matching debit(s) (recipients, amounts). Calculate pass-through ratio.

**Significance:** HIGH

---

## 3. Balance & Cashflow Anomalies

### 3a. Post-Salary Burn Rate

**What:** How many days after salary credit does it take for 80% of the salary to be spent?

**Why it matters:** A customer who burns through 80% of salary in 5 days is living paycheck-to-paycheck with no buffer. One missed salary = immediate default. A customer who takes 25 days has a sustainable spending pattern.

**Detection:**
```
for each salary credit:
    cumulative_debits = running sum of debits after salary date
    days_to_80pct = days until cumulative_debits ≥ 0.8 × salary_amount
    avg across months
```

**What to report:** Average days to 80% burn. Flag if < 7 days: "Customer exhausts salary within one week — minimal financial buffer." Include month-by-month trend.

**Significance:** HIGH if < 7 days, MEDIUM if 7-14 days

---

### 3b. Consecutive Declining Month-End Balance

**What:** Month-end balance (or average daily balance) declines for 3+ consecutive months.

**Why it matters:** A steadily declining balance means the customer is spending more than they earn — the savings buffer is eroding. If the decline continues, the account will hit zero and the customer will need to borrow. This is the earliest signal of upcoming financial distress.

**Detection:**
```
month_end_balance = last transaction balance per month (or approximate from cumulative)
flag if balance[M] < balance[M-1] < balance[M-2] for any run of 3+ months
```

**What to report:** The declining trend with amounts. "Month-end balance declined from ₹1.2L (Oct) → ₹85k (Nov) → ₹52k (Dec) → ₹18k (Jan) — 4-month erosion of 85%."

**Significance:** HIGH if decline > 50% over the period

---

### 3c. Month-End Stress Pattern

**What:** Concentration of small credits (₹1k–₹15k) from individuals in the last 5 days of the month, not seen mid-month.

**Why it matters:** Borrowing small amounts from friends/family at month-end to survive until salary is a classic cash-crunch signal. These are informal loans that won't appear on any bureau but indicate the customer cannot cover expenses through the full month.

**Detection:**
```
for each month:
    last_5_day_credits = credits from individuals in last 5 calendar days
    mid_month_credits = credits from individuals in days 6-25
    if count(last_5_day_credits) > 2 × count(mid_month_credits):
        flag as month-end stress borrowing
```

**What to report:** Count and total of late-month small credits, with narration samples. "4 credits totaling ₹28,000 from individuals in last 5 days of month — possible informal borrowing to bridge cash gap."

**Significance:** MEDIUM (HIGH if recurring across 3+ months)

---

### 3d. Net Cashflow Reversal

**What:** Customer normally has positive monthly net cashflow (inflow > outflow) but suddenly goes negative.

**Why it matters:** A single negative month is noise. But the first negative month after a streak of positive months is a leading indicator — something changed. Losing income, gaining a new obligation, or a large one-off expense. Identify what flipped it.

**Detection:**
```
monthly_net = monthly_inflow - monthly_outflow
if customer had 3+ positive months followed by a negative month:
    flag with the top debits that caused the reversal
```

**What to report:** The reversal month, net amount, and the specific transactions that caused outflows to exceed inflows.

**Significance:** MEDIUM (first occurrence), HIGH (2+ consecutive negative months)

---

## 4. Transaction Velocity & Pattern Anomalies

### 4a. Daily Transaction Count Spike

**What:** Number of debit transactions on a single day exceeds 3× the customer's average daily debit count.

**Why it matters:** A burst of transactions in one day could indicate panic spending, clearing multiple obligations at once, or account takeover. The specific transactions tell the story.

**Detection:**
```
daily_debit_count = count of debits per day
avg_daily = mean(daily_debit_count) for days with at least 1 transaction
flag days where count > 3 × avg_daily AND count ≥ 5
```

**What to report:** The date, transaction count, total amount, and the individual transactions.

**Significance:** LOW (informational — context determines risk)

---

### 4b. First-Time High-Value Payee

**What:** A debit of ₹25,000+ goes to a recipient the customer has never paid before.

**Why it matters:** Regular payees are expected (rent, EMIs, family). A large payment to someone entirely new is unusual — could be a security deposit, a down payment, an informal loan given, or a scam payment.

**Detection:**
```
extract recipient name from each debit narration
for each debit where amount > ₹25,000:
    if recipient never appears in prior months → flag
```

**What to report:** Recipient name, amount, narration, and date. "First-time payment of ₹1,50,000 to RAJESH KUMAR — not seen in prior 5 months of transaction history."

**Significance:** LOW-MEDIUM (contextual)

---

### 4c. Salary Date Drift

**What:** Salary credit date shifts by >5 days from the customer's usual pattern.

**Why it matters:** If salary consistently arrives on the 1st but suddenly comes on the 10th, the employer may be in financial difficulty. Salary delays are a leading indicator of employer distress — which eventually becomes the customer's problem.

**Detection:**
```
usual_salary_day = mode of salary credit dates (day of month)
for each salary credit:
    if abs(day - usual_salary_day) > 5 → flag
```

**What to report:** Expected date vs actual date, delay in days. "Salary received on 12th (usual: 1st) — 11-day delay. Potential employer cash flow issue."

**Significance:** MEDIUM (HIGH if 2+ consecutive delayed months)

---

### 4d. UPI Micro-Transaction Explosion

**What:** UPI transaction count increases by 2× or more in recent months vs earlier months, with average transaction size dropping.

**Why it matters:** A customer switching from fewer large transactions to many small UPI payments may be splitting expenses to manage cash flow — paying ₹500 at a time instead of ₹5,000 at once. It's a behavioral stress signal even when total spend is unchanged.

**Detection:**
```
monthly_upi_count = count of UPI transactions per month
monthly_upi_avg_size = mean UPI amount per month
recent_3m = last 3 months
earlier_3m = first 3 months
if mean(recent_3m.count) > 2 × mean(earlier_3m.count) AND
   mean(recent_3m.avg_size) < 0.6 × mean(earlier_3m.avg_size):
    flag
```

**What to report:** Transaction count trend and average size trend. "UPI transactions increased from avg 45/month to 112/month while average size dropped from ₹2,100 to ₹680 — possible expense fragmentation."

**Significance:** MEDIUM

---

## 5. Debt & Obligation Signals

### 5a. EMI-to-Salary Ratio Creep

**What:** The ratio of total EMI debits to salary is increasing month over month.

**Why it matters:** If EMI was 30% of salary 6 months ago and is now 45%, the customer has taken on new debt. This is FOIR deterioration in real-time — visible in bank statements before the bureau updates.

**Detection:**
```
monthly_emi = sum of EMI-tagged debits per month
monthly_salary = salary credit per month
emi_ratio = monthly_emi / monthly_salary
flag if emi_ratio increased by >10pp over the analysis period
```

**What to report:** EMI ratio trend month by month. Identify which new EMI debits appeared and when. "EMI burden increased from 28% (Jul) to 43% (Dec) — new recurring debit of ₹12,500 to BAJAJ FINANCE started in Sep."

**Significance:** HIGH

---

### 5b. Round-Number Credits from Individuals

**What:** Credits of exact round numbers (₹10,000, ₹25,000, ₹50,000, ₹1,00,000) from non-institutional sources.

**Why it matters:** Round-number transfers from individuals are almost always informal loans or family support. They are NOT income, but they inflate the inflow. If the customer is receiving ₹50,000 round-number credits from individuals every month, their actual self-sustaining income is lower than inflow suggests.

**Detection:**
```
for each credit:
    if amount is exact round number (mod 5000 == 0 or mod 10000 == 0) AND amount ≥ 10000:
        if source is individual (UPI, IMPS from person name, not company/bank):
            flag
```

**What to report:** Total round-number individual credits per month, frequency, and sources. "₹1,60,000 in round-number credits from 3 individuals over 6 months — possible informal borrowing inflating apparent inflow."

**Significance:** MEDIUM

---

### 5c. Multiple Loan Disbursals in Analysis Period

**What:** Two or more loan disbursal credits detected within the statement period.

**Why it matters:** Multiple loans in a short period = debt stacking. The customer is borrowing from multiple sources — possibly to service existing debt. Even if each loan individually seems manageable, the combined obligation may not be.

**Detection:**
```
count credits matching lender names or loan disbursal keywords
flag if count ≥ 2 within 6-month period
```

**What to report:** Each disbursal — date, amount, source. Total borrowed. "Two loan disbursals in 4 months: ₹2,50,000 from BAJAJ FINANCE (Aug) + ₹1,80,000 from TATA CAPITAL (Nov). Combined new debt: ₹4,30,000."

**Significance:** HIGH

---

### 5d. Debt Servicing from Non-Salary Funds

**What:** EMI or loan repayment debits occur in a month where salary was not received, funded instead by credits from individuals or other accounts.

**Why it matters:** If the customer missed salary but still paid EMIs using borrowed money or self-transfers, they are masking the true stress level. The EMI was paid — but not from income. Next month may not be so lucky.

**Detection:**
```
for months with EMI debits but no salary credit:
    check if credits from individuals or self-transfers cover the EMI amount
    flag as "EMI funded from non-income sources"
```

**What to report:** The month, missing salary, EMI amount, and how it was funded. "Nov: No salary received. ₹35,000 EMI to HDFC BANK paid from ₹40,000 credit received from SURESH KUMAR on same day — EMI serviced from informal borrowing."

**Significance:** HIGH

---

## 6. Behavioral Classification Events

### 6a. Spending Concentration Shift

**What:** Customer's top spending category changes significantly between first half and second half of the analysis period.

**Why it matters:** If grocery/essentials replace discretionary spending as the top category, the customer may be cutting back — a behavioral stress signal. If EMI replaces everything, new debt is crowding out lifestyle.

**Detection:**
```
first_half_top_category = largest debit category in months 1-3
second_half_top_category = largest debit category in months 4-6
if they differ AND the shift is from discretionary → essential/EMI:
    flag as "spending pattern shift"
```

**What to report:** Before/after comparison. "Spending shifted: Travel & Entertainment was #1 category (Jul-Sep, ₹45k/month) → dropped to #4 (Oct-Dec, ₹8k/month). EMI moved to #1 at ₹52k/month."

**Significance:** MEDIUM

---

### 6b. Weekend/Off-Hours Cash Withdrawals

**What:** ATM withdrawals concentrated on weekends or late evening, especially in increasing amounts.

**Why it matters:** Cash is untraceable. Frequent off-hours cash withdrawals in increasing amounts suggest the customer is funding something they don't want in their transaction trail — gambling, informal lending, or personal expenses hidden from a business partner/spouse. From a risk perspective, untracked spending is unassessable spending.

**Detection:**
```
atm_withdrawals on Sat/Sun or public holidays
flag if count > 4/month AND amount increasing month over month
```

**What to report:** Frequency, total amount, trend. "12 weekend ATM withdrawals in 3 months totaling ₹1,85,000 — amounts increasing from avg ₹12k to ₹20k per withdrawal."

**Significance:** MEDIUM

---

## 7. Multi-Signal Inference Patterns (Analyst-Grade)

> These are patterns an experienced credit analyst infers by **reading across the statement**, not by looking at any single metric. Each requires combining 2-4 data points to reach a conclusion that no individual signal provides.

---

### 7a. Robbing Peter to Pay Paul (Loan-to-Loan Servicing)

**What:** Loan disbursal credit from Lender A is followed within 7 days by EMI payments to Lender B and/or Lender C.

**Why it matters:** The customer is not using the new loan for its stated purpose — they are borrowing from one lender to service another. This is the most reliable early indicator of a debt spiral. A bounced NACH is a lagging indicator; this pattern appears months before the default.

**The inference an analyst makes:** "This customer took a ₹2L loan from Tata Capital on Nov 3rd. By Nov 8th, ₹45k went to HDFC BANK (EMI) and ₹18k to Bajaj Finance (EMI). The loan didn't fund a purchase — it funded survival. The customer's actual cashflow cannot support their existing obligations."

**Detection:**
```
for each credit from known lender (>₹50k):
    window = debits within 7 days
    emi_debits_in_window = debits matching EMI/loan keywords to OTHER lenders
    if sum(emi_debits_in_window) > 0.25 × loan_credit_amount:
        flag as loan-to-loan servicing
```

**Signals combined:** Loan disbursal detection + EMI payee identification + temporal proximity

**Significance:** CRITICAL — near-certain predictor of future default

---

### 7b. Balance Window Dressing (Statement Grooming)

**What:** Large credits appear in the last 3-5 days of the month (or quarter), followed by debits of similar amounts in the first 3-5 days of the next period.

**Why it matters:** The customer (or someone helping them) is parking money temporarily to inflate average balance on the bank statement. This is the #1 trick used before loan applications. An average balance of ₹2L looks healthy — until you realize ₹1.5L of it was parked for 5 days each month and withdrawn immediately after.

**The inference an analyst makes:** "Average balance shows ₹1.8L, but if I strip out these 4 month-end deposits that reverse within 3 days, the real average balance is ₹45k. The statement has been dressed."

**Detection:**
```
for each month boundary:
    late_credits = credits in last 5 days of month from individuals/self
    early_debits = debits in first 5 days of next month to same payees or self
    if any late_credit has a matching early_debit (±20% amount, same/similar payee):
        flag as balance dressing
        calculate "real" avg balance excluding dressed amounts
```

**Signals combined:** Month-boundary credit timing + matching reverse debit + payee linkage + balance impact calculation

**Significance:** HIGH — indicates deliberate misrepresentation

---

### 7c. The Propping-Up Pattern (External Dependency)

**What:** Credits from a specific individual arrive precisely when the customer's balance would have gone negative or below a critical threshold (like an EMI amount due).

**Why it matters:** Someone is monitoring the customer's account and bailing them out. The customer appears to be servicing all obligations — but they aren't doing it from their own income. Remove this one supporter and the entire financial structure collapses. This dependency is invisible on any bureau report.

**The inference an analyst makes:** "Every month, 2-3 days before the NACH debit for ₹35k EMI, SURESH KUMAR sends exactly ₹30-40k. The customer's own balance at that point is ₹8-12k. Without Suresh, the EMI bounces every single month."

**Detection:**
```
for each recurring obligation (EMI/NACH/rent):
    obligation_date = usual debit date
    pre_obligation_credits = credits from individuals 1-4 days before obligation_date
    if same individual sends credit before the same obligation in 3+ months:
        if customer's balance before that credit < obligation_amount:
            flag as "externally propped obligation"
```

**Signals combined:** Recurring debit identification + individual credit timing + balance sufficiency check + counterparty consistency across months

**Significance:** CRITICAL — obligations are not self-sustaining

---

### 7d. Income Supplementation Dependency

**What:** Customer's total monthly debits consistently exceed their salary, with the gap filled by regular credits from family/individuals.

**Why it matters:** The salary alone does not support the customer's lifestyle. They are structurally dependent on external support. FOIR calculated on salary alone is misleading — the customer already cannot cover existing expenses from salary, let alone a new EMI.

**The inference an analyst makes:** "Salary is ₹65k. Monthly spending is ₹82-90k. The gap is covered by ₹15-25k/month from two family members. Without family support, this customer is ₹20k/month underwater. Adding a ₹15k EMI on top means the family needs to double their support — or the loan defaults."

**Detection:**
```
for each month:
    gap = total_debits - salary_credit
    if gap > 0:
        individual_credits = credits from individuals (not employers, not banks)
        if individual_credits cover >60% of the gap:
            track as supplemented month
if supplemented months ≥ 3:
    flag as "income supplementation dependency"
    report: true_self_sustaining_capacity = salary - (debits - individual_credits)
```

**Signals combined:** Salary identification + expense totaling + individual credit sourcing + deficit calculation across multiple months

**Significance:** HIGH — loan capacity is overstated if based on salary alone

---

### 7e. Obligation Stacking Timeline

**What:** Plotting when each recurring debit obligation first appeared reveals rapid leveraging — 3+ new obligations within 4 months.

**Why it matters:** Any single new EMI might be fine. But when an analyst sees new obligations appearing every few weeks, the pattern tells a story of escalating credit hunger. The customer is on an acquisition spree — each new loan possibly funding the servicing of the previous ones. This is the behavioral fingerprint of someone heading toward over-leverage.

**The inference an analyst makes:** "Jul: New EMI ₹8k to Bajaj. Sep: New EMI ₹12k to Tata Capital. Oct: New EMI ₹6.5k to KreditBee. Nov: New NACH ₹4.2k to Slice. Four new obligations in 5 months — total ₹30.7k/month added against ₹75k salary. FOIR went from 32% to 73% in half a year."

**Detection:**
```
identify all recurring debit patterns (same payee ±15%, appears 2+ months)
for each pattern, determine first_seen_month
sort by first_seen_month
if 3+ new patterns started within any 4-month window:
    flag as "rapid obligation stacking"
    report cumulative FOIR impact
```

**Signals combined:** Recurring debit identification + first-appearance dating + FOIR trend calculation + temporal clustering

**Significance:** HIGH — FOIR deteriorating faster than bureau can capture

---

### 7f. Fungibility Test (Salary-Spend Independence)

**What:** Measure whether spending behavior changes based on whether salary has arrived yet in a given month.

**Why it matters:** A customer with savings buffer spends steadily regardless of salary timing — their spending on day 5 looks the same whether salary arrived on day 1 or hasn't arrived yet. A customer with no buffer freezes spending until salary hits, then bursts. The degree of salary-dependence reveals the true financial cushion — or lack of it.

**The inference an analyst makes:** "In months where salary came on the 1st, this customer made 8 transactions averaging ₹4,200 in the first week. In months where salary was delayed to the 7th, they made 1 transaction of ₹350 in the first week. This customer has zero financial buffer — they literally cannot spend until salary arrives."

**Detection:**
```
for months where salary arrived late (>5 days later than usual):
    pre_salary_daily_spend = avg daily debits before salary in that month
for months where salary arrived on time:
    same_period_daily_spend = avg daily debits in same calendar days

fungibility_ratio = pre_salary_daily_spend / same_period_daily_spend
if fungibility_ratio < 0.3:
    flag as "high salary dependency — near-zero financial buffer"
```

**Signals combined:** Salary timing detection + pre/post salary spending comparison + cross-month behavioral comparison

**Significance:** HIGH — reveals true buffer that balance alone doesn't show

---

### 7g. Festive Spending Without Recovery

**What:** Large spending spike during known festival months (Oct-Nov Diwali, Mar-Apr financial year-end) that is NOT followed by a return to normal spending within 2 months.

**Why it matters:** Festival spending spikes are normal and expected. The question is whether the customer recovers. If spending drops back to baseline in December, it was discretionary — the customer managed it. If December and January spending remains elevated or balance never recovers, the festival spending became debt that is now being serviced. The analyst is looking for the recovery, not the spike.

**The inference an analyst makes:** "October outflow spiked to ₹1.8L vs usual ₹95k. Normal. But November was ₹1.4L and December ₹1.3L. The customer didn't snap back — they're still paying off Diwali three months later, likely through credit card revolving or BNPL installments."

**Detection:**
```
spike_months = months where outflow > 1.5 × median
for each spike_month:
    recovery_months = next 2 months
    if mean(recovery_months.outflow) > median × 1.2:
        flag as "spending spike without recovery"
    if balance at end of recovery period < balance before spike - (spike excess × 0.5):
        flag as "spending spike eroded savings"
```

**Signals combined:** Spending spike detection + post-spike trend analysis + balance recovery check

**Significance:** MEDIUM-HIGH — distinguishes managed spending from debt creation

---

### 7h. Cascading Obligation Failure

**What:** One obligation bounces (NACH RETURN, ECS RETURN), and within the same month or next month, another obligation is missed or bounced.

**Why it matters:** A single bounce can be a timing issue — salary arrived a day late, insufficient balance for a few hours. But when one bounce triggers another, it reveals that the customer was running on zero margin. They had exactly enough for all obligations, and one failure cascaded. This customer has no recovery capacity.

**The inference an analyst makes:** "Oct 5: NACH RETURN ₹18k (HDFC auto loan). Oct 12: NACH RETURN ₹12k (Bajaj personal loan). Same month, two bounces — the customer couldn't cover either. ₹30k total bounced against ₹70k salary means 43% of obligations failed simultaneously. This isn't a timing issue — it's structural insolvency."

**Detection:**
```
bounce_events = transactions matching NACH RETURN, ECS RETURN, MANDATE RETURN, DISHONOUR
group by month
if any month has 2+ bounce events to different payees:
    flag as "cascading obligation failure"
if consecutive months each have 1+ bounce (even different payees):
    flag as "sustained obligation failure"
```

**Signals combined:** Bounce keyword detection + payee differentiation + temporal clustering + multi-month persistence check

**Significance:** CRITICAL — strongest default predictor in bank statements

---

### 7i. The "Too Clean" Statement

**What:** Transaction count or total throughput is suspiciously low for someone with this salary level. A customer earning ₹1.2L/month but showing only 8-12 transactions and ₹40k throughput.

**Why it matters:** Either this isn't the primary account (salary is split or routed elsewhere) or the customer lives predominantly in cash. Both are problems for a lender — in the first case, you can't see the real spending; in the second, the untraceable spending is a black box.

**The inference an analyst makes:** "₹1.2L salary, but total debits are only ₹38k. Where does the other ₹82k go? Either there's another account doing the heavy lifting, or this customer withdraws cash and operates outside the banking system. Either way, I can't assess their real expenses."

**Detection:**
```
monthly_debit_total = sum of all debits per month
monthly_txn_count = count of transactions per month
utilization = avg(monthly_debit_total) / salary_amount

if utilization < 0.4 AND avg(monthly_txn_count) < 15:
    flag as "low-utilization account — likely not primary"
if cash_withdrawal / salary > 0.5:
    flag as "cash-heavy lifestyle — expenses not traceable"
```

**Signals combined:** Transaction volume + salary amount + debit utilization ratio + cash withdrawal proportion

**Significance:** MEDIUM — doesn't indicate risk directly but means the statement is unreliable for expense assessment

---

### 7j. Reciprocal Flow With Single Counterparty

**What:** The customer regularly sends money TO and receives money FROM the same individual, with both directions showing significant amounts.

**Why it matters:** This is different from a round-trip (same amount bouncing). This is an ongoing two-way financial relationship — could be a joint business, informal lending circle, kite-flying between accounts, or rotating credit arrangement. The net flow matters more than the gross: if you net it out, the actual transfer might be tiny, but the gross inflates both inflow and outflow.

**The inference an analyst makes:** "Amit Kumar sends ₹50k/month and receives ₹45k/month from this customer. Gross: ₹95k. Net: ₹5k. The statement shows ₹50k extra inflow and ₹45k extra outflow that are essentially the same money going back and forth. Real inflow is overstated by ₹50k and real outflow by ₹45k."

**Detection:**
```
extract counterparty names from all transactions
for each counterparty seen in both credits and debits:
    total_received_from = sum of credits from this person
    total_sent_to = sum of debits to this person
    if total_received_from > ₹20k AND total_sent_to > ₹20k:
        net = total_received_from - total_sent_to
        flag as "reciprocal flow"
        report gross vs net, and the inflated inflow/outflow amounts
```

**Signals combined:** Counterparty extraction + bidirectional flow detection + net-vs-gross calculation

**Significance:** MEDIUM-HIGH — distorts all flow-based metrics if not netted out

---

### 7k. Pre-Application Behavioral Shift

**What:** The customer's financial behavior changed significantly in the 2-3 most recent months compared to the 3-4 months before that — in a way that makes the statement look better.

**Why it matters:** If cash withdrawals dropped, discretionary spending decreased, balance increased, and fewer irregular payments appear — all in the last 2 months — the customer may be grooming the statement for this loan application. The earlier months show the real behavior.

**The inference an analyst makes:** "Months 1-4: avg balance ₹22k, cash withdrawals ₹35k/month, spending ₹95k/month. Months 5-6: avg balance ₹68k, cash withdrawals ₹8k/month, spending ₹60k/month. The customer suddenly became financially disciplined exactly when they'd need a clean statement for a loan application. The earlier period is the real picture."

**Detection:**
```
recent = last 2 months
earlier = months 1-4
compare:
    avg_balance: if recent > 2 × earlier → suspicious improvement
    cash_withdrawals: if recent < 0.4 × earlier → suspicious reduction
    discretionary_spend: if recent < 0.5 × earlier → suspicious cut
    individual_credits: if recent < 0.3 × earlier → stopped informal borrowing
if 3 or more of these shifts occurred simultaneously:
    flag as "possible pre-application statement grooming"
    report the earlier-period metrics as "likely representative behavior"
```

**Signals combined:** Multi-metric comparison across time periods + simultaneous improvement detection + directionality check (all improvements, not mixed)

**Significance:** HIGH — the earlier period should be used for risk assessment, not the recent "clean" period

---

### 7l. Salary Thinning (Partial Salary Credits)

**What:** Salary amount decreases over the analysis period — not a one-time change (which could be a raise/cut) but a gradual erosion, or salary arriving in 2-3 splits instead of one lump sum.

**Why it matters:** A salary arriving in splits (₹40k on 1st + ₹25k on 5th instead of the usual ₹65k lump sum) suggests the employer is in cash flow difficulty and is paying in tranches. A gradual decline (₹70k → ₹65k → ₹58k → ₹52k) may indicate variable pay components shrinking, bonus structure changing, or the customer moving to a lower role. Neither will show on the bureau.

**The inference an analyst makes:** "Salary was consistently ₹72k lump-sum through August. September onwards it arrives as two credits: ₹45k on the 2nd and ₹27k on the 8th. The employer is staggering payroll — they don't have the full amount on salary day. If this employer fails, the customer's income disappears."

**Detection:**
```
for each month:
    salary_credits = credits matching salary pattern
    if count(salary_credits) > 1 AND combined amount ≈ usual salary:
        flag as "split salary — possible employer cash flow stress"
    if salary_amount declining >5% month-over-month for 3+ months:
        flag as "eroding salary — variable component shrinking"
```

**Signals combined:** Salary pattern identification + split detection + trend analysis across months

**Significance:** HIGH — leading indicator of employer distress that precedes job loss

---

### 7m. The Lifestyle-Income Mismatch

**What:** Transaction patterns indicate a lifestyle tier inconsistent with the stated salary — either far above (funded by invisible sources) or far below (money going elsewhere).

**Why it matters:** A ₹50k salaried person making ₹15k restaurant payments and ₹30k fashion purchases monthly is either supplemented by undeclared income, burning savings, or accumulating credit card debt. Conversely, a ₹2L salaried person with only ₹20k lifestyle spend may be routing income to undisclosed obligations.

**The inference an analyst makes:** "₹55k salary. Monthly spending on dining + fashion + entertainment = ₹48k. That's 87% of salary on discretionary alone before rent, EMIs, or essentials. This lifestyle is not funded by this salary — there's money coming from somewhere I can't see, or this person is heading for a cliff."

**Detection:**
```
discretionary_categories = [dining, fashion, entertainment, travel, electronics]
discretionary_monthly = sum of debits in discretionary categories
essential_monthly = sum of debits in essential categories (EMI, rent, grocery, bills)
total_committed = discretionary_monthly + essential_monthly

if total_committed > 0.9 × salary AND discretionary > 0.4 × salary:
    flag as "lifestyle exceeds income — unsustainable without external funding"
if total_committed < 0.3 × salary AND no significant savings/investment activity:
    flag as "low account utilization — expenses likely handled elsewhere"
```

**Signals combined:** Category-level spending analysis + salary benchmarking + savings activity check

**Significance:** MEDIUM-HIGH — reveals hidden funding or hidden obligations

---

## 8. Implementation Notes

### Priority Order (by signal strength)

**Tier 1 — Strongest Predictors (implement first)**

| # | Event | Effort | Signal Value |
|---|---|---|---|
| 1 | Cascading obligation failure (7h) | Low | Critical |
| 2 | Loan-to-loan servicing (7a) | Medium | Critical |
| 3 | The propping-up pattern (7c) | High | Critical |
| 4 | Debt servicing from non-salary (5d) | Medium | Very High |
| 5 | Same-day pass-through (2d) | Low | Very High |
| 6 | Monthly inflow spike >2× median (1a) | Low | Very High |
| 7 | New large recurring debit (2b) | Medium | Very High |

**Tier 2 — High-Value Multi-Signal Patterns**

| # | Event | Effort | Signal Value |
|---|---|---|---|
| 8 | Obligation stacking timeline (7e) | Medium | High |
| 9 | Income supplementation dependency (7d) | Medium | High |
| 10 | Balance window dressing (7b) | Medium | High |
| 11 | Pre-application behavioral shift (7k) | Medium | High |
| 12 | Post-salary burn rate (3a) | Medium | High |
| 13 | EMI-to-salary ratio creep (5a) | Medium | High |
| 14 | Consecutive declining balance (3b) | Low | High |
| 15 | Salary thinning / split salary (7l) | Medium | High |
| 16 | Fungibility test (7f) | High | High |
| 17 | Multiple loan disbursals (5c) | Low | High |

**Tier 3 — Contextual & Behavioral**

| # | Event | Effort | Signal Value |
|---|---|---|---|
| 18 | Reciprocal flow with counterparty (7j) | Medium | Medium-High |
| 19 | Lifestyle-income mismatch (7m) | Medium | Medium-High |
| 20 | Festive spending without recovery (7g) | Medium | Medium-High |
| 21 | The "too clean" statement (7i) | Low | Medium |
| 22 | Round-number individual credits (5b) | Low | Medium |
| 23 | Month-end stress borrowing (3c) | Medium | Medium |
| 24 | Salary date drift (4c) | Low | Medium |
| 25 | Recurring debit disappears (2c) | Medium | Medium |
| 26 | Net cashflow reversal (3d) | Low | Medium |
| 27 | Spending concentration shift (6a) | Medium | Medium |
| 28 | UPI micro-transaction explosion (4d) | Medium | Medium |

### Architecture

Each detector follows the same pattern:
```python
def _detect_inflow_spike(df: pd.DataFrame, salary_amount: float) -> list:
    """Returns list of event dicts with type, date, amount, significance, description."""
    ...
```

All detectors are called from `detect_events()` in `tools/event_detector.py` and their results are merged, deduplicated, and sorted by significance.

The key difference from keyword-based detection: these detectors compute the customer's **own baseline** first, then flag deviations from that baseline. There are no hardcoded amount thresholds — everything is relative to the customer's own salary and spending patterns.

---

*Last updated: 2026-03*
