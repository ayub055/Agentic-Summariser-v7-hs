# Banking Feature Dictionary — Computed Variables from Bank Statements

> The bureau tells you what the customer **owes**. The bank statement tells you how they **live**.
>
> This document defines computable features from transaction data — structured like a bureau scorecard but derived entirely from bank statements. Each feature has a clear computation, risk interpretation, and interaction with other features.
>
> Design principle: Every feature must be a **number**, not a label. Numbers go into models. Labels are for humans — and we derive labels FROM numbers, not the other way around.

---

## 1. Income Quality Features

These answer: "How reliable and sustainable is the income flowing into this account?"

---

### 1.1 Salary Consistency Ratio

```
salary_months_present / total_months_analyzed
```

| Value | Interpretation |
|---|---|
| 1.0 | Salary received every month — stable employment |
| 0.8–0.99 | Minor gap — could be delayed processing, leave without pay |
| 0.5–0.8 | Significant gaps — contractual, gig, or unstable employment |
| < 0.5 | Salary absent more than present — this is not reliable salaried income |

**Bureau equivalent:** None. Bureau has employment status from application form (self-declared). This is ground truth.

**Interaction:** When salary_consistency < 0.8 AND income_source_count = 1, the customer has a single unreliable income stream. When salary_consistency < 0.8 AND income_source_count ≥ 3, the customer may be a freelancer with diversified income — less concerning.

---

### 1.2 Salary Stability Index (CV)

```
std(monthly_salary_amounts) / mean(monthly_salary_amounts)
```

Measures how much the salary amount varies month to month.

| Value | Interpretation |
|---|---|
| < 0.05 | Fixed salary — very stable (pure base pay, no variable) |
| 0.05–0.15 | Minor variation — likely small variable/incentive component |
| 0.15–0.30 | Meaningful variation — significant commission/bonus component |
| > 0.30 | Highly variable — income is effectively uncertain; use P25 not mean for capacity |

**Why this matters for lending:** A customer with mean salary ₹80k but CV 0.35 has months at ₹52k. If you size the EMI at 50% of ₹80k (₹40k), in low months the FOIR is 77%. The right capacity metric is P25 of salary, not mean.

**Computation note:** Exclude months with no salary (those are captured by consistency ratio above). Only measure the variation of months where salary WAS received.

---

### 1.3 Income Source Count

```
count of distinct regular credit sources (appears 2+ months)
```

Classify each credit into: employer salary, employer bonus, rental, business receipts, interest/dividends, freelance, individual transfers, government. Count sources appearing in 2+ months.

| Value | Interpretation |
|---|---|
| 1 | Single-source income — fragile (employer-dependent) |
| 2–3 | Diversified — salary + rental or salary + freelance; resilient |
| 4+ | Highly diversified — either genuinely multi-stream or messy accounting |

**Interaction:** income_source_count = 1 AND salary_consistency = 1.0 → classic salaried employee, reliable but fragile. income_source_count ≥ 3 AND salary_consistency < 0.7 → gig/freelance worker, resilience depends on whether sources are stable individually.

---

### 1.4 Salary Growth Rate

```
(mean of last 3 months salary - mean of first 3 months salary) / mean of first 3 months salary × 100
```

| Value | Interpretation |
|---|---|
| > +10% | Positive career trajectory — raise, promotion |
| 0% to +10% | Stable — standard inflation adjustment or no change |
| -5% to 0% | Slight decline — possible variable component reduction |
| < -5% | Declining income — role change, reduced hours, employer distress |

**Interaction:** salary_growth < -10% AND emi_to_salary_ratio > 0.4 → the customer's obligations were sized for the old salary; current capacity is weaker than FOIR suggests.

---

### 1.5 Income Concentration Ratio

```
salary_credits / total_credits × 100
```

How much of total inflow comes from identifiable salary vs other sources.

| Value | Interpretation |
|---|---|
| > 85% | Income is almost entirely salary — clean, assessable, but fragile |
| 60–85% | Salary-dominant with supplementary income — healthy if supplements are recurring |
| 30–60% | Mixed income — salary is NOT the primary funding source; need to assess other sources |
| < 30% | Salary is minor — this is either a business account or non-primary account |

**Why it matters:** If income_concentration < 60%, calculating FOIR from salary alone underestimates the customer's real income AND makes the FOIR look worse than reality. But the non-salary income needs to be assessed for sustainability before including it.

