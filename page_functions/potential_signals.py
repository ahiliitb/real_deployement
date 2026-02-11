"""
Potential Entry & Exit Page

Displays signals from:
- trade_store/INDIA/potential_entry.csv
- trade_store/INDIA/potential_exit.csv

UI is modeled after the Monitored Trades page:
- Sidebar controls section with Update Prices
- Filters for Function, Symbol, Win Rate, Sharpe
- Tabs and summary metrics + detailed table
"""

import os
import time
import json
from datetime import datetime, date
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

from config import TRADE_DEDUP_COLUMNS
# Shared metrics and price helpers (moved into utils package).
from utils import (
    fetch_current_price_yfinance,
    display_monitored_trades_metrics,
)


POTENTIAL_ENTRY_CSV = "trade_store/INDIA/potential_entry.csv"
POTENTIAL_EXIT_CSV = "trade_store/INDIA/potential_exit.csv"
DATA_FETCH_DATETIME_JSON = os.path.join(os.path.dirname(POTENTIAL_ENTRY_CSV), "data_fetch_datetime.json")


def _load_potential_from_csv(path: str) -> List[Dict[str, Any]]:
    """Generic CSV loader for potential_entry/exit files."""
    try:
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            return []
        if os.path.getsize(path) == 0:
            return []
        try:
            df = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return []
        if df.empty or len(df.columns) == 0:
            return []
        records = df.to_dict("records")
        return records
    except Exception as e:
        st.error(f"Error loading {path}: {e}")
        return []


def _save_potential_to_csv(path: str, records: List[Dict[str, Any]]) -> None:
    """Save potential signals back to CSV."""
    try:
        if not records:
            pd.DataFrame().to_csv(path, index=False)
        else:
            df = pd.DataFrame(records)
            df.to_csv(path, index=False)
    except Exception as e:
        st.error(f"Error saving {path}: {e}")


def _get_data_fetch_date() -> date | None:
    """Return data-fetch date from data_fetch_datetime.json as date, or None if missing/invalid."""
    if not os.path.isfile(DATA_FETCH_DATETIME_JSON):
        return None
    try:
        with open(DATA_FETCH_DATETIME_JSON) as f:
            data = json.load(f)
        d = data.get("date") or (data.get("datetime", "")[:10] if data.get("datetime") else None)
        if not d:
            return None
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _update_potential_prices(progress_callback=None) -> None:
    """
    Update Today_Price for all symbols in potential_entry and potential_exit CSVs
    using latest prices from stock_data/INDIA.
    """
    paths = [POTENTIAL_ENTRY_CSV, POTENTIAL_EXIT_CSV]
    all_records: List[Dict[str, Any]] = []
    index_slices = []

    # Load all records, remember slices per file
    for path in paths:
        recs = _load_potential_from_csv(path)
        index_slices.append((path, len(all_records), len(all_records) + len(recs)))
        all_records.extend(recs)

    total = len(all_records)
    if total == 0:
        raise ValueError("No potential entry/exit records to update.")

    updated_count = 0
    processed = 0

    for rec in all_records:
        symbol = str(rec.get("Symbol", "")).strip()
        if not symbol:
            processed += 1
            if progress_callback:
                progress_callback(processed, total, "(empty)", False, None)
            continue

        price = fetch_current_price_yfinance(symbol)
        success = price is not None
        if success:
            rec["Today_Price"] = float(price)
            updated_count += 1
        processed += 1
        if progress_callback:
            progress_callback(processed, total, symbol, success, price)

    if updated_count == 0:
        raise ValueError(
            "No symbols could be updated. Check internet connection and that symbols are valid."
        )

    # Write back to individual CSVs (drop any transient columns)
    for path, start, end in index_slices:
        if start == end:
            continue
        subset = all_records[start:end]
        for rec in subset:
            rec.pop("Current_Price", None)
        _save_potential_to_csv(path, subset)


