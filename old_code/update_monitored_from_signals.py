#!/usr/bin/env python3
"""
Update monitored trades from Trendline and Distance signals.
For each monitored trade, compute the dedup key (Function|Symbol|Signal_Date|Signal_Type|Interval).
Search for that key in the latest Trendline and Distance CSVs; if found, update the monitored
trade row with the latest data from the source (Current_MTM, Win_Rate, Strategy_CAGR, etc.).
Run after update_trade.sh so Trendline/Distance CSVs are current.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pandas as pd
from config import TRADE_DEDUP_COLUMNS, INDIA_DATA_DIR, DATA_FILES
from utils.data_loader import get_latest_dated_file_path
from utils.helpers import (
    parse_symbol_signal_info,
    parse_interval_info,
    parse_win_rate_info,
    parse_exit_signal_info,
)


MONITORED_CSV = os.path.join(SCRIPT_DIR, "trade_store", "INDIA", "monitored_trades.csv")


def build_dedup_key(record):
    """Build dedup key from record dict (same logic as get_trade_dedup_key)."""
    parts = []
    for col in TRADE_DEDUP_COLUMNS:
        val = str(record.get(col, "") or "").strip()
        if col == "Signal_Type":
            val = "SHORT" if "SHORT" in val.upper() else "LONG"
        parts.append(val)
    return "|".join(parts)


# Column indices for Trendline vs Distance (from cards.py)
TRENDLINE_COLS = {
    "cagr": 18,
    "sharpe": 21,
    "holding": 16,
    "targets": 23,
    "returns": 14,
}
DISTANCE_COLS = {
    "cagr": 12,
    "sharpe": 15,
    "holding": 10,
    "targets": 17,
    "returns": 8,
}


def row_to_key_and_update(row, function_name):
    """From a Trendline or Distance CSV row, build dedup key and update dict for monitored trade."""
    if len(row) == 0:
        return None, None
    symbol_signal_info = str(row.iloc[0]) if len(row) > 0 else ""
    symbol, signal_type, signal_date, signal_price = parse_symbol_signal_info(symbol_signal_info)
    interval_info = str(row.iloc[4]) if len(row) > 4 else ""
    interval_display = parse_interval_info(interval_info)
    key = build_dedup_key({
        "Function": function_name,
        "Symbol": symbol,
        "Signal_Date": signal_date,
        "Signal_Type": signal_type,
        "Interval": interval_display,
    })

    cols = TRENDLINE_COLS if function_name == "Trendline" else DISTANCE_COLS
    win_rate_info = str(row.iloc[3]) if len(row) > 3 else ""
    win_rate_display = parse_win_rate_info(win_rate_info)
    try:
        win_rate_num = float(win_rate_display.rstrip("%")) if win_rate_display != "N/A" else None
    except (ValueError, AttributeError):
        win_rate_num = None

    current_mtm = str(row.iloc[2]) if len(row) > 2 else "N/A"
    if current_mtm == "nan":
        current_mtm = "N/A"

    exit_date, exit_price = None, None
    if len(row) > 1:
        exit_date, exit_price = parse_exit_signal_info(row.iloc[1])

    strategy_cagr = "N/A"
    if len(row) > cols["cagr"] and str(row.iloc[cols["cagr"]]) != "nan":
        try:
            strategy_cagr = f"{float(str(row.iloc[cols['cagr']]).strip('%')):.2f}%"
        except (ValueError, TypeError):
            pass
    strategy_sharpe = "N/A"
    if len(row) > cols["sharpe"] and str(row.iloc[cols["sharpe"]]) != "nan":
        try:
            strategy_sharpe = f"{float(row.iloc[cols['sharpe']]):.2f}"
        except (ValueError, TypeError):
            pass
    holding_period = str(row.iloc[cols["holding"]]) if len(row) > cols["holding"] else "N/A"
    if holding_period == "nan":
        holding_period = "N/A"
    targets = str(row.iloc[cols["targets"]]) if len(row) > cols["targets"] else "N/A"
    if targets == "nan":
        targets = "N/A"
    backtested_returns = str(row.iloc[cols["returns"]]) if len(row) > cols["returns"] else "N/A"
    if backtested_returns == "nan":
        backtested_returns = "N/A"

    try:
        numeric_signal_price = float(signal_price) if signal_price and signal_price != "N/A" else None
    except (ValueError, TypeError):
        numeric_signal_price = None
    numeric_signal_open = None
    if len(row) > 0:
        try:
            raw = row.iloc[-1]
            if raw is not None and str(raw).strip() not in ("", "nan"):
                numeric_signal_open = float(str(raw).strip())
        except (ValueError, TypeError):
            pass

    update = {
        "Symbol": symbol,
        "Signal_Type": signal_type,
        "Signal_Date": signal_date,
        "Signal_Price": numeric_signal_price,
        "Signal_Open_Price": numeric_signal_open,
        "Win_Rate": win_rate_num,
        "Win_Rate_Display": win_rate_display,
        "Current_MTM": current_mtm,
        "Strategy_CAGR": strategy_cagr,
        "Strategy_Sharpe": strategy_sharpe,
        "Backtested_Returns": backtested_returns,
        "Targets": targets,
        "Holding_Period": holding_period,
        "Function": function_name,
        "Interval": interval_display,
        "Exit_Price": exit_price,
        "Exit_Date": exit_date,
        "Raw_Data": row.to_dict() if hasattr(row, "to_dict") else {},
    }
    if "PE_Ratio" in row.index and pd.notna(row.get("PE_Ratio")):
        update["PE_Ratio"] = row.get("PE_Ratio")
        update["Industry_PE"] = row.get("Industry_PE")
        update["Last_Quarter_Profit"] = row.get("Last_Quarter_Profit")
        update["Last_Year_Same_Quarter_Profit"] = row.get("Last_Year_Same_Quarter_Profit")
    if function_name == "Trendline" and len(row) > 13:
        tp = str(row.iloc[13])
        if tp != "nan":
            update["trendpulse_start_end"] = tp
    return key, update


def load_source_rows(file_path, function_name):
    """Load CSV and return dict key -> update for each row."""
    if not file_path or not os.path.isfile(file_path):
        return {}
    try:
        df = pd.read_csv(file_path, sep=",", quotechar='"', encoding="utf-8")
    except Exception:
        return {}
    out = {}
    for _, row in df.iterrows():
        key, update = row_to_key_and_update(row, function_name)
        if key:
            out[key] = update
    return out


def main():
    os.chdir(SCRIPT_DIR)
    print("🔄 Updating monitored trades from Trendline and Distance signals...")

    if not os.path.isfile(MONITORED_CSV):
        print("   ⚠️  monitored_trades.csv not found")
        return

    try:
        mon_df = pd.read_csv(MONITORED_CSV)
    except pd.errors.EmptyDataError:
        print("   ⚠️  monitored_trades.csv is empty")
        return
    if mon_df.empty or len(mon_df.columns) == 0:
        print("   ⚠️  No monitored trades")
        return

    trend_path = get_latest_dated_file_path(INDIA_DATA_DIR, DATA_FILES["trends_suffix"])
    dist_path = get_latest_dated_file_path(INDIA_DATA_DIR, DATA_FILES["distance_suffix"])
    updates_by_key = {}
    if trend_path:
        updates_by_key.update(load_source_rows(trend_path, "Trendline"))
    if dist_path:
        updates_by_key.update(load_source_rows(dist_path, "Distance"))

    updated_count = 0
    for i in range(len(mon_df)):
        row = mon_df.iloc[i]
        key = build_dedup_key({
            "Function": row.get("Function", ""),
            "Symbol": row.get("Symbol", ""),
            "Signal_Date": row.get("Signal_Date", ""),
            "Signal_Type": row.get("Signal_Type", ""),
            "Interval": row.get("Interval", ""),
        })
        if key not in updates_by_key:
            continue
        u = updates_by_key[key]
        for col, val in u.items():
            if col in mon_df.columns:
                mon_df.at[mon_df.index[i], col] = val
        updated_count += 1
        print(f"   ✅ Updated: {row.get('Symbol', '?')} | {row.get('Function', '?')} | {row.get('Signal_Date', '?')}")

    if updated_count > 0:
        mon_df.to_csv(MONITORED_CSV, index=False)
        print(f"✅ Monitored trades updated: {updated_count} row(s) synced from Trendline/Distance.")
    else:
        print("   No monitored trades matched Trendline or Distance rows (no updates).")


if __name__ == "__main__":
    main()
