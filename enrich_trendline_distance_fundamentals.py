#!/usr/bin/env python3
"""
Add PE_Ratio, Industry_PE, Last_Quarter_Profit, Last_Year_Same_Quarter_Profit
to the latest Trendline and Distance CSVs in trade_store/INDIA.
Run after update_trade.sh so strategy cards can show these columns from the CSV.
"""

import os
import sys
import time

# Run from project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pandas as pd
import yfinance as yf
from utils.data_loader import get_latest_dated_file_path
from config import INDIA_DATA_DIR, DATA_FILES


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


def fetch_additional_stock_data(symbol):
    """
    Fetch PE_Ratio, Industry_PE, Last_Quarter_Profit, Last_Year_Same_Quarter_Profit
    using yfinance. This is an inlined version of the helper previously defined
    in the monitored trades module.
    """
    try:
        # Small delay to avoid rate limiting
        time.sleep(0.5)

        ticker = yf.Ticker(symbol)

        info = ticker.info or {}

        # PE Ratio
        pe_ratio = info.get("trailingPE") or info.get("forwardPE") or "N/A"

        # Industry/Sector for Industry PE approximation
        industry = info.get("industry", "Unknown")
        sector = info.get("sector", "Unknown")

        industry_pe_ratios = {
            # Technology
            "Semiconductors": 25.0,
            "Software": 30.0,
            "Consumer Electronics": 20.0,
            "Computer Hardware": 22.0,
            "Information Technology Services": 28.0,
            # Healthcare
            "Biotechnology": 35.0,
            "Drug Manufacturers": 18.0,
            "Medical Devices": 25.0,
            "Healthcare Plans": 15.0,
            "Medical Diagnostics & Research": 30.0,
            # Financial Services
            "Banks": 12.0,
            "Insurance": 14.0,
            "Asset Management": 16.0,
            "Credit Services": 10.0,
            "Capital Markets": 18.0,
            # Consumer Goods
            "Beverages": 20.0,
            "Food": 18.0,
            "Household & Personal Products": 22.0,
            "Tobacco": 15.0,
            "Apparel": 25.0,
            # Energy
            "Oil & Gas": 8.0,
            "Utilities": 16.0,
            # Industrials
            "Aerospace": 20.0,
            "Engineering": 22.0,
            "Manufacturing": 18.0,
            # Default
            "Unknown": 20.0,
        }

        industry_pe = industry_pe_ratios.get(
            industry, industry_pe_ratios.get(sector, 20.0)
        )

        # Quarterly financials for profit data
        quarterly_financials = ticker.quarterly_financials

        last_quarter_profit = "N/A"
        last_year_same_quarter_profit = "N/A"

        if (
            quarterly_financials is not None
            and not quarterly_financials.empty
            and "Net Income" in quarterly_financials.index
        ):
            net_income_series = quarterly_financials.loc["Net Income"]

            last_available_idx = None
            for i in range(len(net_income_series)):
                val = net_income_series.iloc[i]
                if pd.notna(val) and str(val).strip() not in ("", "nan", "N/A"):
                    try:
                        float(val)
                        last_available_idx = i
                        break
                    except (ValueError, TypeError):
                        continue

            if last_available_idx is not None:
                last_quarter_profit = net_income_series.iloc[last_available_idx]
                prior_year_idx = last_available_idx + 4
                if prior_year_idx < len(net_income_series):
                    last_year_same_quarter_profit = net_income_series.iloc[prior_year_idx]

        def clean_value(val):
            if val == "N/A" or (
                hasattr(val, "isna") and val.isna()
            ) or str(val).lower() == "nan":
                return "No Data"
            return val

        return {
            "PE_Ratio": clean_value(pe_ratio),
            "Industry_PE": clean_value(industry_pe),
            "Last_Quarter_Profit": clean_value(last_quarter_profit),
            "Last_Year_Same_Quarter_Profit": clean_value(
                last_year_same_quarter_profit
            ),
        }

    except Exception:
        return {
            "PE_Ratio": "No Data",
            "Industry_PE": "No Data",
            "Last_Quarter_Profit": "No Data",
            "Last_Year_Same_Quarter_Profit": "No Data",
        }


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
