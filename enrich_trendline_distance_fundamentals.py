#!/usr/bin/env python3
"""
Add PE_Ratio, Industry_PE, Last_Quarter_Profit, Last_Year_Same_Quarter_Profit
to the latest Trendline and Distance CSVs in trade_store/INDIA.
Run after update_trade.sh so strategy cards can show these columns from the CSV.
"""

import os
import sys

# Run from project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pandas as pd
from utils.data_loader import get_latest_dated_file_path
from config import INDIA_DATA_DIR, DATA_FILES
from page_functions.monitored_signals import fetch_additional_stock_data


def symbol_from_first_column(cell):
    """Extract symbol from first column value (e.g. 'AAPL, Long, 2026-02-06 (Price: 150)')."""
    if cell is None or (hasattr(cell, 'isna') and pd.isna(cell)):
        return ""
    s = str(cell).strip()
    if not s or s == "nan":
        return ""
    if ", " in s:
        return s.split(", ")[0].strip('"').strip()
    return s.strip('"').strip()


def enrich_csv_with_fundamentals(file_path):
    """Add PE_Ratio, Industry_PE, Last_Quarter_Profit, Last_Year_Same_Quarter_Profit to CSV. Returns (rows_updated, error_message)."""
    if not file_path or not os.path.isfile(file_path):
        return 0, "File not found"
    try:
        df = pd.read_csv(file_path, sep=",", quotechar='"', encoding="utf-8")
    except Exception as e:
        return 0, str(e)
    if df.empty:
        return 0, None
    # First column (index 0) has symbol
    updated = 0
    pe_list, ind_pe_list, lq_list, ly_list = [], [], [], []
    for i, row in df.iterrows():
        sym = symbol_from_first_column(row.iloc[0])
        if not sym:
            pe_list.append("")
            ind_pe_list.append("")
            lq_list.append("")
            ly_list.append("")
            continue
        try:
            data = fetch_additional_stock_data(sym)
            pe_list.append(data.get("PE_Ratio", "No Data"))
            ind_pe_list.append(data.get("Industry_PE", "No Data"))
            lq_list.append(data.get("Last_Quarter_Profit", "No Data"))
            ly_list.append(data.get("Last_Year_Same_Quarter_Profit", "No Data"))
            updated += 1
        except Exception:
            pe_list.append("No Data")
            ind_pe_list.append("No Data")
            lq_list.append("No Data")
            ly_list.append("No Data")
    df["PE_Ratio"] = pe_list
    df["Industry_PE"] = ind_pe_list
    df["Last_Quarter_Profit"] = lq_list
    df["Last_Year_Same_Quarter_Profit"] = ly_list
    try:
        df.to_csv(file_path, index=False)
    except Exception as e:
        return 0, str(e)
    return updated, None


def main():
    os.chdir(SCRIPT_DIR)
    print("📈 Enriching Trendline and Distance CSVs with PE_Ratio, Industry_PE, Last_Quarter_Profit, Last_Year_Same_Quarter_Profit...")
    trend_path = get_latest_dated_file_path(INDIA_DATA_DIR, DATA_FILES["trends_suffix"])
    dist_path = get_latest_dated_file_path(INDIA_DATA_DIR, DATA_FILES["distance_suffix"])
    if trend_path:
        n, err = enrich_csv_with_fundamentals(trend_path)
        if err:
            print(f"   ⚠️  Trendline: {err}")
        else:
            print(f"   ✅ Trendline: {os.path.basename(trend_path)} — {n} rows enriched")
    else:
        print("   ⚠️  No Trendline CSV found")
    if dist_path:
        n, err = enrich_csv_with_fundamentals(dist_path)
        if err:
            print(f"   ⚠️  Distance: {err}")
        else:
            print(f"   ✅ Distance: {os.path.basename(dist_path)} — {n} rows enriched")
    else:
        print("   ⚠️  No Distance CSV found")
    print("✅ Fundamentals enrichment done.")


if __name__ == "__main__":
    main()
