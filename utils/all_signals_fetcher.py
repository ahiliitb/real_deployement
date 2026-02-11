import os
from typing import Dict, Any, List, Tuple

import pandas as pd

from config import INDIA_DATA_DIR, DATA_FILES, TRADE_DEDUP_COLUMNS, ALL_SIGNALS_CSV
from utils.data_loader import get_latest_dated_file_path
from utils.entry_exit_fetcher import build_standard_record
from utils import fetch_current_price_yfinance


def load_existing_csv(path: str) -> pd.DataFrame:
    """Load a CSV if it exists, otherwise return empty DataFrame."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def get_trade_dedup_key_from_record(record: Dict[str, Any]) -> str:
    """Build deduplication key using TRADE_DEDUP_COLUMNS."""
    parts: List[str] = []
    for col in TRADE_DEDUP_COLUMNS:
        val = str(record.get(col, "")).strip()
        if col == "Signal_Type":
            val = "Short" if "short" in val.lower() else "Long"
        parts.append(val)
    return "|".join(parts)


def save_records_to_csv(path: str, records: List[Dict[str, Any]]) -> None:
    """
    Save records to CSV using **only** the columns required by the app.
    """
    if not records:
        pd.DataFrame().to_csv(path, index=False)
        return

    flattened: List[Dict[str, Any]] = []
    for rec in records:
        rec_copy = dict(rec)
        rec_copy.pop("Raw_Data", None)
        flattened.append(rec_copy)

    df = pd.DataFrame(flattened)

    cols_to_drop = [c for c in ("Signal_Open_Price", "Signal Open Price") if c in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    core_columns = [
        "Symbol",
        "Signal_Type",
        "Signal_Date",
        "Signal_Price",
        "Win_Rate",
        "Number_Of_Trades",
        "Win_Rate_Display",
        "Today_Price",
        "Exit_Signal_Raw",
        "Function",
        "Interval",
        "PE_Ratio",
        "Industry_PE",
        "Last_Quarter_Profit",
        "Last_Year_Same_Quarter_Profit",
        "Strategy_CAGR",
        "Strategy_Sharpe",
        "TrendPulse_Start_End",
        "TrendPulse_Start_Price",
        "TrendPulse_End_Price",
        "Exit_Date",
        "Exit_Price",
        "Dedup_Key",
    ]

    existing_cols = [c for c in core_columns if c in df.columns]
    df = df[existing_cols]

    if "Signal_Date" in df.columns:
        df = df.sort_values(by="Signal_Date", ascending=False, na_position="last")

    df.to_csv(path, index=False)


def update_today_prices_for_all_signals(path: str) -> None:
    """
    After all_signals.csv is (re)built, update today's price for each symbol.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return

    if df.empty or "Symbol" not in df.columns:
        return

    prices: List[float | None] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip()
        if not symbol:
            prices.append(row.get("Today_Price"))
            continue
        price = fetch_current_price_yfinance(symbol)
        if price is None:
            prices.append(row.get("Today_Price"))
        else:
            prices.append(round(float(price), 2))

    df["Today_Price"] = prices
    if "Current_Price" in df.columns:
        df = df.drop(columns=["Current_Price"])
    df.to_csv(path, index=False)


def main() -> None:
    """
    Build / update all_signals.csv from the latest Distance and Trendline CSVs.
    """
    distance_suffix = DATA_FILES.get("distance_suffix", "Distance.csv")
    trend_suffix = DATA_FILES.get("trends_suffix", "Trendline.csv")

    distance_path = get_latest_dated_file_path(INDIA_DATA_DIR, distance_suffix)
    trend_path = get_latest_dated_file_path(INDIA_DATA_DIR, trend_suffix)

    if distance_path is None and trend_path is None:
        raise FileNotFoundError("No Distance or Trendline files found in INDIA data directory.")

    dfs_with_function: List[Tuple[pd.DataFrame, str]] = []
    if distance_path:
        df_distance = pd.read_csv(distance_path)
        dfs_with_function.append((df_distance, "Distance"))
    if trend_path:
        df_trend = pd.read_csv(trend_path)
        dfs_with_function.append((df_trend, "Trendline"))

    new_records: List[Dict[str, Any]] = []
    for df, fn_name in dfs_with_function:
        for _, row in df.iterrows():
            record = build_standard_record(row, fn_name)
            new_records.append(record)

    existing_df = load_existing_csv(ALL_SIGNALS_CSV)
    merged_by_key: Dict[str, Dict[str, Any]] = {}

    if not existing_df.empty:
        for rec in existing_df.to_dict(orient="records"):
            key = get_trade_dedup_key_from_record(rec)
            merged_by_key[key] = rec

    for rec in new_records:
        key = rec["Dedup_Key"]
        merged_by_key[key] = rec

    save_records_to_csv(ALL_SIGNALS_CSV, list(merged_by_key.values()))
    update_today_prices_for_all_signals(ALL_SIGNALS_CSV)


if __name__ == "__main__":
    main()
