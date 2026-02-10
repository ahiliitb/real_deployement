import os
from typing import Dict, Any, List, Tuple

import pandas as pd

from config import INDIA_DATA_DIR, DATA_FILES, TRADE_DEDUP_COLUMNS
from entry_exit_fetcher import get_latest_dated_file_path, build_standard_record


ALL_SIGNALS_CSV = os.path.join(INDIA_DATA_DIR, "all_signals.csv")


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
            val = "SHORT" if "SHORT" in val.upper() else "LONG"
        parts.append(val)
    return "|".join(parts)


def save_records_to_csv(path: str, records: List[Dict[str, Any]]) -> None:
    """
    Save records to CSV, including the full original Distance/Trendline columns.

    Each record contains:
    - Standardized fields (Symbol, Signal_Type, Win_Rate, etc.)
    - Raw_Data: the original CSV row as a dict

    This function flattens Raw_Data into top-level columns so that
    all_signals.csv contains the complete original data (plus helper columns).
    """
    if not records:
        pd.DataFrame().to_csv(path, index=False)
        return

    flattened: List[Dict[str, Any]] = []
    for rec in records:
        rec_copy = dict(rec)
        raw = rec_copy.pop("Raw_Data", None)
        if isinstance(raw, dict):
            # Only add raw-data columns that don't already exist on the record
            for k, v in raw.items():
                if k not in rec_copy:
                    rec_copy[k] = v
        flattened.append(rec_copy)

    df = pd.DataFrame(flattened)

    # Sort newest first by Signal_Date if present
    if "Signal_Date" in df.columns:
        df = df.sort_values(by="Signal_Date", ascending=False, na_position="last")

    df.to_csv(path, index=False)


def main() -> None:
    """
    Build / update all_signals.csv from the latest Distance and Trendline CSVs.

    - Uses TRADE_DEDUP_COLUMNS to deduplicate trades.
    - If a key already exists, the row is updated with the latest data.
    - If a key is new, the row is appended.
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

    # Build standardized records from both files
    new_records: List[Dict[str, Any]] = []
    for df, fn_name in dfs_with_function:
        for _, row in df.iterrows():
            record = build_standard_record(row, fn_name)
            new_records.append(record)

    # Load existing all_signals.csv and index by dedup key
    existing_df = load_existing_csv(ALL_SIGNALS_CSV)
    merged_by_key: Dict[str, Dict[str, Any]] = {}

    if not existing_df.empty:
        for rec in existing_df.to_dict(orient="records"):
            key = get_trade_dedup_key_from_record(rec)
            merged_by_key[key] = rec

    # Merge / update with latest records
    for rec in new_records:
        key = rec["Dedup_Key"]
        merged_by_key[key] = rec

    # Save back to CSV
    save_records_to_csv(ALL_SIGNALS_CSV, list(merged_by_key.values()))


if __name__ == "__main__":
    main()

