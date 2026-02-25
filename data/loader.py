"""
Data loading and management module.
Handles all data access in one place.
"""

import pandas as pd
from typing import Optional, Dict, Any

from config.settings import (
    TRANSACTIONS_FILE, TRANSACTIONS_DELIMITER,
    RG_SAL_FILE, RG_SAL_DELIMITER,
    RG_INCOME_FILE, RG_INCOME_DELIMITER,
)

# Module-level cache for the dataframe
_transactions_df: Optional[pd.DataFrame] = None


def load_transactions(force_reload: bool = False) -> pd.DataFrame:
    """
    Load transaction data from CSV.

    Args:
        force_reload: If True, reload from disk even if cached

    Returns:
        DataFrame with transaction data
    """
    global _transactions_df

    if _transactions_df is None or force_reload:
        _transactions_df = pd.read_csv(TRANSACTIONS_FILE, sep=TRANSACTIONS_DELIMITER)
        print(f"Loaded {len(_transactions_df)} transactions from {TRANSACTIONS_FILE}")

    return _transactions_df


def get_transactions_df() -> pd.DataFrame:
    """
    Get the transactions DataFrame (loads if not already loaded).

    This is the main function tools should use to access data.
    """
    return load_transactions()


def get_data_summary() -> str:
    """
    Generate a summary of the transaction data.

    Returns:
        String with data statistics
    """
    df = get_transactions_df()

    total_credits = df[df['dr_cr_indctor'] == 'C']['tran_amt_in_ac'].sum()
    total_debits = df[df['dr_cr_indctor'] == 'D']['tran_amt_in_ac'].sum()

    summary = f"""
Transaction Data Summary
========================
Total Records: {len(df)}
Unique Customers: {df['cust_id'].nunique()}
Date Range: {df['tran_date'].min()} to {df['tran_date'].max()}

Transaction Types: {df['tran_type'].unique().tolist()}
Categories: {df['category_of_txn'].unique().tolist()}

Total Credits (Income): ${total_credits:,.2f}
Total Debits (Expenses): ${total_debits:,.2f}
"""
    return summary


def load_rg_salary_data(customer_id: int) -> Dict[str, Any]:
    """
    Load internal salary algorithm outputs for a customer.

    Reads rg_sal_strings.csv (primary salary) and rg_income_strings.csv
    (multi-source total income) and returns structured data for template rendering.

    Args:
        customer_id: Customer identifier (CRN)

    Returns:
        Dict with optional 'rg_sal' and 'rg_income' sub-dicts.
        Returns {} if both files are missing or customer has no data.
    """
    result: Dict[str, Any] = {}

    # --- Primary salary (rg_sal) ---
    try:
        sal_df = pd.read_csv(RG_SAL_FILE, sep=RG_SAL_DELIMITER, index_col=False)
        cust_sal = sal_df[sal_df['crn'] == customer_id].copy()

        if len(cust_sal) > 0:
            salary_amount = float(cust_sal['rg_sal'].iloc[0])
            merchant = str(cust_sal['merchant'].iloc[0]).title()
            method = str(cust_sal['chosen_method'].iloc[0])
            pension_flag = int(cust_sal['pension_pay_flag'].iloc[0])

            cust_sal_sorted = cust_sal.sort_values('tran_date', ascending=False)
            transactions = [
                {
                    'date': str(row['tran_date']),
                    'narration': str(row['tran_partclr']),
                    'amount': float(row['tran_amt_in_ac']),
                }
                for _, row in cust_sal_sorted.iterrows()
            ]

            n = len(transactions)
            observation = (
                f"Estimated monthly salary of INR {salary_amount:,.0f} from {merchant}, "
                f"identified across {n} month{'s' if n != 1 else ''}."
            )

            result['rg_sal'] = {
                'salary_amount': salary_amount,
                'merchant': merchant,
                'method': method,
                'pension_flag': pension_flag,
                'transaction_count': n,
                'transactions': transactions,
                'observation': observation,
            }
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # --- Total income across all sources (rg_income) ---
    try:
        inc_df = pd.read_csv(RG_INCOME_FILE, sep=RG_INCOME_DELIMITER, index_col=False)
        cust_inc = inc_df[inc_df['crn'] == customer_id].copy()

        if len(cust_inc) > 0:
            total_income = float(cust_inc['rg_income'].iloc[0])

            merchant_groups = (
                cust_inc.groupby('merchant')
                .agg(count=('tran_amt_in_ac', 'count'), total=('tran_amt_in_ac', 'sum'))
                .reset_index()
                .sort_values('total', ascending=False)
            )
            sources = []
            for _, row in merchant_groups.iterrows():
                merchant_name = str(row['merchant']).title()
                merchant_txns = (
                    cust_inc[cust_inc['merchant'] == row['merchant']]
                    .sort_values('tran_date', ascending=False)
                    .head(3)
                )
                txn_list = [
                    {
                        'date': str(t['tran_date']),
                        'narration': str(t['tran_partclr']),
                        'amount': float(t['tran_amt_in_ac']),
                    }
                    for _, t in merchant_txns.iterrows()
                ]
                sources.append({
                    'merchant': merchant_name,
                    'count': int(row['count']),
                    'total': float(row['total']),
                    'transactions': txn_list,
                })
            source_count = len(sources)

            rg_sal_amount = result.get('rg_sal', {}).get('salary_amount')
            if rg_sal_amount and source_count > 1:
                secondary_income = total_income - rg_sal_amount
                primary_merchant = result['rg_sal']['merchant']
                other_merchants = [
                    s['merchant'] for s in sources
                    if s['merchant'].lower() != primary_merchant.lower()
                ]
                other_str = ', '.join(other_merchants[:2])
                observation = (
                    f"Total estimated monthly income of INR {total_income:,.0f} from "
                    f"{source_count} source{'s' if source_count != 1 else ''}. "
                    f"Primary salary from {primary_merchant} accounts for INR {rg_sal_amount:,.0f}; "
                    f"remaining INR {secondary_income:,.0f} from secondary "
                    f"source{'s' if len(other_merchants) != 1 else ''} ({other_str})."
                )
            else:
                observation = (
                    f"Total estimated monthly income of INR {total_income:,.0f} from "
                    f"{source_count} contributing source{'s' if source_count != 1 else ''}."
                )

            result['rg_income'] = {
                'total_income': total_income,
                'source_count': source_count,
                'sources': sources,
                'observation': observation,
            }
    except FileNotFoundError:
        pass
    except Exception:
        pass

    return result
