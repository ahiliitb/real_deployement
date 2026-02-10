import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

from config import INDIA_DATA_DIR, DATA_FILES, TRADE_DEDUP_COLUMNS


POTENTIAL_ENTRY_CSV = os.path.join(INDIA_DATA_DIR, "potential_entry.csv")
POTENTIAL_EXIT_CSV = os.path.join(INDIA_DATA_DIR, "potential_exit.csv")


def get_latest_dated_file_path(data_dir: str, suffix: str) -> Optional[str]:
    """
    Find the latest dated file in data_dir with pattern YYYY-MM-DD_<suffix>.
    Example: 2026-02-09_Distance.csv
    """
    if not os.path.isdir(data_dir):
        return None

    latest_date: Optional[datetime] = None
    latest_path: Optional[str] = None

    for fname in os.listdir(data_dir):
        if not fname.endswith(suffix):
            continue
        # Expect pattern: YYYY-MM-DD_<suffix>
        parts = fname.split("_", 1)
        if len(parts) != 2:
            continue
        date_str, _ = parts
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if latest_date is None or d > latest_date:
            latest_date = d
            latest_path = os.path.join(data_dir, fname)

    return latest_path


def parse_signal_column(value: str) -> Dict[str, Any]:
    """
    Parse 'Symbol, Signal, Signal Date/Price[$]' column.
    Example: "HCLTECH.NS, Long, 2026-02-09 (Price: 1597.5)"
    """
    result = {
        "Symbol": None,
        "Signal_Type": None,
        "Signal_Date": None,
        "Signal_Price": None,
    }
    if not isinstance(value, str):
        return result

    parts = [p.strip() for p in value.split(",")]
    if len(parts) < 3:
        return result

    symbol = parts[0]
    signal_type = parts[1]
    # Re-join remaining in case there were extra commas in symbol
    date_price_part = ",".join(parts[2:]).strip()

    # Extract date and price from "YYYY-MM-DD (Price: 1597.5)"
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_price_part)
    price_match = re.search(r"Price:\s*([0-9.]+)", date_price_part)

    signal_date = date_match.group(1) if date_match else None
    signal_price = float(price_match.group(1)) if price_match else None

    result["Symbol"] = symbol
    result["Signal_Type"] = signal_type
    result["Signal_Date"] = signal_date
    result["Signal_Price"] = signal_price
    return result


def parse_win_rate_and_trades(value: str) -> Tuple[Optional[float], Optional[int]]:
    """
    Parse 'Win Rate [%], History Tested, Number of Trades' column.
    Example: "92.31%, Past 4 years, 13"
    Returns (win_rate_percent, number_of_trades)
    """
    if not isinstance(value, str):
        return None, None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) < 3:
        return None, None
    # First part: "92.31%"
    win_rate_str = parts[0].replace("%", "").strip()
    try:
        win_rate = float(win_rate_str)
    except ValueError:
        win_rate = None

    # Last part should contain number of trades
    num_trades_part = parts[-1]
    # Extract last integer from the string
    trades_match = re.search(r"(\d+)", num_trades_part)
    num_trades = int(trades_match.group(1)) if trades_match else None
    return win_rate, num_trades