def _prepare_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert list of dicts to DataFrame with extra computed columns."""
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Ensure required columns exist
    for col in ["Function", "Symbol", "Signal_Type", "Interval"]:
        if col not in df.columns:
            df[col] = ""

    # Status: treat rows with non-empty Exit_Date as Closed
    if "Exit_Date" in df.columns:
        df["Status"] = df.apply(
            lambda row: "Closed"
            if pd.notna(row.get("Exit_Date"))
            and str(row.get("Exit_Date")).strip()
            and str(row.get("Exit_Signal_Raw", "")).strip().lower() != "no exit yet"
            else "Open",
            axis=1,
        )
    else:
        df["Status"] = "Open"

    # Numeric conversions for key fields (use Today_Price as the live price column)
    numeric_cols = [
        "Signal_Price",
        "Today_Price",
        "Exit_Price",
        "Win_Rate",
        "PE_Ratio",
        "Industry_PE",
        "Last_Quarter_Profit",
        "Last_Year_Same_Quarter_Profit",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Win_Rate_Display as string, fallback to Win_Rate
    if "Win_Rate_Display" in df.columns:
        df["Win_Rate_Display"] = df["Win_Rate_Display"].fillna("")
    else:
        if "Win_Rate" in df.columns:
            df["Win_Rate_Display"] = df["Win_Rate"].apply(
                lambda x: f"{float(x):.2f}%" if pd.notna(x) else ""
            )
        else:
            df["Win_Rate_Display"] = ""

    # Position (Long / Short) inferred from Signal_Type
    df["Position"] = df["Signal_Type"].apply(
        lambda x: "Long"
        if str(x).upper() == "LONG"
        else ("Short" if str(x).upper() == "SHORT" else "Long")
    )

    return df


def display_trades_table_potential(df: pd.DataFrame, title: str) -> None:
    """
    Display trades table for potential signals.

    This is adapted from monitored_signals.display_trades_table, but:
    - Uses column label 'Today Price' backed by the Today_Price column.
    """
    if df.empty:
        st.warning(f"No {title.lower()} to display")
        return

    fetch_date = _get_data_fetch_date()

    custom_data = []
    for _, row in df.iterrows():
        # Calculate profit/loss (same logic as monitored page)
        profit = None
        try:
            signal_price = row.get("Signal_Price")
            signal_type = str(row.get("Signal_Type", "")).upper()

            if row.get("Status") == "Closed":
                exit_price = row.get("Exit_Price")
                if (
                    pd.notna(signal_price)
                    and pd.notna(exit_price)
                    and signal_price != ""
                    and exit_price != ""
                ):
                    signal_price = float(signal_price)
                    exit_price = float(exit_price)
                    if signal_price > 0:
                        profit = ((exit_price - signal_price) / signal_price) * 100
                        if signal_type == "SHORT":
                            profit = -profit
            elif row.get("Status") == "Open":
                current_price = row.get("Today_Price")
                if (
                    pd.notna(signal_price)
                    and pd.notna(current_price)
                    and signal_price != ""
                    and current_price != ""
                ):
                    signal_price = float(signal_price)
                    current_price = float(current_price)
                    if signal_price > 0:
                        profit = ((current_price - signal_price) / signal_price) * 100
                        if signal_type == "SHORT":
                            profit = -profit
        except (ValueError, TypeError):
            profit = None

        # Holding period:
        # - For open trades: data fetch date minus Signal_Date
        # - For closed trades: Exit_Date minus Signal_Date
        holding_days = None
        try:
            sig_date_str = row.get("Signal_Date")
            sig_date = (
                datetime.strptime(str(sig_date_str), "%Y-%m-%d").date()
                if sig_date_str
                else None
            )
            if sig_date:
                if row.get("Status") == "Closed":
                    exit_date_str = row.get("Exit_Date")
                    exit_d = (
                        datetime.strptime(str(exit_date_str), "%Y-%m-%d").date()
                        if exit_date_str
                        else None
                    )
                    if exit_d:
                        holding_days = (exit_d - sig_date).days
                else:
                    if fetch_date:
                        holding_days = (fetch_date - sig_date).days
        except Exception:
            holding_days = None

        custom_row = {
            "Function": row.get("Function", "Unknown"),
            "Symbol": row.get("Symbol", ""),
            "Signal_Type": row.get("Signal_Type", ""),
            "Interval": row.get("Interval", ""),
            "Signal_Date": row.get("Signal_Date", ""),
            "Signal_Price": row.get("Signal_Price", ""),
            "Today Price": row.get("Today_Price", ""),
            "Profit (%)": profit,
            "Holding Period (days)": holding_days,
            "Status": row.get("Status", ""),
            "Exit_Date": row.get("Exit_Date", ""),
            "Exit_Price": row.get("Exit_Price", ""),
            "Win_Rate": row.get("Win_Rate_Display", row.get("Win_Rate", "")),
            "Strategy_CAGR": row.get("Strategy_CAGR", ""),
            "Strategy_Sharpe": row.get("Strategy_Sharpe", ""),
            "PE_Ratio": row.get("PE_Ratio", "N/A"),
            "Industry_PE": row.get("Industry_PE", "N/A"),
            "Last Qtr Profit (Net Inc)": row.get(
                "Last_Quarter_Profit", "N/A"
            ),
            "Same Qtr Prior Yr (Net Inc)": row.get(
                "Last_Year_Same_Quarter_Profit", "N/A"
            ),
        }
        custom_data.append(custom_row)

    custom_df = pd.DataFrame(custom_data)

    # Format numeric columns (same style as monitored page)
    for col in [
        "Signal_Price",
        "Today Price",
        "Profit (%)",
        "Holding Period (days)",
        "PE_Ratio",
        "Industry_PE",
        "Last Qtr Profit (Net Inc)",
        "Same Qtr Prior Yr (Net Inc)",
        "Exit_Price",
        "Win_Rate",
        "Strategy_CAGR",
        "Strategy_Sharpe",
    ]:
        if col in custom_df.columns:
            def format_value(x):
                if (
                    pd.isna(x)
                    or x == ""
                    or x is None
                    or str(x).lower() == "no data"
                ):
                    return str(x) if str(x).lower() == "no data" else ""
                try:
                    numeric_val = float(x)
                    if col == "Profit (%)":
                        return f"{numeric_val:.2f}"
                    elif "Net Inc" in col or "Profit" in col:
                        return f"{numeric_val:,.0f}"
                    else:
                        return f"{numeric_val:.2f}"
                except (ValueError, TypeError):
                    return str(x)

            custom_df[col] = custom_df[col].apply(format_value)

    st.dataframe(custom_df, use_container_width=True, height=400)


def show_potential_entry_exit() -> None:
    """Streamlit page: Potential Entry & Exit."""
    # Info toggle
    if st.button(
        "ℹ️ Info About This Page",
        key="info_potential_page",
        help="Click to learn about the Potential Entry & Exit page",
    ):
        st.session_state["show_info_potential"] = not st.session_state.get(
            "show_info_potential", False
        )

    if st.session_state.get("show_info_potential", False):
        with st.expander("📖 Potential Entry & Exit Information", expanded=True):
            st.markdown(
                """
                ### What is this page?
                This page shows **pre-filtered potential entry and exit signals** that were
                generated by the `entry_exit_fetcher.py` script.

                ### Why is it used?
                - **Potential Entry**: Candidates that satisfy your strict conditions.
                - **Potential Exit**: Signals where an exit condition has appeared.

                ### How to use?
                - Use the **tabs** to switch between potential entries and exits.
                - Use the **sidebar** to update prices and apply filters by function, symbol, and win rate.
                """
            )

    st.title("📌 Potential Entry & Exit")
    st.markdown("---")

    # Load data
    entry_records = _load_potential_from_csv(POTENTIAL_ENTRY_CSV)
    exit_records = _load_potential_from_csv(POTENTIAL_EXIT_CSV)

    if not entry_records and not exit_records:
        st.info("No potential entry or exit signals found yet. Run `entry_exit_fetcher.py` first.")
        return

    df_entry = _prepare_dataframe(entry_records)
    df_exit = _prepare_dataframe(exit_records)

    # Sidebar controls
    st.sidebar.markdown("### 🔧 Controls (Potential)")

    if st.sidebar.button(
        "🔄 Update Prices (Potential)",
        key="update_potential_prices_btn",
        help="Fetch latest prices for all potential entry/exit signals from local stock_data/INDIA files",
    ):
        total_records = len(df_entry) + len(df_exit)
        if total_records == 0:
            st.sidebar.warning("No potential records to update.")
        else:
            progress_placeholder = st.sidebar.empty()
            progress_bar = st.sidebar.progress(0, text="Starting...")
            status_text = st.sidebar.empty()

            def on_progress(processed, total, symbol, success, price):
                pct = processed / total if total else 0
                progress_bar.progress(pct, text=f"Updating {processed}/{total}")
                if success and price is not None:
                    status_text.caption(
                        f"✓ {symbol}: {price:.2f} — {processed} of {total} updated"
                    )
                else:
                    status_text.caption(
                        f"— {symbol or '(empty)'}: no price — {processed}/{total} processed"
                    )

            try:
                _update_potential_prices(progress_callback=on_progress)
                progress_bar.progress(1.0, text="Done!")
                progress_placeholder.success("✅ Prices updated for potential signals.")
            except Exception as e:
                progress_placeholder.error(f"Update failed: {e}")
            st.rerun()

    # Build combined DataFrame for filter options
    combined = pd.concat(
        [df_entry.assign(Source="Entry"), df_exit.assign(Source="Exit")],
        ignore_index=True,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 🔍 Filters")

    # Function filter
    available_functions = sorted(
        [f for f in combined["Function"].dropna().unique() if str(f).strip()]
    )
    all_functions_label = "All Functions"
    function_options = [all_functions_label] + available_functions

    selected_functions = st.sidebar.multiselect(
        "Select Functions",
        options=function_options,
        default=function_options,
        key="potential_functions_multiselect",
        help=f"Choose one or more functions. Select '{all_functions_label}' to include all.",
    )

    if all_functions_label in selected_functions or not selected_functions:
        active_functions = available_functions
    else:
        active_functions = [f for f in selected_functions if f in available_functions]

    # Symbol filter
    available_symbols = sorted(
        [s for s in combined["Symbol"].dropna().unique() if str(s).strip()]
    )
    all_symbols_label = "All Symbols"
    symbol_options = [all_symbols_label] + available_symbols

    selected_symbols = st.sidebar.multiselect(
        "Select Symbols",
        options=symbol_options,
        default=symbol_options,
        key="potential_symbols_multiselect",
        help=f"Choose one or more symbols. Select '{all_symbols_label}' to include all.",
    )

    if all_symbols_label in selected_symbols or not selected_symbols:
        active_symbols = available_symbols
    else:
        active_symbols = [s for s in selected_symbols if s in available_symbols]

    # Win rate filter
    min_win_rate = st.sidebar.slider(
        "Min Win Rate (%)",
        min_value=0,
        max_value=100,
        value=0,
        help="Minimum win rate threshold",
        key="potential_win_rate_slider",
    )

    # Sharpe ratio filter (if present, otherwise ignored in filtering)
    min_sharpe_ratio = st.sidebar.slider(
        "Min Strategy Sharpe Ratio",
        min_value=-5.0,
        max_value=5.0,
        value=-5.0,
        step=0.1,
        help="Minimum Strategy Sharpe Ratio threshold (if column exists)",
        key="potential_sharpe_slider",
    )

    # Apply filters to each DataFrame
    def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df_f = df[
            (df["Function"].isin(active_functions) if active_functions else True)
            & (df["Symbol"].isin(active_symbols) if active_symbols else True)
        ]
        if "Win_Rate" in df_f.columns and min_win_rate > 0:
            df_f = df_f[df_f["Win_Rate"].fillna(0) >= float(min_win_rate)]
        if "Strategy_Sharpe" in df_f.columns:
            df_f = df_f[df_f["Strategy_Sharpe"].fillna(-999) >= float(min_sharpe_ratio)]
        return df_f

    df_entry_f = _apply_filters(df_entry)
    df_exit_f = _apply_filters(df_exit)

    # Tabs: Potential Entry / Potential Exit
    tab_entry, tab_exit = st.tabs(["📥 Potential Entry", "📤 Potential Exit"])

    with tab_entry:
        st.subheader("📥 Potential Entry Signals")
        if df_entry_f.empty:
            st.info("No potential entry signals match the current filters.")
        else:
            # Sort newest first by Signal_Date if present
            if "Signal_Date" in df_entry_f.columns:
                df_entry_f = df_entry_f.sort_values(
                    by="Signal_Date", ascending=False, na_position="last"
                )
            # Summary metrics and detailed table (reuse metrics; custom table for Today Price label)
            display_monitored_trades_metrics(df_entry_f, "All Intervals", "Potential Entry")
            st.markdown("### 📋 Detailed Data Table — Potential Entry")
            display_trades_table_potential(df_entry_f, "Potential Entry")

    with tab_exit:
        st.subheader("📤 Potential Exit Signals")
        if df_exit_f.empty:
            st.info("No potential exit signals match the current filters.")
        else:
            if "Signal_Date" in df_exit_f.columns:
                df_exit_f = df_exit_f.sort_values(
                    by="Signal_Date", ascending=False, na_position="last"
                )
            display_monitored_trades_metrics(df_exit_f, "All Intervals", "Potential Exit")
            st.markdown("### 📋 Detailed Data Table — Potential Exit")
            display_trades_table_potential(df_exit_f, "Potential Exit")

