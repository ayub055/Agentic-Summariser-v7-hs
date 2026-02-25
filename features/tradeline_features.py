"""Pre-computed tradeline-level features from tl_features.csv.

These are customer-level aggregate features (NOT per-loan-type).
They represent behavioral and risk signals computed upstream.
All values are pre-computed — no derivation happens here.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TradelineFeatures:
    """Customer-level pre-computed tradeline features.

    Grouped into 6 logical categories for display and narration.
    NULL values from CSV are represented as None.
    """

    # --- Loan Activity ---
    months_since_last_trade_pl: Optional[float] = None       # monsnclasttrop_pl_onc
    months_since_last_trade_uns: Optional[float] = None      # monsnclasttrop_uns_onc
    new_trades_6m_pl: Optional[int] = None                   # no_tr_open_l6m_pl_onc
    total_trades: Optional[int] = None                       # no_trades_all_onc

    # --- DPD & Delinquency ---
    max_dpd_6m_cc: Optional[int] = None                      # max_dpd_l6m_cc_onc
    max_dpd_6m_pl: Optional[int] = None                      # max_dpd_l6m_pl_onc
    max_dpd_9m_cc: Optional[int] = None                      # max_dpd_l9m_cc_onc
    months_since_last_0p_uns: Optional[float] = None         # mon_sin_last_0p_uns_op
    months_since_last_0p_pl: Optional[float] = None          # monsinlast_0p_pl_onc

    # --- Payment Behavior ---
    pct_0plus_24m_all: Optional[float] = None                # pct_0p_l24m_all_onc
    pct_0plus_24m_pl: Optional[float] = None                 # pct_0p_l24m_pl_onc
    pct_missed_payments_18m: Optional[float] = None          # pct_missed_pymt_last18m_all
    pct_trades_0plus_12m: Optional[float] = None             # pct_tr_0p_l12m_all_onc
    ratio_good_closed_pl: Optional[float] = None             # ratio_good_closed_loans_pl

    # --- Utilization ---
    cc_balance_utilization_pct: Optional[float] = None       # pct_bal_cc_lv
    pl_balance_remaining_pct: Optional[float] = None         # pct_bal_pl_lv

    # --- Enquiry Behavior ---
    unsecured_enquiries_12m: Optional[int] = None            # uns_enq_l12m
    trade_to_enquiry_ratio_uns_24m: Optional[float] = None   # tr_to_enq_ratio_uns_l24m

    # --- Customer Profile ---
    ktk_rel: Optional[str] = None                            # ktk_rel
    customer_segment: Optional[str] = None                   # customer_segment_1_ordered
    bank_grp: Optional[str] = None                           # bank_grp
    bu_grp: Optional[str] = None                             # bu_grp
    affluence_amt: Optional[float] = None                    # affluence_amt_6
    income_source: Optional[str] = None                      # income_source_new
    node: Optional[str] = None                               # node

    # --- Loan Acquisition Velocity ---
    interpurchase_time_12m_plbl: Optional[float] = None      # interpurchase_time_l12m_plbl
    interpurchase_time_6m_plbl: Optional[float] = None       # interpurchase_time_l6m_plbl
    interpurchase_time_24m_all: Optional[float] = None       # interpurchase_time_l24m_all
    interpurchase_time_9m_hl_lap: Optional[float] = None     # interpurchase_time_l9m_hl_lap
    interpurchase_time_24m_hl_lap: Optional[float] = None    # interpurchase_time_l24m_hl_lap
    interpurchase_time_24m_twl: Optional[float] = None       # interpurchase_time_l24m_twl
    interpurchase_time_12m_cl: Optional[float] = None        # interpurchase_time_l12m_cl
