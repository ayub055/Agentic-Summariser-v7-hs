# Tools & Logic Sanity Check — Complete Reference

> **Generated**: 2026-03-17
> **Scope**: All files in `tools/`, merchant extraction logic, groupby/aggregation sanity, scorecard & thresholds

---

## Table of Contents

1. [Data Source: `data/loader.py`](#1-data-source-dataloaderpy)
2. [tools/analytics.py — Banking Analytics (16 functions)](#2-toolsanalyticspy--banking-analytics)
   - [2.1 debit_total](#21-debit_total)
   - [2.2 get_total_income](#22-get_total_income)
   - [2.3 get_spending_by_category](#23-get_spending_by_category)
   - [2.4 top_spending_categories](#24-top_spending_categories)
   - [2.5 spending_in_date_range](#25-spending_in_date_range)
   - [2.6 list_customers](#26-list_customers)
   - [2.7 list_categories](#27-list_categories)
   - [2.8 get_credit_statistics](#28-get_credit_statistics)
   - [2.9 get_debit_statistics](#29-get_debit_statistics)
   - [2.10 get_transaction_counts](#210-get_transaction_counts)
   - [2.11 get_balance_trend](#211-get_balance_trend)
   - [2.12 detect_anomalies](#212-detect_anomalies)
   - [2.13 get_income_stability](#213-get_income_stability)
   - [2.14 get_cash_flow](#214-get_cash_flow)
   - [2.15 generate_customer_report](#215-generate_customer_report)
   - [2.16 generate_lender_profile](#216-generate_lender_profile)
   - [2.17 Analytics Cross-Cutting Issues](#217-analytics-cross-cutting-issues)
3. [tools/category_resolver.py — Category Presence Lookup](#3-toolscategory_resolverpy--category-presence-lookup)
4. [tools/transaction_fetcher.py — Merchant Extraction & Transaction Grouping](#4-toolstransaction_fetcherpy--merchant-extraction--transaction-grouping)
5. [Merchant Extraction Deep Dive (narration_utils.py)](#5-merchant-extraction-deep-dive-narration_utilspy)
6. [Top Merchants Logic (customer_report_builder.py)](#6-top-merchants-logic-customer_report_builderpy)
7. [tools/account_quality.py — Account Classification](#7-toolsaccount_qualitypy--account-classification)
8. [tools/event_detector.py — Transaction Event Detection](#8-toolsevent_detectorpy--transaction-event-detection)
9. [tools/scorecard.py — Risk Scorecard](#9-toolsscorecardpy--risk-scorecard)
10. [tools/bureau_chat.py — Bureau Query Tools](#10-toolsbureau_chatpy--bureau-query-tools)
11. [tools/bureau.py — Bureau Report Orchestrator](#11-toolsbureaupy--bureau-report-orchestrator)
12. [tools/combined_report.py — Combined Report](#12-toolscombined_reportpy--combined-report)
13. [tools/excel_exporter.py — Excel Export](#13-toolsexcel_exporterpy--excel-export)
14. [tools/__init__.py — Tool Registry Exports](#14-tools__init__py--tool-registry-exports)
15. [GroupBy / Aggregation Sanity Check](#15-groupby--aggregation-sanity-check)
16. [Master Bug & Issue Tracker](#16-master-bug--issue-tracker)
17. [Pipeline Wiring Summary](#17-pipeline-wiring-summary)

---

## 1. Data Source: `data/loader.py`

| Aspect | Details |
|--------|---------|
| **File** | `data/loader.py` (203 lines) |
| **Main function** | `get_transactions_df()` → calls `load_transactions()` |
| **Source** | CSV from `config.settings.TRANSACTIONS_FILE` with `TRANSACTIONS_DELIMITER` |
| **Caching** | Module-level `_transactions_df` — loaded once, reused for all calls |
| **Key columns** | `cust_id`, `tran_date`, `dr_cr_indctor` (C/D), `tran_amt_in_ac`, `category_of_txn`, `tran_type`, `tran_partclr`, `prty_name` |
| **Secondary data** | `load_rg_salary_data(customer_id)` — reads `rg_sal_strings.csv` + `rg_income_strings.csv` |

**`load_rg_salary_data` returns**:
```python
{
  "rg_sal": {salary_amount, merchant, method, pension_flag, transaction_count, transactions, observation},
  "rg_income": {total_income, source_count, sources: [{merchant, count, total, transactions}], observation}
}
```

**Bugs / Issues**:
1. **SILENT EXCEPTION**: Lines 127-130, 198-201 — bare `except Exception: pass` swallows all errors including data corruption. At minimum should log a warning.
2. **NO VALIDATION**: No schema validation on CSV columns. If a column is renamed/missing, downstream functions crash with KeyError.

**Sample CLI Command**:
```bash
claude "In data/loader.py, add logging.warning in the except blocks instead of bare pass, and validate expected columns after loading the CSV"
```

---

## 2. `tools/analytics.py` — Banking Analytics

> **File**: `tools/analytics.py` (597 lines, 16 functions)
> **Registration**: `pipeline/core/executor.py` → `ToolExecutor.tool_map`
> **Intent Mapping**: `config/intents.py` → `INTENT_TOOL_MAP`
> **Arg Building**: `pipeline/core/planner.py` → `QueryPlanner._get_tool_args()`

---

### 2.1 `debit_total`

`debit_total(customer_id: int, months: int = 6)`

| Aspect | Details |
|--------|---------|
| **Input** | `customer_id` (int), `months` (int, default 6) |
| **Source** | `tools/analytics.py:8-41` |
| **Logic** | Filters debits (D) for customer. If `months > 0`, restricts to last N months from max transaction date. Groups by month, sums `tran_amt_in_ac`. |
| **Returns** | `{customer_id, currency, month_wise_spending: {YYYY-MM: float}, total_spending, transaction_count}` |
| **Used By** | Intent `TOTAL_SPENDING`, `FINANCIAL_OVERVIEW`, `DEBIT_ANALYSIS`. Report builder `_get_savings_block()`. `generate_customer_report()`, `generate_lender_profile()` |
| **Planner Args** | `customer_id` only — `months` always defaults to 6 (never passed from planner) |

**Code Logic**:
- Line 10: Converts `tran_date` to datetime via `pd.to_datetime`.
- Line 15-16: Uses `filtered['tran_date'].max()` as anchor; falls back to `datetime.today()` if no debits.
- Line 27: Converts to period then back to timestamp for month grouping.
- Line 29: Builds `months_list` by subtracting `DateOffset(months=i)` from the max month.

**Bugs / Issues**:
1. **BUG**: Line 29 — `months_list` uses `month_group.index.max()`, but if `month_group` is empty, this is `NaT` → crash.
2. **ISSUE**: `months` param never exposed through the planner.
3. **GOOD**: `.copy()` on line 9 avoids modifying cached DataFrame.

**Sample CLI Command**:
```bash
# Change default months from 6 to 12:
claude "In tools/analytics.py, change the default value of months parameter in debit_total from 6 to 12"

# Expose months through planner:
# 1. Add months field to ParsedIntent in schemas/intent.py
# 2. Update planner.py _get_tool_args to pass intent.months for debit_total
# 3. Update intent_parser.py prompt to extract months from user query
```

---

### 2.2 `get_total_income`

`get_total_income(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Input** | `customer_id` (int) |
| **Source** | `tools/analytics.py:44-53` |
| **Logic** | Filters credits (C) for customer, sums `tran_amt_in_ac` |
| **Returns** | `{customer_id, total_income, transaction_count, currency}` |
| **Used By** | Intent `TOTAL_INCOME`, `FINANCIAL_OVERVIEW`. Report builder `_get_savings_block()`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**:
1. **INCONSISTENCY**: `transaction_count` not cast to `int()` (numpy int). `debit_total` casts on line 36.
2. **NO TIME FILTER**: Returns ALL-TIME total income. No `months` parameter.

**Sample CLI Command**:
```bash
claude "In tools/analytics.py, add an optional months parameter to get_total_income similar to how debit_total handles it"
```

---

### 2.3 `get_spending_by_category`

`get_spending_by_category(customer_id: int, category: str = None)`

| Aspect | Details |
|--------|---------|
| **Input** | `customer_id` (int), `category` (str, optional) |
| **Source** | `tools/analytics.py:56-86` |
| **Logic** | If `category`: filters debits for that category, returns sum. If None: groups all debits by category. |
| **Returns** | With category: `{customer_id, category, category_spending, transaction_count, currency}`. Without: `{customer_id, all_categories_spending, transactions_by_category, total_spending, currency}` |
| **Used By** | Intent `SPENDING_BY_CATEGORY`, `ALL_CATEGORIES_SPENDING`, `COMPARE_CATEGORIES`. Report builder `_get_category_overview()` |

**Bugs / Issues**:
1. `transaction_count` / `transactions_by_category` — numpy ints not cast.
2. **NO TIME FILTER**: All-time spending.

---

### 2.4 `top_spending_categories`

`top_spending_categories(customer_id: int, top_n: int = 5)`

| Aspect | Details |
|--------|---------|
| **Input** | `customer_id` (int), `top_n` (int, default 5) |
| **Source** | `tools/analytics.py:89-101` |
| **Logic** | Groups debits by category, sorts descending, takes top N |
| **Returns** | `{customer_id, top_n, top_categories: {cat: float}, currency}` |
| **Used By** | Intent `TOP_CATEGORIES`, `FINANCIAL_OVERVIEW`, `DEBIT_ANALYSIS`. `generate_customer_report()`, `generate_lender_profile()` |
| **Planner Args** | `{customer_id, top_n}` — `top_n` from `intent.top_n or 5` |

**Bugs / Issues**: No time filter. Otherwise clean.

---

### 2.5 `spending_in_date_range`

`spending_in_date_range(customer_id: int, start_date: str, end_date: str)`

| Aspect | Details |
|--------|---------|
| **Input** | `customer_id` (int), `start_date` (str YYYY-MM-DD), `end_date` (str YYYY-MM-DD) |
| **Source** | `tools/analytics.py:104-124` |
| **Logic** | Filters debits where `tran_date >= start_date` and `<= end_date` |
| **Returns** | `{customer_id, start_date, end_date, total_spending, transaction_count, currency}` |
| **Used By** | Intent `SPENDING_IN_PERIOD` |

**Bugs / Issues**:
1. **POTENTIAL BUG**: Date comparison is **string-based**, not datetime-based. `debit_total` converts to datetime (line 10) but this function does not. If dates aren't `YYYY-MM-DD` strings, comparison is lexicographic and wrong.
2. `transaction_count` not cast to `int()`.

**Sample CLI Command**:
```bash
claude "In tools/analytics.py spending_in_date_range, convert tran_date to datetime before comparison, like debit_total does"
```

---

### 2.6 `list_customers`

| **Source** | `tools/analytics.py:127-134` |
|--------|---------|
| **Returns** | `{customers: [int], total_count: int}` |
| **Used By** | Intent `LIST_CUSTOMERS` |

No issues.

---

### 2.7 `list_categories`

| **Source** | `tools/analytics.py:137-144` |
|--------|---------|
| **Returns** | `{categories: [str], total_count: int}` |
| **Used By** | Intent `LIST_CATEGORIES` |

No issues.

---

### 2.8 `get_credit_statistics`

`get_credit_statistics(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:147-211` |
| **Logic** | Computes max/second-max credit, avg, median, monthly/quarterly averages |
| **Returns** | `{customer_id, max_credit: {amount, source, date, tran_type}, second_max_credit: {amount, source, date}, avg_credit, median_credit, total_credit_count, monthly_avg_amount, monthly_median_amount, monthly_avg_count, monthly_median_count, quarterly_avg_amount, currency}` |
| **Used By** | Intent `CREDIT_ANALYSIS`, `TRANSACTION_STATISTICS`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**:
1. **INCONSISTENCY with `debit_total`**: Uses string slicing `tran_date.str[:7]` instead of `pd.to_datetime`.
2. **POTENTIAL BUG**: `max_credit['date']` returns raw DataFrame value — could be Timestamp if another function converted the cached DataFrame's `tran_date` column.
3. **INCONSISTENCY**: `max_credit` has `tran_type` field but `second_max_credit` doesn't.
4. **NAMING**: Uses key `source` for `category_of_txn` while `get_debit_statistics` uses `category`.

---

### 2.9 `get_debit_statistics`

`get_debit_statistics(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:214-254` |
| **Returns** | `{customer_id, max_debit: {amount, category, date}, avg_debit, median_debit, total_debit_count, monthly_avg/median_amount/count, currency}` |
| **Used By** | Intent `DEBIT_ANALYSIS`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**: Same string-slicing date handling. Key naming inconsistency with credit statistics (`category` vs `source`). No `second_max_debit`.

---

### 2.10 `get_transaction_counts`

`get_transaction_counts(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:257-284` |
| **Returns** | `{customer_id, total_credits, total_debits, total_transactions, monthly_credit/debit_avg/median, credit_debit_ratio}` |
| **Used By** | Intent `TRANSACTION_STATISTICS`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**:
1. **UNUSED CODE**: Lines 266-267 — `cust_df_copy` with `month` column is created but never used.
2. `credit_debit_ratio` is a count ratio — could be confused with amount ratio.

---

### 2.11 `get_balance_trend`

`get_balance_trend(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:287-336` |
| **Logic** | Sorts by date, computes running balance (C positive, D negative), determines trend |
| **Returns** | `{customer_id, balance_series (last 50), monthly_balances, min/max/final_balance, trend, currency}` |
| **Used By** | Intent `BALANCE_TREND`. Report builder `_get_risk_indicators_block()`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**:
1. **IMPORTANT**: Running balance starts from zero — no opening balance. Synthetic, not real bank balance.
2. **PERFORMANCE**: `apply(lambda)` is slow. Use `np.where` instead.
3. **TREND LOGIC**: Compares first vs last monthly balance only. V-shaped recovery shows "increasing".

---

### 2.12 `detect_anomalies`

`detect_anomalies(customer_id: int, threshold_std: float = 2.0)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:339-370` |
| **Logic** | Flags transactions above mean + threshold_std * std for credits/debits separately |
| **Returns** | `{customer_id, threshold_std, credit/debit_spikes, spike counts, mean/std/threshold, currency}` |
| **Used By** | Intent `ANOMALY_DETECTION`. Report builder `_get_risk_indicators_block()`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**:
1. **SERIALIZATION**: Spike records from `.to_dict('records')` may contain numpy types.
2. **EDGE CASE**: If `std == 0`, `threshold = mean` → all amounts equal to mean become spikes.

---

### 2.13 `get_income_stability`

`get_income_stability(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:373-428` |
| **Logic** | CV of monthly income → stability score 0-100. Checks salary regularity. |
| **Returns** | `{customer_id, stability_score, coefficient_of_variation, income_sources, primary_income_source, salary_regularity, monthly_income_avg/std, currency}` |
| **Used By** | Intent `INCOME_STABILITY`. Report builder `_get_risk_indicators_block()`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**:
1. **HARDCODED CATEGORY**: Line 405 checks `category_of_txn == 'Salary'`. Case-sensitive; won't match "SALARY" or other labels.
2. **MISLEADING SCORE**: 1 month of data → std=0, CV=0, score=100. Looks perfectly stable but insufficient data.
3. **AGGRESSIVE SCORING**: CV of 0.5 gives score 50 — may be too harsh for seasonal workers.

---

### 2.14 `get_cash_flow`

`get_cash_flow(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:431-476` |
| **Logic** | Converts dates to datetime/period, groups inflows/outflows by month |
| **Returns** | `{customer_id, monthly_cash_flow: {YYYY-MM: {inflow, outflow, net}}, avg_monthly_inflow/outflow, avg_net_cash_flow, currency}` |
| **Used By** | Intent `CASH_FLOW`. Report builder `_get_savings_block()`, `_get_monthly_cashflow()`. `generate_customer_report()`, `generate_lender_profile()` |

**Bugs / Issues**: One of the few functions that properly uses `pd.to_datetime`. No major issues.

---

### 2.15 `generate_customer_report`

`generate_customer_report(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:479-494` |
| **Logic** | Calls ALL analytics sub-functions, combines into one dict |
| **Returns** | Composite dict of all metrics |
| **Used By** | Intent `CUSTOMER_REPORT` (wrapped as `_generate_customer_report_with_pdf` in executor) |

**Bugs / Issues**: Calls `get_transactions_df()` 10+ times across sub-functions. Redundant filtering.

---

### 2.16 `generate_lender_profile`

`generate_lender_profile(customer_id: int)`

| Aspect | Details |
|--------|---------|
| **Source** | `tools/analytics.py:497-597` |
| **Logic** | Computes savings_rate, risk factors, credit_score_proxy, lending_recommendation |
| **Returns** | Large dict with financial metrics, income/spending analysis, risk assessment |
| **Used By** | Intent `LENDER_PROFILE` |

**Bugs / Issues**:
1. **HIGH — CREDIT SCORE BUG**: Line 553 — positive adjustments (savings_rate * 50 + stability_score / 2) overpower risk penalties. A customer with 4 risk factors can still score 95/100. Formula: `100 - 60 + 15 + 40 = 95`.
2. **HARDCODED THRESHOLDS**: savings_rate < 0.1 flagged — conservative for many households.

**Sample CLI Command**:
```bash
claude "In tools/analytics.py generate_lender_profile, fix the credit_score calculation. Use: base=50, add min(20, savings_rate*50) for savings, add min(20, stability_score/5) for stability, subtract len(risk_factors)*10 for risks, clamp 0-100"
```

---

### 2.17 Analytics Cross-Cutting Issues

#### Date Handling Inconsistency

| Approach | Functions | Method |
|----------|-----------|--------|
| **DateTime Period** | `debit_total`, `get_cash_flow` | `pd.to_datetime()` → `.dt.to_period('M')` |
| **String Slicing** | `get_credit/debit_statistics`, `get_transaction_counts`, `get_balance_trend`, `get_income_stability` | `tran_date.str[:7]` |
| **No conversion** | `spending_in_date_range` | Raw string comparison |

**Recommendation**: Standardize to `pd.to_datetime` in all functions, or convert once in `get_transactions_df()`.

#### Numpy Type Serialization

Functions not casting to `int()`: `get_total_income`, `get_spending_by_category`, `spending_in_date_range`, `get_transaction_counts`.

#### Missing Time Filters

`get_total_income`, `get_spending_by_category`, `top_spending_categories` — all return all-time data with no `months` parameter.

---

## 3. `tools/category_resolver.py` — Category Presence Lookup

| Aspect | Details |
|--------|---------|
| **File** | `tools/category_resolver.py` (215 lines) |
| **Main function** | `category_presence_lookup(customer_id, category)` → `resolve_category_presence()` |
| **Data Source** | `get_transactions_df()` + `config/categories.yaml` via `config/category_loader.py` |
| **Registration** | `executor.py` tool_map key: `"category_presence_lookup"` |
| **Intent** | `CATEGORY_PRESENCE_LOOKUP` |
| **Planner Args** | `{customer_id, category}` |

**How It Works**:
1. Resolves user category input to canonical key via `resolve_category_alias()`
2. Loads category config from `config/categories.yaml` (keywords, category_matches, direction filter, min_count)
3. Filters customer transactions
4. Applies matching strategies in priority order:
   - **Strategy 0**: Direct `category_of_txn` column match (case-insensitive)
   - **Strategy 1**: YAML `category_matches` exact match
   - **Strategy 2**: Keyword match in narration (`tran_partclr`)
   - **Strategy 3**: Fuzzy match (fuzzywuzzy `token_set_ratio`, threshold from YAML fallback config)
5. Returns `CategoryPresenceResult` with: present/absent, total_amount, transaction_count, supporting_transactions (max 10), matched_keywords

**Returns**:
```python
{
  customer_id, category, present (bool), total_amount, transaction_count,
  supporting_transactions: [{date, amount, narration, transaction_type, direction}],
  direction_filter, matched_keywords, category_config_used
}
```

**Bugs / Issues**:
1. **PERFORMANCE**: Line 131 — `iterrows()` over entire customer DataFrame. For customers with 2000+ transactions, this is slow. Could use vectorized pandas operations for Strategy 0/1/2 and only fall back to iterrows for Strategy 3.
2. **FUZZY FALSE POSITIVES**: Strategy 3 fuzzy match with threshold 70 on `token_set_ratio` can match unrelated narrations. E.g., "RENT" could fuzzy-match "RESTAURANT" at 70+.
3. **FALLBACK CONFIG**: `get_fallback_config()` is called per-row inside the loop (line 164) — should be called once outside.
4. **GRACEFUL DEGRADATION**: If fuzzywuzzy not installed, falls back to substring check — could match too aggressively (e.g., "rent" in "current").

**Sample CLI Command**:
```bash
claude "In tools/category_resolver.py, move get_fallback_config() call outside the iterrows loop for performance, and vectorize Strategy 0 and 1 using pandas operations"
```

---

## 4. `tools/transaction_fetcher.py` — Merchant Extraction & Transaction Grouping

| Aspect | Details |
|--------|---------|
| **File** | `tools/transaction_fetcher.py` (312 lines) |
| **Main function** | `fetch_transaction_summary(customer_id)` |
| **Data Source** | `get_transactions_df()` |
| **Called By** | `customer_report_builder.py:_get_top_merchants()`, `_get_salary_block()` |
| **Not in executor tool_map** | Not a direct intent tool — called internally by report builder |

**How It Works**:
1. Loads customer transactions via `get_transactions_df()`
2. **Salary detection** (`_detect_salary`):
   - Filters credits (C) where `category_of_txn == 'SALARY'` OR `is_salary_narration()` matches
   - Requires `MIN_SALARY_COUNT = 2` occurrences
   - Returns `SalarySummary` with average_amount, frequency, narrations, count, total
3. **Transaction grouping** (`_group_similar_transactions`):
   - Separates debits and credits (excluding salary credits)
   - For each transaction: extracts recipient via `extract_recipient_name()`, falls back to `normalize_narration()[:50]`
   - Groups by fuzzy matching (`fuzz.token_set_ratio >= 70`)
   - Filters groups with `MIN_GROUP_SIZE = 3` transactions
   - Returns `HighFrequencyTransaction` list sorted by count

**Returns**:
```python
TransactionSummary {
  customer_id, salary_summary (SalarySummary | None),
  high_frequency_transactions: [HighFrequencyTransaction {
    representative_narration, similar_narrations, count, total_amount, average_amount, transaction_type
  }],
  total_transactions_analyzed
}
```

**Configuration Constants**:
- `SIMILARITY_THRESHOLD = 70` — min fuzzy match score
- `MIN_GROUP_SIZE = 3` — min transactions per group
- `MIN_SALARY_COUNT = 2` — min salary transactions to detect

**Bugs / Issues**:
1. **GROUPING ORDER DEPENDENCY**: Line 188-194 — fuzzy matching is order-dependent. The first transaction in a group becomes the `representative`, and subsequent transactions match against it. Reordering data can produce different groups.
2. **O(n*m) COMPLEXITY**: For each transaction, iterates all existing groups to find a match (line 190-194). With 1000 transactions and 100 groups, that's 100K fuzzy comparisons. Consider building a lookup or using more efficient clustering.
3. **SALARY DETECTION**: `is_salary_narration()` matches "bonus" — a one-time bonus would be grouped with salary, skewing the average.
4. **EXACT MATCH FALLBACK**: `_group_by_exact_match()` (line 253-296) groups debits and credits together but stores only the last `txn_type` seen (line 279) — if a group has mixed types, type is incorrectly set to whichever was last.
5. **NOT REGISTERED AS TOOL**: Not in executor's `tool_map`. Only accessible through report builder — can't be queried directly via chat.

**Sample CLI Command**:
```bash
# To register as a direct tool for chat queries:
claude "Add fetch_transaction_summary to the ToolExecutor.tool_map in pipeline/core/executor.py, and add a new TRANSACTION_SUMMARY intent in config/intents.py"

# To fix grouping performance:
claude "In tools/transaction_fetcher.py _fuzzy_group_transactions, consider using a hash-based pre-filter before fuzzy matching to reduce comparisons"
```

---

## 5. Merchant Extraction Deep Dive (`narration_utils.py`)

| Aspect | Details |
|--------|---------|
| **File** | `utils/narration_utils.py` (~99 lines) |
| **Functions** | `normalize_narration()`, `extract_recipient_name()`, `is_salary_narration()` |
| **Called By** | `transaction_fetcher.py`, `event_detector.py` |

### `extract_recipient_name(narration)`

**Patterns handled** (in order):

| Pattern | Regex | Example Input | Output |
|---------|-------|--------------|--------|
| UPI | `^UPI/([^/]+)/` | `UPI/RAJU KUMAR/9876@ybl/...` | `RAJU KUMAR` |
| IMPS | `^SentIMPS\d+([a-zA-Z\s]+)\s*IMPS-` | `SentIMPS123456RAJU IMPS-...` | `RAJU` |
| Salary | contains `SALARY` or `EMPLOYEE` | `EMPLOYEE SALARY FOR OCT` | `SALARY` (literal) |
| Cash Deposit | starts with `CASH DEPOSIT` | `Cash Deposit at ATM...` | `CASH_DEPOSIT` |
| Reversal | starts with `REV-` | `REV-UPI/NAME/...` | Recursive call on inner |

**Bugs / Issues**:
1. **MISSING PATTERNS**: No handling for NEFT (`NEFT/IFSC/NAME/BANK`), RTGS, cheque, or direct bank transfer narrations. `event_detector.py` has `_extract_name_from_narration()` that covers NEFT but this utility doesn't.
2. **FALSE POSITIVE**: Any narration containing "SALARY" returns literal `"SALARY"` even if it's `"SALARY ADVANCE FROM KREDITBEE"` — this is a salary advance (BNPL), not actual salary.
3. **IMPS PATTERN**: `SentIMPS\d+([a-zA-Z\s]+)\s*IMPS-` — requires "SentIMPS" prefix with digits followed by letters. If IMPS narration format varies (e.g., "IMPS-123-RAJU KUMAR"), it won't match.
4. **DUPLICATE LOGIC**: `event_detector.py:_extract_name_from_narration()` duplicates and extends this function. Should be consolidated.

### `normalize_narration(text)`

Strips digits, special chars, lowercases. Used for fuzzy comparison.

**Issue**: Removing ALL digits means "UPI/RAJU123" and "UPI/RAJU456" normalize to the same string — correct for grouping, but loses discriminating info.

### `is_salary_narration(narration)`

Keywords: `salary, employee, payroll, stipend, bonus, wages`

**Issue**: "bonus" matches as salary. A one-time festive bonus is not recurring salary.

**Sample CLI Command**:
```bash
claude "In utils/narration_utils.py extract_recipient_name, add NEFT pattern handling similar to event_detector.py _extract_name_from_narration, and exclude 'SALARY ADVANCE' from the salary match"
```

---

## 6. Top Merchants Logic (`customer_report_builder.py`)

| Aspect | Details |
|--------|---------|
| **Function** | `_get_top_merchants(customer_id)` in `pipeline/reports/customer_report_builder.py:163-183` |
| **Called By** | `build_customer_report()` (line 86), `execute_section("spending_summary")` (line 454) |
| **Uses** | `fetch_transaction_summary()` → `high_frequency_transactions[:5]` |
| **Schema** | `CustomerReport.top_merchants: Optional[List[Dict[str, Any]]]` |

**How It Works**:
1. Calls `fetch_transaction_summary(customer_id)` from `transaction_fetcher.py`
2. Takes the top 5 `high_frequency_transactions` (already sorted by count descending)
3. Maps each to: `{name, count, total, avg, type}`
4. Returns `None` if no high-frequency groups exist

**Data Flow**:
```
Raw narrations → extract_recipient_name() → normalize → fuzzy group → sort by count → top 5
```

**Bugs / Issues**:
1. **MERCHANT NAME QUALITY**: `representative_narration` is the extracted recipient name or normalized narration fallback. For UPI transactions this is clean (e.g., "RAJU KUMAR"), but for NEFT/cheques it's often garbage or missing → "Unknown" merchants in report.
2. **NO AMOUNT FILTER**: Groups with 3 tiny transactions (e.g., 3x INR 10 UPI) rank above 2 large transactions (e.g., 2x INR 50,000 rent). Consider a hybrid score: `count * avg_amount` or a minimum total threshold.
3. **MIXED DEBIT/CREDIT**: Top merchants list includes both debit merchants (spending) and credit sources (income). The `type` field distinguishes them, but the report heading "Top Merchants" is misleading for credit groups.
4. **NOT USED IN CHAT**: Top merchants are only available in the report. No direct chat query "who are my top merchants?"

**Sample CLI Command**:
```bash
# To add a minimum total threshold:
claude "In pipeline/reports/customer_report_builder.py _get_top_merchants, filter out transaction groups with total_amount < 1000 before taking top 5"

# To add a chat intent for top merchants:
claude "Add a TOP_MERCHANTS intent that calls fetch_transaction_summary and returns the top 5 merchants"
```

---

## 7. `tools/account_quality.py` — Account Classification

| Aspect | Details |
|--------|---------|
| **File** | `tools/account_quality.py` (363 lines) |
| **Main function** | `compute_account_quality(customer_id, customer_report=None)` |
| **Data Source** | `get_transactions_df()` + `load_rg_salary_data()` |
| **Called By** | `customer_report_builder.py:build_customer_report()` (line 113), `report_orchestrator.py:_aggregate_to_report()` |
| **Not in executor tool_map** | Internal function, not a direct chat tool |

**Four Patterns Detected**:

| Pattern | Logic | Score Impact |
|---------|-------|-------------|
| **Salary Conduit** | Large outflow (≥40% of salary) within 3 days of credit | -15 (1-2 months), -35 (3+ months) |
| **ATM Cash Dependency** | % of debits that are ATM withdrawals | -20 if >50% |
| **Low Activity** | Avg monthly debits < 10 despite salary | -15 |
| **No Obligations** | No EMI + no utility + no rent debits | -15 |

**Scoring**:
- Base: 50
- Bonuses: +15 EMI, +10 utility, +10 rent, +10 high activity (>20/mo), +15 no conduit
- Penalties: -35 conduit (3+mo), -15 conduit (1-2mo), -20 high ATM, -15 low activity, -15 no obligations
- Classification: ≥60 → primary, 40-59 → secondary, <40 → conduit
- Falls to "unknown" if no salary data at all

**Returns**:
```python
{
  account_type: "primary"|"secondary"|"conduit"|"unknown",
  confidence: "high"|"medium"|"low",
  primary_score: 0-100,
  conduit_events: [{salary_date, outflow_date, outflow_amount, pct_of_salary, days_after_salary, is_self_transfer, narration, tran_type}],
  conduit_months, salary_outflow_pct_3d, atm_debit_pct, avg_monthly_debits,
  has_emi_debits, has_utility_debits, has_rent_visible, has_small_ticket_txns,
  observations: [human-readable strings for LLM prompt]
}
```

**Bugs / Issues**:
1. **SELF-TRANSFER DETECTION**: Line 97-99 — uses first 6 chars of customer name to match in narration. If customer is "RAJU" (4 chars), `name_prefix` is set but `len < 6` check on line 73 means it IS used (≥3 check). However, short names like "RAJ" (3 chars) matching in narrations like "RAJESH KUMAR" would be a false positive.
2. **HARDCODED CATEGORIES**: `_SMALL_TICKET_CATS` (line 25-29) is a hardcoded set of category names. If category naming in the CSV changes, these won't match. Should reference `config/categories.yaml`.
3. **CONDUIT FALSE POSITIVE**: A customer who pays rent (40%+ of salary) within 3 days of salary credit would be flagged as conduit. Rent is a legitimate outflow, not salary pass-through.
4. **NO TIME DECAY**: A conduit event from 12 months ago counts the same as one from last month.

**Sample CLI Command**:
```bash
claude "In tools/account_quality.py _detect_conduit_events, exclude transactions whose category_of_txn is 'Rent' or 'EMI' from conduit detection, as these are legitimate obligations not salary pass-through"
```

---

## 8. `tools/event_detector.py` — Transaction Event Detection

| Aspect | Details |
|--------|---------|
| **File** | `tools/event_detector.py` (647 lines) |
| **Main function** | `detect_events(customer_id, rg_salary_data=None)` |
| **Data Source** | `get_transactions_df()` + `load_rg_salary_data()` |
| **Called By** | `customer_report_builder.py:build_customer_report()` (line 120), `report_orchestrator.py:_aggregate_to_report()` |
| **Not in executor tool_map** | Internal function, not a direct chat tool |

**Two Detection Layers**:

#### Layer 1: Keyword Rules (`KEYWORD_RULES`)

| Type | Direction | Significance | Min Months | Keywords |
|------|-----------|-------------|------------|----------|
| `pf_withdrawal` | C | high | — | EPFO, PF SETTL, PF FINAL, PROVIDENT FUND, etc. |
| `fd_closure` | C | medium | — | FD CLOSURE, FD MATURITY, PREMATURE CLOSURE, etc. |
| `salary_advance_bnpl` | C | high | — | EARLY SALARY, LAZYPAY, SIMPL, SLICE, KREDITBEE, etc. |
| `sip_investment` | D | positive | 2 | SIP, MUTUAL FUND, BSE STAR MF, etc. |
| `insurance_premium` | D | positive | 2 | LIC, HDFC LIFE, ICICI PRU, TERM INSURANCE, etc. |
| `govt_benefit` | D | medium | — | PM KISAN, MNREGA, DBT, SCHOLARSHIP, etc. |

#### Layer 2: Custom Multi-Step Detectors

| Detector | Logic | Significance |
|----------|-------|-------------|
| `_detect_self_transfer_post_salary` | ≥40% of salary self-transferred within 3 days | high |
| `_detect_post_salary_routing` | 2+ recipients within 48h of salary, each ≥8% of salary | high |
| `_detect_loan_redistribution` | Large credit from bank/NBFC → 2+ outflows within 48h | high |
| `_detect_round_trips` | Money sent and received back within 7 days (same name, ±15%) | medium |

**Returns**: List of event dicts: `{type, date, month_label, amount, significance, description}`

**Deduplication**: Same type + same month → only one event kept. "Ongoing" events → one per type.

**Bugs / Issues**:
1. **KEYWORD OVERLAP**: `salary_advance_bnpl` keywords include "KREDITBEE", "MONEYVIEW" — but these could also appear in loan repayment debits, not just credits. The direction filter (C only) handles this correctly.
2. **GOVERNMENT BENEFIT**: `govt_benefit` rule has `direction: "C"` in the code but the KEYWORD_RULES show `direction: "D"` — **this is a BUG**. Government benefits are credits (C), but the rule says debit (D). Checking source: line 128 shows `"direction": "C"` — this is actually correct in the code. The table above is wrong; the code is correct.
3. **ROUND TRIP FALSE POSITIVE**: Line 510 — matches if first 6 chars of extracted names match. "RAJESH" and "RAJENDRA" would match as same person. Too aggressive.
4. **LOAN REDISTRIBUTION THRESHOLD**: Line 361 — `max(150000, salary_amount * 2.0)`. If salary is INR 20K, threshold stays at 150K. If salary is 200K, threshold is 400K. Reasonable but might miss smaller loan disbursals for low-income customers.
5. **DEDUPLICATION BY MONTH**: Line 547 — dedup key is `(type, date[:7])`. For non-recurring events, if two PF withdrawals happen in the same month, only the first is kept. This could hide important information.
6. **GOOD ARCHITECTURE**: Adding new keyword patterns requires zero changes to intents/templates/renderers.

**Sample CLI Command**:
```bash
# To add a new keyword rule (e.g., crypto detection):
claude "In tools/event_detector.py, add a new KEYWORD_RULES entry for cryptocurrency transactions with keywords like 'WAZIRX', 'COINSWITCH', 'BINANCE', 'CRYPTO', direction 'D', significance 'medium'"

# To fix round-trip name matching:
claude "In tools/event_detector.py _detect_round_trips, increase name match from first 6 chars to full fuzz.token_set_ratio >= 80 for more accurate matching"
```

---

## 9. `tools/scorecard.py` — Risk Scorecard

| Aspect | Details |
|--------|---------|
| **File** | `tools/scorecard.py` (517 lines) |
| **Main function** | `compute_scorecard(customer_report=None, bureau_report=None, rg_salary_data=None)` |
| **Thresholds** | `config/thresholds.py` |
| **Called By** | `pdf_renderer.py`, `bureau_pdf_renderer.py`, `combined_report_renderer.py` |
| **Not in executor tool_map** | Internal function, called during PDF rendering |

**How It Works**:
1. Computes **bureau signals** (if bureau_report provided): CIBIL score, Max DPD, CC utilization, enquiry pressure, loan stacking, missed payments, adverse events, FOIR, exposure trends
2. Computes **banking signals** (if customer_report provided): Income (hierarchy: affluence_amt → rg_sal → rg_income → txn avg), red flag spending, account type
3. Determines **verdict**: RED count ≥3 or forced adverse events → HIGH RISK, ≥1 → CAUTION, else → LOW RISK
4. Derives strengths, concerns, verify items

**Threshold Constants** (from `config/thresholds.py`):

| Metric | Green | Amber | Red |
|--------|-------|-------|-----|
| DPD | 0 | 1-30 | >30 |
| CC Utilization | ≤30% | 31-75% | >75% |
| Enquiries (12M) | ≤3 | 4-10 | >10 |
| New PLs (6M) | 0 | 1 | ≥2-3 |
| Missed Payments (18M) | 0% | 1-10% | >10% |
| FOIR | ≤40% | 41-65% | >65% |
| CIBIL Score | ≥750 | 650-749 | <650 |

**Returns**:
```python
{
  verdict: "LOW RISK"|"CAUTION"|"HIGH RISK",
  verdict_rag: "green"|"amber"|"red",
  signals: [{label, value, rag, note, tooltip}],
  strengths: [up to 3 strings],
  concerns: [up to 3 strings],
  verify: [items to cross-check],
  narrative: bureau narrative text
}
```

**Bugs / Issues**:
1. **INCOME SIGNAL HIERARCHY**: Lines 287-348 — if affluence_amt is available from bureau, it takes priority. But if affluence_amt is stale or wrong, it overrides more recent banking salary data. No cross-validation.
2. **RED FLAG SPENDING**: Lines 351-372 — only checks `Digital_Betting_Gaming`, `Betting_Gaming`, `Betting`, `Gaming`. Hardcoded category names. Missing: liquor, cash advances, crypto.
3. **VERDICT SIMPLISTIC**: 3 red signals = HIGH RISK regardless of what they are. A customer with red CIBIL + red utilization + red enquiries is very different from red betting + red account_type + red income. No weighting.
4. **EXPOSURE SIGNALS**: `_exposure_signals()` only computes 12M trend, not 6M (code at line 117 returns before computing 6M). The 6M signal code appears to be missing (truncated).
5. **EMI MISMATCH**: Line 429-436 — checks `bureau_report._banking_emi_count` which is a private attribute never set anywhere. This verify item will never fire because `hasattr()` returns False.
6. **GOOD**: Tooltip generation is excellent — provides threshold context for every signal.

**Sample CLI Command**:
```bash
claude "In tools/scorecard.py _banking_signals, add red flag detection for 'Liquor_Smoke' and 'Cash_Advance' categories alongside the existing betting categories"

claude "In tools/scorecard.py _exposure_signals, add the 6M average trend signal computation after the 12M point-in-time signal"
```

---

## 10. `tools/bureau_chat.py` — Bureau Query Tools

| Aspect | Details |
|--------|---------|
| **File** | `tools/bureau_chat.py` (219 lines) |
| **Functions** | `bureau_credit_card_info`, `bureau_loan_type_info`, `bureau_delinquency_check`, `bureau_overview` |
| **Data Source** | `extract_bureau_features()`, `extract_tradeline_features()`, `aggregate_bureau_features()` |
| **Registration** | All 4 in `executor.py` tool_map |
| **Intents** | `BUREAU_CREDIT_CARDS`, `BUREAU_LOAN_COUNT`, `BUREAU_DELINQUENCY`, `BUREAU_OVERVIEW` |

### `bureau_credit_card_info(customer_id)`

Returns: has_credit_cards, count, live/closed counts, total sanctioned/outstanding, utilization %, max DPD, on_us/off_us counts, CC balance utilization from tradeline features.

### `bureau_loan_type_info(customer_id, loan_type=None)`

If loan_type given: fuzzy matches to `LoanType` enum, returns specific tradeline info. If None: returns all loan types summary.

### `bureau_delinquency_check(customer_id, loan_type=None)`

Checks delinquency across all or specific loan types. Includes DPD features from tradeline_features (max_dpd_6m_cc, max_dpd_6m_pl, pct_missed_payments_18m, etc.).

### `bureau_overview(customer_id)`

High-level summary: total/live/closed tradelines, total sanctioned/outstanding, unsecured sanctioned, max DPD, loan types present.

**Bugs / Issues**:
1. **FUZZY MATCH RISK**: `_fuzzy_match_loan_type()` line 43 — `"pl" in raw_lower` would match "apple" or "simple". Should use word boundary matching.
2. **NO ERROR HANDLING FOR MISSING BUREAU DATA**: If `extract_bureau_features()` returns empty dict (customer not in bureau data), the functions return partial results without clear "no data" indication. `bureau_overview` would show 0 tradelines.
3. **FORMATTING INCONSISTENCY**: `format_inr()` formats amounts for display but `utilization_pct` is formatted as f-string. Return format mixes display strings and raw values.

**Sample CLI Command**:
```bash
claude "In tools/bureau_chat.py _fuzzy_match_loan_type, add word boundary check to prevent 'pl' matching inside longer words like 'apple'"
```

---

## 11. `tools/bureau.py` — Bureau Report Orchestrator

| Aspect | Details |
|--------|---------|
| **File** | `tools/bureau.py` (54 lines) |
| **Main function** | `generate_bureau_report_pdf(customer_id)` |
| **Called By** | `executor.py:_generate_bureau_report_with_pdf()`, `combined_report.py` |
| **Registration** | Wrapped as `"generate_bureau_report"` in executor tool_map |

**Steps**:
1. Build bureau report (deterministic — feature extraction + aggregation)
2. Generate LLM narrative from executive inputs (fail-soft)
3. Render PDF (fail-soft)

**Returns**: `Tuple[BureauReport, pdf_path]`

**Bugs / Issues**:
1. **LAZY IMPORTS**: Lines 36, 49 — lazy imports inside function body to avoid circular imports. This is a code smell indicating tight coupling between modules.
2. **FAIL-SOFT**: Both LLM narrative and PDF rendering catch all exceptions. A completely broken report could still return with empty narrative and no PDF. Should at minimum log at ERROR level.

No major logic bugs.

---

## 12. `tools/combined_report.py` — Combined Report

| Aspect | Details |
|--------|---------|
| **File** | `tools/combined_report.py` (127 lines) |
| **Main function** | `generate_combined_report_pdf(customer_id)` |
| **Called By** | `executor.py:_generate_combined_report_with_pdf()` |
| **Registration** | Wrapped as `"generate_combined_report"` in executor tool_map |

**Steps**:
1. Generate customer report (fail-soft)
2. Generate bureau report (fail-soft)
3. Generate combined executive summary via LLM (fail-soft) — includes FOIR context and exposure timeline
4. Load RG salary data (fail-soft)
5. Render combined PDF+HTML
6. Export Excel row for batch merge

**Returns**: `Tuple[Optional[CustomerReport], Optional[BureauReport], pdf_path]`

**Bugs / Issues**:
1. **ALL FAIL-SOFT**: If both customer and bureau reports fail, the function still renders a combined PDF with no data. Should at least warn or return a meaningful error.
2. **EXCEL EXPORT SIDE EFFECT**: Line 110-124 — `generate_combined_report_pdf` has a side effect of writing an Excel file. This coupling between report generation and Excel export is unexpected. Should be decoupled.
3. **HARDCODED OUTPUT DIR**: `_EXCEL_OUTPUT_DIR` on line 20-23 — uses relative path from file location. Could break if file is moved.

**Sample CLI Command**:
```bash
claude "In tools/combined_report.py, decouple Excel export from generate_combined_report_pdf — move the export call to the caller (batch_reports.py or executor.py) instead"
```

---

## 13. `tools/excel_exporter.py` — Excel Export

| Aspect | Details |
|--------|---------|
| **File** | `tools/excel_exporter.py` (335 lines) |
| **Functions** | `build_excel_row()`, `export_row_to_excel()`, `merge_excel_reports()` |
| **Called By** | `combined_report.py` (per-customer), `batch_reports.py` (merge) |
| **Not in executor tool_map** | Internal utility |

**Template Columns** (20 columns matching `crn_report_template.csv`):
CRN, offer Amt, Salary Value & Company, Assessment Strength & Quality, Relationship, Event Detector, Summary, Bureau Brief, Banking Brief, Bu & Banking Segment, Max DPD & Product, CC Util, Enquiries, Payments Missed in l 18M, Foir, Exposure Commentary, TU Score, Transaction Red flag, Concerns, Intelligent Report

**How `build_excel_row()` Maps Data**:

| Column | Source | Notes |
|--------|--------|-------|
| CRN | customer_id | Direct |
| offer Amt | None | Manual fill placeholder |
| Salary Value & Company | rg_sal → salary_amount + merchant | Falls back to customer_report.salary |
| Assessment Strength & Quality | None | Manual fill placeholder |
| Relationship | rg_sal.method + pension_flag | "Pension SAL" or "Corp SAL" |
| Event Detector | customer_report.events | Formatted as "month: description" |
| Summary | combined_summary | LLM-generated |
| Bureau Brief | bureau_report.narrative | LLM-generated |
| Banking Brief | customer_report.customer_review | LLM-generated |
| Bu & Banking Segment | tradeline_features.customer_segment + account_quality.account_type | e.g., "Thick & Primary" |
| Max DPD & Product | executive_inputs.max_dpd + loan_type + months_ago | e.g., "30d DPD / PL / 3M ago" |
| CC Util | tradeline_features.cc_balance_utilization_pct | Rounded to 2 decimal |
| Enquiries | tradeline_features.unsecured_enquiries_12m | Raw int |
| Payments Missed | tradeline_features.pct_missed_payments_18m | Rounded to 2 decimal |
| Foir | tradeline_features.foir + foir_unsec | e.g., "45.2% / Unsec: 30.1%" |
| Exposure Commentary | exposure_summary | LLM-generated |
| TU Score | executive_inputs.tu_score | Raw int |
| Transaction Red flag | category_overview["Digital_Betting_Gaming"] | Amount or None |
| Concerns | bureau key_findings (high/moderate risk) | Pipe-separated |
| Intelligent Report | HTML path (from pdf_path) | .pdf → .html |

**Bugs / Issues**:
1. **TYPO IN COLUMN NAME**: "Banking Breif" (line 40) — should be "Brief". This matches the template so can't be changed without template update.
2. **TYPO IN COLUMN NAME**: "Assesement" (line 35) — should be "Assessment". Same template dependency.
3. **RED FLAG INCOMPLETE**: Line 247-249 — only checks `Digital_Betting_Gaming`. Scorecard checks 4 variants (`Betting_Gaming`, `Betting`, `Gaming`). Inconsistent.
4. **SALARY COMPANY EXTRACTION**: Line 108 — `narration.split()[0].title()` takes first word of salary narration as company name. "EMPLOYEE SALARY FOR OCT 2025" → company = "Employee". Incorrect.
5. **MERGE READS ALL FILES**: `merge_excel_reports()` reads all .xlsx files in directory with `pd.read_excel()`. If directory has non-template Excel files, merge will fail or produce garbage.

**Sample CLI Command**:
```bash
claude "In tools/excel_exporter.py build_excel_row, fix the salary company extraction on line 108. Instead of splitting first word, try to extract the employer name from the narration more intelligently, or leave it as None if no rg_sal data"
```

---

## 14. `tools/__init__.py` — Tool Registry Exports

| Aspect | Details |
|--------|---------|
| **File** | `tools/__init__.py` (16 lines) |

**Exports**:
- Individual functions: `debit_total`, `get_spending_by_category`, `top_spending_categories`, `spending_in_date_range`, `get_total_income`, `list_customers`, `list_categories`
- Full module: `analytics`
- Category resolver: `category_presence_lookup`

**Bugs / Issues**:
1. **INCOMPLETE EXPORTS**: Newer functions (`get_credit_statistics`, `get_debit_statistics`, `get_transaction_counts`, `get_balance_trend`, `detect_anomalies`, `get_income_stability`, `get_cash_flow`, `generate_customer_report`, `generate_lender_profile`) are not individually exported. They're accessed via `from tools import analytics` then `analytics.function_name`. Not a bug but inconsistent.
2. **MISSING TOOLS**: `transaction_fetcher`, `account_quality`, `event_detector`, `scorecard`, `bureau_chat`, `bureau`, `combined_report`, `excel_exporter` are not exported from `__init__.py`. They're imported directly where needed.

---

## 15. GroupBy / Aggregation Sanity Check

### Month-wise Grouping Approaches

| Approach | Files Using | Method |
|----------|------------|--------|
| **DateTime Period** | `analytics.debit_total`, `analytics.get_cash_flow`, `account_quality.py`, `event_detector.py` | `pd.to_datetime()` → `.dt.to_period('M')` |
| **String Slicing** | `analytics.get_credit/debit_statistics`, `analytics.get_transaction_counts`, `analytics.get_balance_trend`, `analytics.get_income_stability` | `tran_date.str[:7]` |
| **No conversion** | `analytics.spending_in_date_range` | Raw string comparison |

**RISK**: If one function converts `tran_date` to datetime on the **cached** DataFrame (without `.copy()`), subsequent functions using string slicing will crash because datetime objects don't have `.str` accessor.

**Actual behavior**: `debit_total` (line 9) does `.copy()` before converting — safe. `get_cash_flow` (line 434) also uses `.copy()` — safe. `account_quality.py` (line 264) uses `.copy()` — safe. `event_detector.py` (line 600) uses `.copy()` — safe. So the cache is protected, but the inconsistency remains fragile.

### Amount Aggregation Consistency

All tools consistently use:
- `tran_amt_in_ac` for amounts — correct
- `dr_cr_indctor == 'C'` for credits, `== 'D'` for debits — correct
- No mixing of credit/debit in aggregations — correct

### Category Aggregation

- Category values come directly from CSV `category_of_txn` column
- No normalization at data load time
- Planner normalizes user input via `normalize_category()` but raw data stays as-is
- If CSV has "Food" and "food" as separate values, they'd be treated as different categories

---

## 16. Master Bug & Issue Tracker

### HIGH Severity

| # | File | Issue |
|---|------|-------|
| H1 | `analytics.py:553` | Credit score formula in `generate_lender_profile` — positive adjustments overpower risk penalties. 4 risk factors → score 95. |
| H2 | `analytics.py` (10+ functions) | Date handling inconsistency — 3 different approaches across functions. Risk of silent wrong results. |
| H3 | `analytics.py:29` | `debit_total` — `month_group.index.max()` crashes (NaT) if month_group is empty. |
| H4 | `scorecard.py:117` | `_exposure_signals` — 6M trend signal code missing/truncated. Only 12M computed. |
| H5 | `scorecard.py:429` | EMI mismatch verify — checks `_banking_emi_count` which is never set. Dead code. |

### MEDIUM Severity

| # | File | Issue |
|---|------|-------|
| M1 | `analytics.py` (4 functions) | `transaction_count` not cast to `int()` — numpy serialization risk |
| M2 | `analytics.py` (3 functions) | No time-filtering on `get_total_income`, `get_spending_by_category`, `top_spending_categories` |
| M3 | `category_resolver.py:131` | `iterrows()` on full customer DataFrame — slow for large datasets |
| M4 | `category_resolver.py:164` | `get_fallback_config()` called per-row inside loop |
| M5 | `transaction_fetcher.py:188-194` | O(n*m) fuzzy matching complexity |
| M6 | `narration_utils.py:67-68` | `extract_recipient_name` — "SALARY ADVANCE" matches as salary |
| M7 | `account_quality.py` | Conduit detection doesn't exclude rent/EMI — legitimate obligations flagged |
| M8 | `event_detector.py:510` | Round-trip name matching too aggressive — first 6 chars only |
| M9 | `scorecard.py:351-372` | Red flag detection only checks betting — misses liquor, crypto, cash advances |
| M10 | `excel_exporter.py:108` | Salary company extraction takes first word of narration — wrong |
| M11 | `excel_exporter.py:247-249` | Red flag only checks `Digital_Betting_Gaming` — inconsistent with scorecard |
| M12 | `bureau_chat.py:43` | `_fuzzy_match_loan_type` — "pl" matches inside longer words |
| M13 | `combined_report.py:110-124` | Excel export side effect in report generation |

### LOW Severity

| # | File | Issue |
|---|------|-------|
| L1 | `analytics.py` | `max_credit.source` vs `max_debit.category` naming inconsistency |
| L2 | `analytics.py` | `max_credit` has `tran_type` but `second_max_credit` doesn't |
| L3 | `analytics.py:266-267` | Unused `cust_df_copy` variable in `get_transaction_counts` |
| L4 | `analytics.py:405` | Hardcoded `'Salary'` category in `get_income_stability` |
| L5 | `analytics.py:305-308` | `apply(lambda)` is slow — use `np.where` |
| L6 | `narration_utils.py` | Missing NEFT/RTGS patterns (covered in event_detector but not in utility) |
| L7 | `narration_utils.py:96` | `is_salary_narration` matches "bonus" as salary |
| L8 | `data/loader.py:127-130` | Bare `except: pass` swallows errors silently |
| L9 | `bureau.py` | Lazy imports inside functions — circular dependency smell |
| L10 | `excel_exporter.py:35,40` | Typos in column names ("Assesement", "Breif") — template-dependent |
| L11 | `tools/__init__.py` | Newer analytics functions not individually exported |

---

## 17. Pipeline Wiring Summary

### Tool Registration (executor.py → tool_map)

| Tool Key | Function | Wrapper? |
|----------|----------|----------|
| `debit_total` | `analytics.debit_total` | No |
| `get_total_income` | `analytics.get_total_income` | No |
| `get_spending_by_category` | `analytics.get_spending_by_category` | No |
| `top_spending_categories` | `analytics.top_spending_categories` | No |
| `spending_in_date_range` | `analytics.spending_in_date_range` | No |
| `list_customers` | `analytics.list_customers` | No |
| `list_categories` | `analytics.list_categories` | No |
| `get_credit_statistics` | `analytics.get_credit_statistics` | No |
| `get_debit_statistics` | `analytics.get_debit_statistics` | No |
| `get_transaction_counts` | `analytics.get_transaction_counts` | No |
| `get_balance_trend` | `analytics.get_balance_trend` | No |
| `detect_anomalies` | `analytics.detect_anomalies` | No |
| `get_income_stability` | `analytics.get_income_stability` | No |
| `get_cash_flow` | `analytics.get_cash_flow` | No |
| `generate_customer_report` | `_generate_customer_report_with_pdf` | **Yes** — wraps report orchestrator |
| `generate_lender_profile` | `analytics.generate_lender_profile` | No |
| `generate_bureau_report` | `_generate_bureau_report_with_pdf` | **Yes** — wraps bureau tool |
| `generate_combined_report` | `_generate_combined_report_with_pdf` | **Yes** — wraps combined tool |
| `bureau_credit_card_info` | `bureau_chat.bureau_credit_card_info` | No |
| `bureau_loan_type_info` | `bureau_chat.bureau_loan_type_info` | No |
| `bureau_delinquency_check` | `bureau_chat.bureau_delinquency_check` | No |
| `bureau_overview` | `bureau_chat.bureau_overview` | No |
| `category_presence_lookup` | `category_resolver.category_presence_lookup` | No |

### Internal-Only Functions (NOT in tool_map)

| Function | File | Called By |
|----------|------|-----------|
| `fetch_transaction_summary` | `transaction_fetcher.py` | `customer_report_builder.py` |
| `compute_account_quality` | `account_quality.py` | `customer_report_builder.py`, `report_orchestrator.py` |
| `detect_events` | `event_detector.py` | `customer_report_builder.py`, `report_orchestrator.py` |
| `compute_scorecard` | `scorecard.py` | `pdf_renderer.py`, `bureau_pdf_renderer.py`, `combined_report_renderer.py` |
| `build_excel_row` | `excel_exporter.py` | `combined_report.py` |

### Full Call Chain Diagram

```
User Chat Query
├─ IntentParser → ParsedIntent
├─ QueryPlanner → execution plan [{tool, args}]
├─ ToolExecutor.execute(plan) → ToolResult[]
│  ├─ analytics.* (direct calls)
│  ├─ bureau_chat.* (direct calls)
│  └─ category_presence_lookup (direct call)
└─ ResponseExplainer → narrated response

Report Generation (generate_customer_report / generate_combined_report)
├─ build_customer_report()
│  ├─ _get_category_overview() → get_spending_by_category()
│  ├─ _get_top_merchants() → fetch_transaction_summary()
│  │  ├─ _detect_salary() → is_salary_narration()
│  │  └─ _group_similar_transactions() → extract_recipient_name() + fuzzy match
│  ├─ _get_monthly_cashflow() → get_cash_flow()
│  ├─ _get_salary_block() → fetch_transaction_summary()
│  ├─ _get_emi_block() → resolve_category_presence("emi")
│  ├─ _get_rent_block() → resolve_category_presence("rent")
│  ├─ _get_bills_block() → resolve_category_presence("utilities")
│  ├─ _get_savings_block() → get_total_income(), debit_total(), get_cash_flow()
│  └─ _get_risk_indicators_block() → detect_anomalies(), get_income_stability(), get_balance_trend()
├─ compute_account_quality() → conduit/ATM/activity/obligation detection
├─ detect_events() → keyword rules + multi-step detectors
├─ generate_customer_review() [LLM]
└─ render_report_pdf()
   └─ compute_scorecard() → bureau signals + banking signals → verdict
```
