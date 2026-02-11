"""
All Signals Page

Displays all deduplicated signals from:
- trade_store/INDIA/all_signals.csv

The CSV is maintained by all_signals_fetcher.py, which pulls from the
latest Distance and Trendline CSVs and merges by dedup key.
"""

import os
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

from config import TRADE_DEDUP_COLUMNS
from utils import (
    display_monitored_trades_metrics,
    fetch_current_price_yfinance,
)
from page_functions.potential_signals import (
    _prepare_dataframe as prepare_potential_dataframe,
    display_trades_table_potential,
)


ALL_SIGNALS_CSV = "trade_store/INDIA/all_signals.csv"


def _load_all_signals_from_csv() -> List[Dict[str, Any]]:
    """Load all signals from CSV file."""
    try:
        if not os.path.exists(ALL_SIGNALS_CSV):
            os.makedirs(os.path.dirname(ALL_SIGNALS_CSV), exist_ok=True)
            return []
        if os.path.getsize(ALL_SIGNALS_CSV) == 0:
            return []
        try:
            df = pd.read_csv(ALL_SIGNALS_CSV)
        except pd.errors.EmptyDataError:
            return []
        if df.empty or len(df.columns) == 0:
            return []
        return df.to_dict("records")
    except Exception as e:
        st.error(f"Error loading all_signals.csv: {e}")
        return []


def _save_all_signals_to_csv(records: List[Dict[str, Any]]) -> None:
    """Save all-signals records back to CSV."""
    try:
        if not records:
            pd.DataFrame().to_csv(ALL_SIGNALS_CSV, index=False)
        else:
            df = pd.DataFrame(records)
            df.to_csv(ALL_SIGNALS_CSV, index=False)
    except Exception as e:
        st.error(f"Error saving all_signals.csv: {e}")


def _update_all_signals_prices(progress_callback=None) -> None:
    """
    Update Today_Price for all symbols in all_signals.csv.

    Prices are sourced from local stock_data/INDIA CSV files via utils.
    """
    records = _load_all_signals_from_csv()
    total = len(records)
    if total == 0:
        raise ValueError("No all-signals records to update.")

    updated_count = 0
    processed = 0

    for rec in records:
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

    _save_all_signals_to_csv(records)


def show_all_signals() -> None:
    """Streamlit page: All Distance & Trendline Signals (deduplicated)."""
    st.title("📚 All Signals (Distance & Trendline)")
    st.markdown("---")

    records = _load_all_signals_from_csv()

    # Sidebar controls for this page
    st.sidebar.markdown("### 🔧 Controls (All Signals)")
    if st.sidebar.button(
        "🔄 Update Prices (All Signals)",
        key="update_all_signals_prices_btn",
        help="Fetch latest prices for all rows on the All Signals page from local stock_data/INDIA files",
    ):
        total_records = len(records)
        if total_records == 0:
            st.sidebar.warning("No all-signals records to update.")
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
                _update_all_signals_prices(progress_callback=on_progress)
                progress_bar.progress(1.0, text="Done!")
                progress_placeholder.success("✅ Prices updated for all-signals data.")
            except Exception as e:
                progress_placeholder.error(f"Update failed: {e}")
            st.rerun()

    if not records:
        st.info(
            "No signals found in `all_signals.csv`. "
            "Run `all_signals_fetcher.py` (or click 'Generate signals & refresh') first."
        )
        return

    # Reuse the same normalization as Potential Entry/Exit page so
    # columns, Status, Win_Rate_Display, and Today Price behave identically.
    df = prepare_potential_dataframe(records)

    # Sidebar filters
    st.sidebar.markdown("### 🔍 All Signals Filters")

    available_functions = sorted(
        [f for f in df["Function"].dropna().unique() if str(f).strip()]
    )
    all_functions_label = "All Functions"
    function_options = [all_functions_label] + available_functions

    selected_function = st.sidebar.selectbox(
        "Function", options=function_options, index=0
    )
    if selected_function != all_functions_label:
        df = df[df["Function"] == selected_function]

    available_symbols = sorted(
        [s for s in df["Symbol"].dropna().unique() if str(s).strip()]
    )
    all_symbols_label = "All Symbols"
    symbol_options = [all_symbols_label] + available_symbols

    selected_symbol = st.sidebar.selectbox(
        "Symbol", options=symbol_options, index=0
    )
    if selected_symbol != all_symbols_label:
        df = df[df["Symbol"] == selected_symbol]

    if df.empty:
        st.warning("No signals match the current filters.")
        return

    # Summary metrics and detailed table should match Potential Entry/Exit
    st.markdown("### 📊 All Signals Summary")
    display_monitored_trades_metrics(df, "All Intervals", "All Signals")

    st.markdown("### 📋 Detailed Data Table — All Signals")
    display_trades_table_potential(df, "All Signals")