---

### 1.6 Effective Net Income

```
total_credits - (self_transfers_in + loan_disbursals + round_trip_credits + reciprocal_inflows)
```

Strip out all credits that are NOT real income: self-transfers from own accounts, loan disbursals, money that came in and went right back out (round-trips), and the gross side of reciprocal flows. What remains is the customer's actual earning power.

| Context | Interpretation |
|---|---|
| effective_net ≈ total_credits | Clean statement — inflows are genuine income |
| effective_net < 0.7 × total_credits | 30%+ of inflow is non-income — stated inflow overstates earning power |
| effective_net < 0.5 × total_credits | Majority of inflow is financial churning — this account's flows are misleading |

**This is the single most important income feature.** Every ratio that uses "income" in the denominator should use effective_net_income, not raw total_credits.

---

## 2. Expense & Obligation Features

These answer: "What does the customer owe, and is it sustainable?"

---

### 2.1 Banking FOIR (Fixed Obligation to Income Ratio)

```
(sum of all identified EMI + rent + insurance + NACH mandates) / effective_net_income × 100
```

Unlike bureau FOIR (which uses declared income and bureau-tracked obligations only), banking FOIR uses ACTUAL observed outflows and ACTUAL observed income.

| Value | Interpretation |
|---|---|
| < 30% | Low leverage — significant room for new obligations |
| 30–50% | Moderate — standard for salaried borrowers with 1-2 loans |
| 50–65% | High — at or near typical lender cutoffs |
| > 65% | Stretched — adding any new EMI creates default risk |

