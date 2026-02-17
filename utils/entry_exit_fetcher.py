import os
import re
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

from config import (
    INDIA_DATA_DIR,
    DATA_FILES,
    TRADE_DEDUP_COLUMNS,
    POTENTIAL_ENTRY_CSV,
    POTENTIAL_EXIT_CSV,
    ALL_SIGNALS_CSV,
    ENTRY_EXIT_MIN_WIN_RATE,
    ENTRY_EXIT_MIN_NUM_TRADES,
    ENTRY_PRICE_BAND_PCT_ABOVE,
    ENTRY_PRICE_BAND_PCT_BELOW,
    ENTRY_EXIT_MAX_PE_RATIO,
    ENTRY_EXIT_PROFIT_RATIO,
    ENTRY_SIGNAL_RECENCY_DAYS,
    EXIT_RECENCY_DAYS,
)


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
    raw_signal = parts[1].strip()
    signal_type = "Short" if "short" in raw_signal.lower() else "Long"
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
    """
    parts: List[str] = []
    for col in TRADE_DEDUP_COLUMNS:
        val = str(record.get(col, "")).strip()
        if col == "Signal_Type":
            val = "Short" if "short" in val.lower() else "Long"
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
    - Signal date within 7 days of fetch date (signal recency)
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

    # Signal date recency check (within ENTRY_SIGNAL_RECENCY_DAYS of fetch date)
    signal_date_str = record.get("Signal_Date")
    if not signal_date_str:
        return False
    try:
        signal_dt = datetime.strptime(str(signal_date_str).strip()[:10], "%Y-%m-%d").date()
        fetch_date = date.today()  # Use today as fetch date
        days_since_signal = (fetch_date - signal_dt).days
        if days_since_signal > ENTRY_SIGNAL_RECENCY_DAYS or days_since_signal < 0:
            return False
    except (ValueError, TypeError):
        return False

    # Win rate & number of trades
    win_rate = record.get("Win_Rate")
    num_trades = record.get("Number_Of_Trades")
    if win_rate is None or num_trades is None:
        return False
    if win_rate <= ENTRY_EXIT_MIN_WIN_RATE:
        return False
    if num_trades <= ENTRY_EXIT_MIN_NUM_TRADES:
        return False

    # Exit signal must be "No Exit Yet"
    exit_raw = str(record.get("Exit_Signal_Raw", "")).strip().lower()
    if "no exit yet" not in exit_raw:
        return False

    # Today vs signal price difference band based on the latest Today_Price.
    # NOTE: We use the **signed** percentage (no abs) and keep only trades
    # where the price is between -3% and +1% vs the signal price:
    # - Reject if already >= +1% above (too much unrealised profit taken)
    # - Reject if <= -3% below (too deep a dip from signal)
    price_now = record.get("Today_Price")
    signal_price = record.get("Signal_Price")
    if price_now is None or signal_price is None:
        return False
    try:
        price_now = float(price_now)
        signal_price = float(signal_price)
    except (TypeError, ValueError):
        return False
    if signal_price <= 0:
        return False
    pct_diff = (price_now - signal_price) / signal_price * 100.0
    # Reject if price is at least ENTRY_PRICE_BAND_PCT_ABOVE above, or more than |ENTRY_PRICE_BAND_PCT_BELOW| below, signal price
    if pct_diff >= ENTRY_PRICE_BAND_PCT_ABOVE or pct_diff <= ENTRY_PRICE_BAND_PCT_BELOW:
        return False

    # PE conditions
    pe_ratio = record.get("PE_Ratio")
    industry_pe = record.get("Industry_PE")
    if pe_ratio is None or industry_pe is None:
        return False
    if not (industry_pe > pe_ratio):
        return False
    if not (pe_ratio < ENTRY_EXIT_MAX_PE_RATIO):
        return False

    # Profit condition
    last_q = record.get("Last_Quarter_Profit")
    last_year_q = record.get("Last_Year_Same_Quarter_Profit")
    if last_q is None or last_year_q is None:
        return False
    if not (last_q > ENTRY_EXIT_PROFIT_RATIO * last_year_q):
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


def exit_conditions(record: Dict[str, Any], fetch_date: date) -> bool:
    """
    Apply exit conditions derived from entry conditions, with the following differences:

    - Exit signal must NOT be "No Exit Yet" (i.e. must have Exit_Date and Exit_Price).
    - (fetch_date - Exit_Date) in days must be <= 3.
    - No profit > 1% filter here; all qualifying exits are kept.
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
    if win_rate <= ENTRY_EXIT_MIN_WIN_RATE:
        return False
    if num_trades <= ENTRY_EXIT_MIN_NUM_TRADES:
        return False

    # Exit signal must be present (not "No Exit Yet")
    exit_raw = str(record.get("Exit_Signal_Raw", "")).strip().lower()
    if not exit_raw or "no exit yet" in exit_raw:
        return False

    # Exit_Date within last 3 days relative to fetch_date
    exit_date_str = record.get("Exit_Date")
    if not exit_date_str:
        return False
    try:
        exit_dt = datetime.strptime(str(exit_date_str).strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    if (fetch_date - exit_dt).days > EXIT_RECENCY_DAYS:
        return False

    # Require Exit_Price to be present
    if record.get("Exit_Price") is None:
        return False

    # PE conditions (same as entry)
    pe_ratio = record.get("PE_Ratio")
    industry_pe = record.get("Industry_PE")
    if pe_ratio is None or industry_pe is None:
        return False
    if not (industry_pe > pe_ratio):
        return False
    if not (pe_ratio < ENTRY_EXIT_MAX_PE_RATIO):
        return False

    # Profit condition (same as entry)
    last_q = record.get("Last_Quarter_Profit")
    last_year_q = record.get("Last_Year_Same_Quarter_Profit")
    if last_q is None or last_year_q is None:
        return False
    if not (last_q > ENTRY_EXIT_PROFIT_RATIO * last_year_q):
        return False

    # Trendline-specific TrendPulse condition (same as entry)
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
    Save potential entry/exit records to CSV with only the fields
    required by the Potential pages and entry/exit logic.
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

    df.to_csv(path, index=False)


def main() -> None:
    """
    Build / update potential_entry.csv and potential_exit.csv **from all_signals.csv**.

    The entry/exit conditions remain exactly the same as before; only the
    data source changes from raw Distance/Trendline CSVs to the
    deduplicated, enriched `all_signals.csv` produced by utils.all_signals_fetcher.
    """
    all_signals_df = load_existing_csv(ALL_SIGNALS_CSV)
    if all_signals_df.empty:
        raise FileNotFoundError("all_signals.csv is empty or missing. Run utils.all_signals_fetcher first.")

    all_records: List[Dict[str, Any]] = []
    for rec in all_signals_df.to_dict(orient="records"):
        if not rec.get("Dedup_Key"):
            rec["Dedup_Key"] = get_trade_dedup_key_from_record(rec)
        all_records.append(rec)

    # --- ENTRY LOGIC: fully recompute potential_entry.csv from all_signals ---
    entry_records: List[Dict[str, Any]] = []
    for record in all_records:
        if entry_conditions(record):
            entry_records.append(record)

    if entry_records:
        save_records_to_csv(POTENTIAL_ENTRY_CSV, entry_records)
    else:
        pd.DataFrame().to_csv(POTENTIAL_ENTRY_CSV, index=False)

    # --- EXIT LOGIC: select exit trades directly from all_signals.csv ---
    fetch_date = date.today()

    exit_records: List[Dict[str, Any]] = []
    for record in all_records:
        if exit_conditions(record, fetch_date):
            exit_records.append(record)

    if exit_records:
        save_records_to_csv(POTENTIAL_EXIT_CSV, exit_records)
    else:
        pd.DataFrame().to_csv(POTENTIAL_EXIT_CSV, index=False)


if __name__ == "__main__":
    main()