def parse_today_vs_signal(value: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Parse 'Today Trading Date/Price[$], Today price vs Signal'.
    Example: "2026-02-09 (Price: 1597.5), 0.0% below"
    Returns (today_price, pct_diff, signed_pct) where pct_diff is absolute value.
    """
    if not isinstance(value, str):
        return None, None, None

    price_match = re.search(r"Price:\s*([0-9.]+)", value)
    pct_match = re.search(r"([0-9.]+)\s*% ?", value)

    today_price = float(price_match.group(1)) if price_match else None
    signed_pct = float(pct_match.group(1)) if pct_match else None
    pct_diff = abs(signed_pct) if signed_pct is not None else None
    return today_price, pct_diff, signed_pct


def parse_trendpulse_start_end(value: Any) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse 'TrendPulse Start/End (Date and Price($))'.
    Example: "2025-12-18 (Price: 200.9578)/2026-02-09 (Price: 169.4817)"
    Returns (start_price, end_price)
    """
    if not isinstance(value, str) or not value.strip():
        return None, None

    prices = re.findall(r"Price:\s*([0-9.]+)", value)
    if len(prices) < 2:
        return None, None

    try:
        start_price = float(prices[0])
        end_price = float(prices[1])
    except ValueError:
        return None, None
    return start_price, end_price


def parse_interval(value: Any) -> str:
    """
    Parse 'Interval, Confirmation Status' column.
    Example: "Daily, is CONFIRMED on 2026-02-09" -> "Daily"
    """
    if not isinstance(value, str):
        return ""
    return value.split(",")[0].strip()


def get_trade_dedup_key_from_record(record: Dict[str, Any]) -> str:
    """
    Build deduplication key using TRADE_DEDUP_COLUMNS.
    Mirrors logic in page_functions.monitored_signals.get_trade_dedup_key.
    """
    parts: List[str] = []
    for col in TRADE_DEDUP_COLUMNS:
        val = str(record.get(col, "")).strip()
        if col == "Signal_Type":
            val = "SHORT" if "SHORT" in val.upper() else "LONG"
        parts.append(val)
    return "|".join(parts)


def build_standard_record(row: pd.Series, function_name: str) -> Dict[str, Any]:
    """
    Standardize a row from Distance/Trendline CSV into a common trade record.
    """
    raw_dict = row.to_dict()

    signal_info = parse_signal_column(row.get("Symbol, Signal, Signal Date/Price[$]", ""))
    win_rate, num_trades = parse_win_rate_and_trades(
        row.get("Win Rate [%], History Tested, Number of Trades", "")
    )
    today_price, today_pct_diff, signed_pct = parse_today_vs_signal(
        row.get("Today Trading Date/Price[$], Today price vs Signal", "")
    )

    pe_ratio = row.get("PE_Ratio")
    industry_pe = row.get("Industry_PE")
    last_q_profit = row.get("Last_Quarter_Profit")
    last_year_q_profit = row.get("Last_Year_Same_Quarter_Profit")
    strategy_cagr = row.get("Backtested Strategy CAGR [%]")
    strategy_sharpe = row.get("Backtested Strategy Sharpe Ratio")

    try:
        pe_ratio = float(pe_ratio)
    except (TypeError, ValueError):
        pe_ratio = None
    try:
        industry_pe = float(industry_pe)
    except (TypeError, ValueError):
        industry_pe = None
    try:
        last_q_profit = float(last_q_profit)
    except (TypeError, ValueError):
        last_q_profit = None
    try:
        last_year_q_profit = float(last_year_q_profit)
    except (TypeError, ValueError):
        last_year_q_profit = None
    try:
        # Strategy CAGR is stored as a percent string, e.g. "24.34%"
        strategy_cagr = float(str(strategy_cagr).replace("%", "")) if strategy_cagr not in (None, "") else None
    except (TypeError, ValueError):
        strategy_cagr = None
    try:
        strategy_sharpe = float(strategy_sharpe)
    except (TypeError, ValueError):
        strategy_sharpe = None

    interval = parse_interval(row.get("Interval, Confirmation Status", ""))

    trendpulse_start_end = row.get("TrendPulse Start/End (Date and Price($))", "")
    start_price, end_price = parse_trendpulse_start_end(trendpulse_start_end)

    record: Dict[str, Any] = {
        "Symbol": signal_info["Symbol"],
        "Signal_Type": signal_info["Signal_Type"],
        "Signal_Date": signal_info["Signal_Date"],
        "Signal_Price": signal_info["Signal_Price"],
        "Signal_Open_Price": row.get("Signal Open Price"),
        "Win_Rate": win_rate,
        "Number_Of_Trades": num_trades,
        "Win_Rate_Display": f"{win_rate:.2f}%" if win_rate is not None else "",
        "Today_Price": today_price,
        "Today_vs_Signal_Pct": today_pct_diff,
        "Today_vs_Signal_Pct_Signed": signed_pct,
        "Exit_Signal_Raw": row.get("Exit Signal Date/Price[$]", ""),
        "Function": function_name,
        "Interval": interval,
        "PE_Ratio": pe_ratio,
        "Industry_PE": industry_pe,
        "Last_Quarter_Profit": last_q_profit,
        "Last_Year_Same_Quarter_Profit": last_year_q_profit,
        "Strategy_CAGR": strategy_cagr,
        "Strategy_Sharpe": strategy_sharpe,
        "TrendPulse_Start_End": trendpulse_start_end,
        "TrendPulse_Start_Price": start_price,
        "TrendPulse_End_Price": end_price,
        "Raw_Data": raw_dict,
    }
    # Also include Exit_Date/Exit_Price parsed from Exit_Signal_Raw for exits
    exit_raw = record["Exit_Signal_Raw"]
    if isinstance(exit_raw, str) and exit_raw and "No Exit Yet" not in exit_raw:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", exit_raw)
        price_match = re.search(r"Price:\s*([0-9.]+)", exit_raw)
        record["Exit_Date"] = date_match.group(1) if date_match else None
        record["Exit_Price"] = float(price_match.group(1)) if price_match else None
    else:
        record["Exit_Date"] = None
        record["Exit_Price"] = None

    # Dedup key
    record["Dedup_Key"] = get_trade_dedup_key_from_record(record)
    return record


def entry_conditions(record: Dict[str, Any]) -> bool:
    """
    Apply all entry conditions specified by the user.

    Conditions:
    - Long signals only (buy trades)
    - Win Rate [%] > 80
    - Number of Trades > 6
    - Exit signal is "No Exit Yet"
    - |today price vs signal| < 1%
    - Industry PE > PE ratio
    - PE ratio < 50
    - Last_Quarter_Profit > 0.5 * Last_Year_Same_Quarter_Profit
    - For Trendline function: TrendPulse start price > TrendPulse end price
    """
    # Long only
    signal_type = str(record.get("Signal_Type", "")).strip().upper()
    if signal_type != "LONG":
        return False

    # Win rate & number of trades
    win_rate = record.get("Win_Rate")
    num_trades = record.get("Number_Of_Trades")
    if win_rate is None or num_trades is None:
        return False
    if win_rate <= 80.0:
        return False
    if num_trades <= 6:
        return False

    # Exit signal must be "No Exit Yet"
    exit_raw = str(record.get("Exit_Signal_Raw", "")).strip().lower()
    if "no exit yet" not in exit_raw:
        return False

    # Today vs signal price difference < 1%
    pct_diff = record.get("Today_vs_Signal_Pct")
    if pct_diff is None:
        return False
    if pct_diff >= 1.0:
        return False

    # PE conditions
    pe_ratio = record.get("PE_Ratio")
    industry_pe = record.get("Industry_PE")
    if pe_ratio is None or industry_pe is None:
        return False
    if not (industry_pe > pe_ratio):
        return False
    if not (pe_ratio < 50.0):
        return False

    # Profit condition
    last_q = record.get("Last_Quarter_Profit")
    last_year_q = record.get("Last_Year_Same_Quarter_Profit")
    if last_q is None or last_year_q is None:
        return False
    if not (last_q > 0.5 * last_year_q):
        return False

    # Trendline-specific TrendPulse condition
    if str(record.get("Function", "")).lower() == "trendline":
        start_price = record.get("TrendPulse_Start_Price")
        end_price = record.get("TrendPulse_End_Price")
        if start_price is None or end_price is None:
            return False
        if not (start_price > end_price):
            return False

    return True


def load_existing_csv(path: str) -> pd.DataFrame:
    """Load a CSV if it exists, otherwise return empty DataFrame."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def save_records_to_csv(path: str, records: List[Dict[str, Any]]) -> None:
    """
    Save records to CSV, including the full original Distance/Trendline columns.

    Each record contains:
    - Standardized fields (Symbol, Signal_Type, Win_Rate, etc.)
    - Raw_Data: the original CSV row as a dict

    This function flattens Raw_Data into top-level columns so that
    potential_entry.csv / potential_exit.csv contain the complete
    original data (plus our helper columns), as requested.
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
    df.to_csv(path, index=False)


def main() -> None:
    # Locate latest Distance and Trendline files
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
    all_records: List[Dict[str, Any]] = []
    for df, fn_name in dfs_with_function:
        for _, row in df.iterrows():
            record = build_standard_record(row, fn_name)
            all_records.append(record)

    # --- ENTRY LOGIC: build/update potential_entry.csv ---
    existing_entry_df = load_existing_csv(POTENTIAL_ENTRY_CSV)
    existing_entry_records: List[Dict[str, Any]] = []
    existing_keys = set()
    if not existing_entry_df.empty:
        existing_entry_records = existing_entry_df.to_dict(orient="records")
        for rec in existing_entry_records:
            key = get_trade_dedup_key_from_record(rec)
            rec["Dedup_Key"] = key
            existing_keys.add(key)

    new_entry_records: List[Dict[str, Any]] = []
    for record in all_records:
        if not entry_conditions(record):
            continue
        key = record["Dedup_Key"]
        if key in existing_keys:
            # Already in potential_entry.csv
            continue
        new_entry_records.append(record)
        existing_keys.add(key)

    updated_entry_records = existing_entry_records + new_entry_records
    if updated_entry_records:
        save_records_to_csv(POTENTIAL_ENTRY_CSV, updated_entry_records)
    else:
        # If no entries at all, ensure file exists but stays empty
        pd.DataFrame().to_csv(POTENTIAL_ENTRY_CSV, index=False)

    # --- EXIT LOGIC: move resolved trades to potential_exit.csv ---
    # Reload entry DataFrame to ensure consistency
    entry_df = load_existing_csv(POTENTIAL_ENTRY_CSV)
    if entry_df.empty:
        # Nothing to exit
        return

    entry_records = entry_df.to_dict(orient="records")
    entry_key_to_indices: Dict[str, List[int]] = {}
    for idx, rec in enumerate(entry_records):
        key = get_trade_dedup_key_from_record(rec)
        rec["Dedup_Key"] = key
        entry_key_to_indices.setdefault(key, []).append(idx)

    # Build records that now have an exit signal
    exit_candidate_records: List[Dict[str, Any]] = []
    for record in all_records:
        exit_raw = str(record.get("Exit_Signal_Raw", "")).strip().lower()
        if not exit_raw or "no exit yet" in exit_raw:
            continue
        key = record["Dedup_Key"]
        if key in entry_key_to_indices:
            exit_candidate_records.append(record)

    if not exit_candidate_records:
        # No exits detected for existing potential entries
        return

    # Load existing potential_exit.csv
    existing_exit_df = load_existing_csv(POTENTIAL_EXIT_CSV)
    existing_exit_records: List[Dict[str, Any]] = []
    if not existing_exit_df.empty:
        existing_exit_records = existing_exit_df.to_dict(orient="records")

    # Build new exit records and mark indices to remove from entry
    indices_to_remove: List[int] = []
    for exit_rec in exit_candidate_records:
        key = exit_rec["Dedup_Key"]
        indices = entry_key_to_indices.get(key, [])
        if not indices:
            continue
        # Use the first matching entry record as base, but update exit info
        base_idx = indices[0]
        base_rec = entry_records[base_idx].copy()
        base_rec["Exit_Signal_Raw"] = exit_rec.get("Exit_Signal_Raw")
        base_rec["Exit_Date"] = exit_rec.get("Exit_Date")
        base_rec["Exit_Price"] = exit_rec.get("Exit_Price")
        base_rec["Today_Price"] = exit_rec.get("Today_Price", base_rec.get("Today_Price"))
        base_rec["Today_vs_Signal_Pct"] = exit_rec.get(
            "Today_vs_Signal_Pct", base_rec.get("Today_vs_Signal_Pct")
        )
        base_rec["Today_vs_Signal_Pct_Signed"] = exit_rec.get(
            "Today_vs_Signal_Pct_Signed", base_rec.get("Today_vs_Signal_Pct_Signed")
        )
        existing_exit_records.append(base_rec)
        # Mark all entries with this key for removal
        indices_to_remove.extend(indices)

    # Remove entries that now have exits
    if indices_to_remove:
        indices_to_remove = sorted(set(indices_to_remove))
        entry_records_after = [
            rec for idx, rec in enumerate(entry_records) if idx not in indices_to_remove
        ]
        if entry_records_after:
            save_records_to_csv(POTENTIAL_ENTRY_CSV, entry_records_after)
        else:
            # Write empty CSV with no rows
            pd.DataFrame().to_csv(POTENTIAL_ENTRY_CSV, index=False)

        # Save updated potential_exit.csv
        if existing_exit_records:
            save_records_to_csv(POTENTIAL_EXIT_CSV, existing_exit_records)
        else:
            pd.DataFrame().to_csv(POTENTIAL_EXIT_CSV, index=False)


if __name__ == "__main__":
    main()