**Why banking FOIR > bureau FOIR:**
- Captures obligations not yet on bureau (new loans, informal commitments)
- Uses actual income, not self-declared
- Includes rent and insurance (bureau doesn't)
- Shows the REAL picture vs the declared picture

**Interaction:** When banking_foir > bureau_foir + 15pp, there are significant obligations the bureau doesn't see. When banking_foir < bureau_foir - 10pp, some bureau obligations may have been closed or are being serviced from another account.

---

### 2.2 FOIR Trend (Slope)

```
linear regression slope of monthly_foir values across the analysis period
```

FOIR at a point in time is a snapshot. The TREND tells you where it's heading.

| Value | Interpretation |
|---|---|
| Negative slope | FOIR improving — obligations reducing relative to income |
| Near zero | Stable — obligations and income moving together |
| Positive slope (< 2pp/month) | Gradual deterioration — monitor |
| Positive slope (> 2pp/month) | Rapid deterioration — customer is stacking obligations faster than income grows |

**This catches what bureau misses:** Bureau shows point-in-time balances. Bank statement shows whether obligations are growing faster than income — before the bureau updates.

---

### 2.3 Essential Expense Ratio

```
(grocery + utility + pharmacy + rent + education + transport) / total_debits × 100
```

What fraction of spending goes to non-discretionary needs.

| Value | Interpretation |
|---|---|
| > 70% | Essentials-dominated — limited room to cut spending if income drops |
| 40–70% | Balanced — some discretionary cushion exists |
| < 40% | Lifestyle-heavy — customer CAN cut back if needed (this is actually positive for resilience) |

**Counter-intuitive insight:** A LOW essential ratio is actually GOOD for lending, not bad. It means the customer has spending they can sacrifice under stress. A customer at 75% essential already has no fat to trim.

---

### 2.4 Discretionary Elasticity

```
(discretionary_spend_month_after_stress - discretionary_spend_normal_months) / discretionary_spend_normal_months
```

When a stress event occurs (salary delayed, large unexpected debit, bounce), does the customer actually CUT discretionary spending in response?

| Value | Interpretation |
|---|---|
| < -0.3 | Customer actively cuts back when stressed — adaptive, responsible |
| -0.3 to 0 | Mild adjustment — some awareness |
| ≈ 0 | No change — customer doesn't react to financial stress, or has sufficient buffer |
| > 0 | Spending INCREASES during stress — possibly stress-spending or using credit |

**Why this matters:** Two customers with identical FOIR can have completely different risk profiles. One cuts dining by 60% when salary is late. The other puts it on a credit card. The bank statement reveals this; the bureau never can.

---

### 2.5 Obligation Servicing Regularity

```
for each recurring obligation:
    months_paid_on_time / months_due × 100
aggregate: weighted average across all obligations
```

Not just whether obligations are paid, but whether they're paid on time, every time.

| Value | Interpretation |
|---|---|
| 100% | Perfect — every obligation met every month |
| 90–99% | Near-perfect — one-off miss, likely timing |
| 75–90% | Irregular — some months missed or late |
| < 75% | Unreliable servicing — customer struggles to meet commitments |

**Interaction:** obligation_regularity = 100% AND propping_up_detected = True → obligations are met, but not self-funded. The regularity is borrowed, not earned.

---

### 2.6 Hidden Obligation Estimate

```
total_fixed_recurring_debits_from_banking - total_emi_from_bureau
```

The difference between what the bank statement shows as recurring fixed outflows and what the bureau reports as outstanding obligations. The gap is hidden obligations — loans from NBFCs not yet reported, informal commitments, buy-now-pay-later, employer advances, etc.

| Value | Interpretation |
|---|---|
| ≈ 0 | Bank and bureau agree — no hidden obligations |
| ₹5k–₹15k | Minor gap — could be subscriptions, insurance, or small BNPL |
| ₹15k–₹40k | Significant gap — likely undisclosed loans or obligations |
| > ₹40k | Major undisclosed obligations — banking FOIR is materially worse than bureau FOIR |

---

## 3. Cashflow & Liquidity Features

These answer: "Can the customer survive a disruption?"

---

### 3.1 Surplus Retention Rate

```
(effective_net_income - total_debits) / effective_net_income × 100
averaged across months
```

What % of real income is the customer keeping each month.

| Value | Interpretation |
|---|---|
| > 25% | Strong saver — accumulating reserves |
| 10–25% | Moderate — retaining some buffer |
| 0–10% | Thin margin — spending nearly everything earned |
| < 0% | Deficit spender — spending more than earning, depleting savings or borrowing |

**Interaction:** surplus_retention < 0% for 3+ consecutive months → savings runway is depleting. Cross with balance_runway (below) to estimate months until zero.

---

### 3.2 Balance Runway (Months of Survival)

```
current_average_balance / average_monthly_essential_expenses
```

If income stopped tomorrow, how many months can the customer cover essential expenses from their balance?

| Value | Interpretation |
|---|---|
| > 6 months | Well-cushioned — can weather extended income disruption |
| 3–6 months | Moderate buffer — can survive a job transition |
| 1–3 months | Thin buffer — one missed salary and stress begins |
| < 1 month | No buffer — lives paycheck to paycheck |

**This is the ultimate liquidity metric.** It combines balance (stock) with expenses (flow) into a single survival estimate.

**Interaction:** balance_runway < 1 AND post_salary_burn_days < 7 → extremely fragile; any disruption = immediate default.

---

### 3.3 Minimum Balance Cushion

```
min(daily_closing_balance across analysis period) / average_monthly_salary
```

The lowest point the account ever reaches, relative to salary. This is the tightest moment — the stress test that already happened.

| Value | Interpretation |
|---|---|
| > 0.5 | Customer never drops below half a month's salary — comfortable |
| 0.1–0.5 | Tight but managed — dips low but recovers |
| 0–0.1 | Near-zero minimums — one unexpected debit and the account bounces |
| < 0 (overdraft) | Account went negative — already experienced cashflow failure |

---

### 3.4 Balance Volatility (Intra-Month)

```
std(daily_balance) / mean(daily_balance) across the analysis period
```

How much does the balance swing within and across months.

| Value | Interpretation |
|---|---|
| < 0.3 | Stable balance — steady income and spending |
| 0.3–0.6 | Moderate swings — typical salary account (spikes at salary, declines through month) |
| 0.6–1.0 | High volatility — large inflows and outflows creating big swings |
| > 1.0 | Extreme volatility — account is used for pass-through or business-like activity |

**Interaction:** balance_volatility > 1.0 AND income_concentration < 50% → likely a business/transaction account being presented as a personal salary account.

---

### 3.5 Cash-to-Digital Ratio

```
(ATM withdrawals + cash deposits) / total_transaction_volume × 100
```

What fraction of the customer's financial life happens in cash (untraceable).

| Value | Interpretation |
|---|---|
| < 10% | Digital-first — nearly all spending visible and assessable |
| 10–25% | Normal cash usage — some cash for daily expenses |
| 25–50% | Cash-heavy — significant portion of expenses untrackable |
| > 50% | Cash-dominant — the bank statement shows less than half the real financial picture |

**Why it matters for lending:** Every rupee in cash is a rupee the lender cannot verify. High cash ratio means true expenses, true obligations, and true spending patterns are unknowable from the statement alone. Risk models should apply a confidence penalty proportional to cash ratio.

---

### 3.6 Inflow-Outflow Timing Gap

```
median(days between salary credit and 50th percentile of monthly debits being completed)
```

How quickly does money flow through the account after salary? This measures the "velocity" of money through the account.

| Value | Interpretation |
|---|---|
| > 20 days | Slow velocity — money sits in the account; customer spends gradually |
| 10–20 days | Normal — typical mid-month spending pattern |
| 5–10 days | Fast velocity — most spending front-loaded after salary |
| < 5 days | Near-instant — money arrives and leaves almost immediately (conduit behavior) |

**Interaction:** timing_gap < 5 AND self_transfer_ratio > 0.4 → classic conduit account. timing_gap < 5 AND emi_count > 3 → all obligations cluster right after salary; no buffer for unexpected debits later in the month.

---

## 4. Behavioral & Discipline Features

These answer: "What kind of financial manager is this customer?"

---

### 4.1 Spending Regularity Index

```
1 - (std(monthly_total_debits) / mean(monthly_total_debits))
```

How predictable is the customer's monthly spending? Inverted CV so higher = more regular.

| Value | Interpretation |
|---|---|
| > 0.85 | Highly predictable spender — budgets and sticks to it |
| 0.7–0.85 | Moderately regular — some month-to-month variation |
| 0.5–0.7 | Irregular — spending swings significantly |
| < 0.5 | Erratic — spending is unpredictable; risk models have low confidence |

**Why it matters:** Predictable spenders are lower risk even at higher FOIR, because their future behavior can be modeled with confidence. Erratic spenders are higher risk even at lower FOIR, because next month could look nothing like the average.

---

### 4.2 Savings Propensity Score

```
weighted score of:
  +2: SIP/mutual fund debits present (recurring)
  +2: FD creation detected
  +1: Insurance premium (recurring)
  +1: PPF/NPS contribution detected
  +1: surplus_retention > 15%
  -1: no investment activity AND surplus_retention < 5%
  -2: crypto/gambling debits detected
normalize to 0–10 scale
```

Composite score measuring the customer's savings and investment behavior.

| Value | Interpretation |
|---|---|
| 8–10 | Active saver/investor — financially disciplined |
| 5–7 | Moderate — some savings behavior but not systematic |
| 2–4 | Minimal savings activity — income consumed in full |
| 0–1 | No savings, possible speculative behavior — high-risk financial habits |

**Interaction:** savings_propensity ≥ 7 AND foir > 50% → customer is leveraged but disciplined; may have assets not visible here. savings_propensity ≤ 2 AND foir > 50% → leveraged and undisciplined; high default risk.

---

### 4.3 Obligation Priority Score

```
when month has insufficient funds for all obligations:
    which obligations get paid first?
    score = (EMI payments made / EMI payments due) under stress months
```

In months where the customer can't pay everything, what do they prioritize? This reveals their relationship with formal debt.

| Behavior | Interpretation |
|---|---|
| EMIs paid first, discretionary cut | Responsible — protects credit record, adjusts lifestyle |
| Rent paid first, EMIs missed | Survival-first — will default on loans before becoming homeless |
| Discretionary maintained, EMIs missed | Irresponsible — prioritizes lifestyle over obligations |
| Nothing paid — all obligations missed | Complete cashflow failure — no prioritization possible |

**Why this matters:** A customer who has bounced twice but ALWAYS paid their EMI first is lower risk than a customer who has never bounced but maintains lifestyle spending at the expense of obligations during tight months. The bank statement reveals this; the bureau only sees the bounce.

---

### 4.4 Financial Planning Horizon

```
weighted indicator:
  - Annual insurance payments (plans ahead for large debits)
  - SIP on specific dates (systematic planning)
  - Tax-saving investments in Jan-Mar (plans for financial year)
  - Rent/EMI on consistent dates (structured obligations)
  vs.
  - Frequent overdraft/low balance
  - Reactive borrowing (credits from individuals before obligation dates)
  - Last-minute payments (obligation paid 3+ days late)
```

Does this customer plan ahead or live reactively?

| Score | Interpretation |
|---|---|
| High planning | Customer anticipates future cash needs — structured financial life |
| Mixed | Some planning elements, some reactive — typical |
| Low planning | Reactive financial behavior — obligations met just-in-time or late |

**Interaction:** financial_planning = high AND foir > 50% → the leverage is probably deliberate and managed. financial_planning = low AND foir > 50% → the leverage is accumulating without awareness.

---

### 4.5 Counterparty Concentration (Herfindahl Index)

```
for all debit recipients:
    share_i = amount_to_recipient_i / total_debits
    HHI = sum(share_i²)
```

How concentrated is the customer's spending across recipients?

| Value | Interpretation |
|---|---|
| > 0.25 | Highly concentrated — 1-2 recipients dominate (likely rent + EMI to one lender) |
| 0.10–0.25 | Moderately concentrated — few large payees + many small ones |
| 0.05–0.10 | Diversified — spending spread across many recipients (typical consumer) |
| < 0.05 | Highly diversified — many small transactions (indicates retail/UPI-heavy spending) |

**Why it matters:** High HHI means the customer's financial life depends on a few relationships. If the largest counterparty is a lender, the customer's spending is obligation-dominated. If it's a single individual, there's a dependency on that relationship.

---

## 5. Account Character Features

These answer: "What role does this account play in the customer's financial life?"

---

### 5.1 Account Utilization Score

```
total_debits / total_credits × 100
```

How much of what comes in gets used from this account.

| Value | Interpretation |
|---|---|
| > 95% | Full utilization — everything that comes in goes out; no accumulation |
| 70–95% | Active primary account — healthy usage with some retention |
| 40–70% | Partial utilization — income comes here but significant spending happens elsewhere |
| < 40% | Low utilization — this is a parking/savings account or income is routed out immediately |

**Interaction:** utilization < 40% AND self_transfer_ratio > 0.3 → income arrives here and is immediately sent to another account where the real spending happens. This statement is an incomplete picture.

---

### 5.2 Self-Transfer Ratio

```
(self_transfers_out + transfers_to_own_accounts) / total_debits × 100
```

What fraction of outflows goes to the customer's own accounts rather than to third parties.

| Value | Interpretation |
|---|---|
| < 5% | Minimal self-transfer — this IS the primary operating account |
| 5–20% | Some splitting — savings or secondary account exists |
| 20–40% | Significant routing — customer actively manages across accounts |
| > 40% | Conduit behavior — this account primarily moves money to another account |

---

### 5.3 Transaction Density

```
total_transactions / months_analyzed
```

| Value | Interpretation |
|---|---|
| > 100/month | Very active — primary operating account with high digital engagement |
| 50–100/month | Active — normal primary account usage |
| 20–50/month | Moderate — may be primary but less digital, or may be secondary |
| < 20/month | Low activity — likely secondary account, salary parking, or cash-heavy lifestyle |

**Interaction:** transaction_density < 20 AND salary present → salary comes here but spending happens elsewhere or in cash. The expense assessment from this account alone is unreliable.

---

### 5.4 Channel Mix Profile

```
upi_share = UPI transactions / total × 100
neft_rtgs_share = (NEFT + RTGS) / total × 100
nach_share = NACH/ECS / total × 100
cash_share = (ATM + cash) / total × 100
card_share = POS/card / total × 100
```

The channel composition reveals the customer's financial sophistication and transaction nature.

| Pattern | Interpretation |
|---|---|
| UPI-dominant (>60%) | Digital-native consumer — common for younger salaried |
| NEFT/RTGS-dominant (>40%) | Business-like or high-value transfers — unusual for pure salary account |
| NACH-dominant (>30%) | Obligation-heavy — most outflows are automated mandates |
| Cash-dominant (>40%) | Cash economy participant — limited digital footprint |
| Card-dominant (>30%) | Credit card usage — may indicate revolving credit dependency |

---

### 5.5 Weekend vs Weekday Spending Ratio

```
weekend_debits / weekday_debits (adjusted for day count)
```

Normalized for the fact that weekdays outnumber weekends.

| Value | Interpretation |
|---|---|
| < 0.8 | Lower weekend spend — obligations and routine dominate (EMI, rent, bills) |
| 0.8–1.2 | Balanced — even spending pattern |
| > 1.2 | Weekend-heavy — discretionary/lifestyle spending skews to weekends |
| > 2.0 | Significantly weekend-heavy — investigate (entertainment, gambling, or cash) |

---

## 6. Stability & Trend Features

These answer: "Is the customer's financial position improving or deteriorating?"

---

### 6.1 Monthly Net Cashflow Trend

```
linear regression slope of (monthly_inflow - monthly_outflow) across months
```

| Value | Interpretation |
|---|---|
| Positive slope | Improving — accumulating more each month (income growing or expenses declining) |
| Near zero | Stable — no change in net position |
| Negative slope | Deteriorating — spending growth outpacing income, or income declining |

**This is the most forward-looking feature.** A customer with moderate FOIR but negative trend is heading toward default. A customer with high FOIR but positive trend is recovering.

---

### 6.2 Balance Trend Slope

```
linear regression slope of month-end balance across months
normalize by dividing by average balance to get % change per month
```

| Value | Interpretation |
|---|---|
| > +5%/month | Accumulating — savings growing |
| 0 to +5% | Stable to slightly growing |
| 0 to -5% | Slight erosion — monitor |
| < -5%/month | Rapid depletion — balance is being drained; count months to zero |

**Interaction:** balance_trend < -5% AND surplus_retention < 0% → customer is in a declining spiral; spending more than earning AND depleting savings. Estimate months_to_zero = current_balance / abs(monthly_net_loss).

---

### 6.3 Expense Growth Rate

```
(mean monthly debits last 3 months - mean monthly debits first 3 months) / mean first 3 months × 100
```

| Value | Interpretation |
|---|---|
| < 0% | Expenses declining — customer is cutting back (could be positive discipline or forced austerity) |
| 0–10% | Normal growth — inflation, lifestyle progression |
| 10–25% | Elevated growth — new obligations or lifestyle inflation |
| > 25% | Rapid expense growth — new EMIs, lifestyle change, or financial stress (emergency spending) |

**Interaction:** expense_growth > 15% AND salary_growth < 5% → expenses growing faster than income; unsustainable trajectory even if current snapshot looks okay.

---

### 6.4 Income-Expense Divergence

```
salary_growth_rate - expense_growth_rate
```

The most powerful single number: is the gap between income and expenses widening (positive) or closing (negative)?

| Value | Interpretation |
|---|---|
| > +10% | Income growing much faster than expenses — improving financial position |
| 0 to +10% | Healthy — income keeping pace with or exceeding expenses |
| -10% to 0 | Expenses catching up to income — margin is eroding |
| < -10% | Scissors opening — expenses outpacing income; projected to cross within months |

---

## 7. Risk Composite Features

These combine multiple signals into single risk indicators for model consumption.

---

### 7.1 Financial Fragility Index

```
fragility = (
    (1 - surplus_retention_rate/25) × 0.25      # how thin is the margin
  + (1 - balance_runway/6) × 0.25               # how small is the buffer
  + (post_salary_burn_days < 7) × 0.20          # how fast does money leave
  + (salary_consistency < 0.9) × 0.15           # how reliable is income
  + (obligation_regularity < 0.9) × 0.15        # are obligations being met
)
clamp to 0–1
```

Single composite score answering: "How close is this customer to financial failure?"

| Value | Interpretation |
|---|---|
| < 0.2 | Robust — multiple buffers, stable income, manageable obligations |
| 0.2–0.4 | Moderate fragility — one or two weak areas but overall manageable |
| 0.4–0.6 | Elevated fragility — multiple stress indicators present |
| 0.6–0.8 | High fragility — slim margins, unreliable income, or obligations at capacity |
| > 0.8 | Critical — any single disruption (salary delay, unexpected expense) will cause default |

---

### 7.2 Statement Reliability Score

```
reliability = (
    (1 - cash_to_digital_ratio/50) × 0.25       # how much is visible
  + (account_utilization > 60%) × 0.25           # is this the primary account
  + (1 - self_transfer_ratio/40) × 0.20          # money stays here vs routed out
  + (transaction_density > 30) × 0.15            # enough activity to assess
  + (1 - reciprocal_flow_ratio/20) × 0.15        # flows aren't inflated
)
clamp to 0–1
```

Can we trust this statement to represent the customer's real financial life?

| Value | Interpretation |
|---|---|
| > 0.8 | High reliability — statement is comprehensive and representative |
| 0.5–0.8 | Moderate — some gaps but broadly usable |
| 0.3–0.5 | Low — significant portions of financial life are not visible here |
| < 0.3 | Unreliable — this statement does not represent the customer's actual financial position |

**Why this matters:** Every other feature is only as good as the statement it's computed from. If reliability < 0.5, all features should carry a confidence discount. A model should weight banking features by reliability score.

---

### 7.3 Debt Capacity Estimate

```
monthly_capacity = effective_net_income × (target_foir - current_banking_foir) / 100
```

Using the customer's actual income and actual obligations, how much additional EMI can they absorb before hitting the target FOIR threshold (typically 55%)?

| Value | Interpretation |
|---|---|
| > ₹25k | Significant capacity — can absorb a sizable new EMI |
| ₹10k–₹25k | Moderate capacity — small to medium loan possible |
| ₹0–₹10k | Minimal capacity — only very small obligations should be added |
| < ₹0 | No capacity — already over-leveraged; adding any EMI creates default risk |

**Interaction:** debt_capacity < 0 AND obligation_regularity = 100% → customer is over-leveraged but somehow managing (probably propped up or supplemented). This is fragile — approval would push them past the breaking point.

---

### 7.4 Behavioral Risk Score

```
risk = sum of:
  +3: cascading_bounce_detected
  +3: loan_to_loan_servicing_detected
  +2: propping_up_detected
  +2: balance_dressing_detected
  +2: debt_servicing_from_non_salary
  +1: income_supplementation_dependency
  +1: obligation_stacking (3+ new EMIs in 4 months)
  +1: pre_application_shift_detected
  +1: round_number_individual_credits > 3
  -1: savings_propensity ≥ 7
  -1: balance_runway > 3
  -1: surplus_retention > 15%
normalize to 0–10
```

Composite of all behavioral red flags and green flags detected from multi-signal inference patterns.

---

## 8. Feature Interactions — The Cross-Signal Matrix

> The power of bank statement analysis is not in any individual feature. It's in the combinations. Two features that are individually "medium risk" can be "critical risk" together.

| Feature A | Feature B | Combined Interpretation |
|---|---|---|
| banking_foir > 55% | salary_stability_cv > 0.25 | Obligations sized for average salary, but salary varies widely — FOIR in low months exceeds 75% |
| surplus_retention < 0% | balance_trend negative | Active savings depletion — customer is in a death spiral with a calculable runway |
| obligation_regularity = 100% | propping_up = True | Perfect on paper, dependent in reality — one supporter away from cascading failure |
| savings_propensity > 7 | foir > 55% | Leveraged but disciplined — may have assets elsewhere; lower risk than FOIR alone suggests |
| cash_ratio > 40% | essential_ratio > 70% | High cash + all essentials = likely paying rent/groceries in cash to landlord/kirana — true expenses much higher than digital trail shows |
| statement_reliability < 0.5 | any risk feature | Discount the finding — statement doesn't capture enough of financial life to be conclusive |
| income_source_count = 1 | salary_consistency < 0.8 | Single income source that is itself unreliable — fragility² |
| expense_growth > 15% | salary_growth < 0% | Income-expense scissors — mathematically guaranteed to cross; timing is the only question |
| self_transfer_ratio > 40% | account_utilization < 50% | This is not the primary account — ALL expense-based features from this statement are unreliable |
| discretionary_elasticity < -0.3 | balance_runway > 3 | Customer adapts under stress AND has buffer — low default risk even if FOIR is elevated |
| foir_trend positive | hidden_obligations > ₹20k | FOIR getting worse AND there are obligations the bureau doesn't see — actual trajectory is worse than visible |

---

## 9. Feature Computation Priority

| Phase | Features | Effort | Dependencies |
|---|---|---|---|
| **Phase 1** | salary_consistency, salary_stability_cv, salary_growth, income_concentration, banking_foir, surplus_retention, balance_runway, expense_growth | Low | Salary identification (already exists) |
| **Phase 2** | effective_net_income, self_transfer_ratio, account_utilization, cash_ratio, transaction_density, foir_trend, balance_trend | Medium | Self-transfer detection, income source classification |
| **Phase 3** | hidden_obligations, obligation_regularity, spending_regularity, discretionary_elasticity, counterparty_concentration | Medium | Recurring debit identification, category classification |
| **Phase 4** | fragility_index, reliability_score, behavioral_risk_score, debt_capacity | Low | Phases 1-3 must be complete |
| **Phase 5** | financial_planning_horizon, obligation_priority, income_expense_divergence, fungibility | High | Stress event detection, temporal analysis |

---

*Last updated: 2026-03*
