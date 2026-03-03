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

*Last updated: 2026-03*
