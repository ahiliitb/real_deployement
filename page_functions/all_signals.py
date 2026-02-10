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
from old_code.monitored_signals import display_monitored_trades_metrics
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


def show_all_signals() -> None:
    """Streamlit page: All Distance & Trendline Signals (deduplicated)."""
    st.title("📚 All Signals (Distance & Trendline)")
    st.markdown("---")

    records = _load_all_signals_from_csv()
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

