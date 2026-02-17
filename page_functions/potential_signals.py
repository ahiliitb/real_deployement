"""
Potential Entry & Exit Page

Displays signals from:
- trade_store/INDIA/potential_entry.csv
- trade_store/INDIA/potential_exit.csv

UI features:
- Filters for Function, Symbol, Win Rate, Sharpe
- Tabs and summary metrics + detailed table
"""

import os
import json
from datetime import datetime, date
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

# Shared metrics and price helpers (moved into utils package).
from config import (
    POTENTIAL_ENTRY_CSV,
    POTENTIAL_EXIT_CSV,
    TRADES_BOUGHT_CSV,
    DATA_FETCH_DATETIME_JSON,
    WIN_RATE_SLIDER_MAX,
    SHARPE_SLIDER_MIN,
    SHARPE_SLIDER_MAX,
    DEFAULT_MIN_SHARPE,
    CARDS_PER_PAGE,
    SCROLLABLE_CONTAINER_CSS,
    TRADE_DEDUP_COLUMNS,
)
from utils import (
    fetch_current_price_yfinance,
    display_monitored_trades_metrics,
)


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


def _generate_dedup_key(record: Dict[str, Any]) -> str:
    """
    Build deduplication key using TRADE_DEDUP_COLUMNS from config.
    """
    parts: List[str] = []
    for col in TRADE_DEDUP_COLUMNS:
        val = str(record.get(col, "")).strip()
        if col == "Signal_Type":
            val = "Short" if "short" in val.lower() else "Long"
        parts.append(val)
    return "|".join(parts)


def _add_to_bought_trades(trade_record: Dict[str, Any]) -> str:
    """
    Add or update a trade in the bought trades CSV.
    Returns "added" if new trade was added, "updated" if existing trade was updated,
    or "error" if something went wrong.
    """
    try:
        # Load existing bought trades
        bought_records = _load_potential_from_csv(TRADES_BOUGHT_CSV)
        
        # Generate deduplication key
        dedup_key = _generate_dedup_key(trade_record)
        trade_record["Dedup_Key"] = dedup_key
        
        # Check if trade already exists
        existing_index = None
        for idx, rec in enumerate(bought_records):
            rec_dedup_key = rec.get("Dedup_Key", "")
            if not rec_dedup_key:
                # Generate key for old records without Dedup_Key
                rec_dedup_key = _generate_dedup_key(rec)
                rec["Dedup_Key"] = rec_dedup_key
            
            if rec_dedup_key == dedup_key:
                existing_index = idx
                break
        
        if existing_index is not None:
            # Update existing trade
            bought_records[existing_index] = trade_record
            _save_potential_to_csv(TRADES_BOUGHT_CSV, bought_records)
            return "updated"
        else:
            # Add new trade
            bought_records.append(trade_record)
            _save_potential_to_csv(TRADES_BOUGHT_CSV, bought_records)
            return "added"
    except Exception as e:
        st.error(f"Error adding/updating bought trades: {e}")
        return "error"


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

    Uses column label 'Today Price' backed by the Today_Price column.
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


def _format_fundamental_value(val):
    """Format a fundamental value for display (e.g. large numbers with commas)."""
    if val is None or val == "No Data" or val == "N/A" or (isinstance(val, str) and val.lower() == "nan"):
        return "No Data"
    try:
        numeric = float(val)
        if abs(numeric) >= 1e6:
            return f"{numeric:,.0f}"
        if abs(numeric) >= 1:
            return f"{numeric:,.2f}"
        return f"{numeric:.2f}"
    except (ValueError, TypeError):
        return str(val)


def create_potential_strategy_cards(df: pd.DataFrame, title: str, tab_context: str = "") -> None:
    """
    Create individual strategy cards with pagination for potential entry/exit signals.
    Similar to create_strategy_cards but adapted for potential signals data structure.
    """
    st.markdown("### 📊 Strategy Performance Cards")
    st.markdown("Click on any card to see important trade details")

    total_signals = len(df)

    if total_signals == 0:
        st.warning("No signals match the current filters.")
        return

    # Display total count
    st.markdown(f"**Total Signals: {total_signals}**")

    # Pagination settings for strategy cards
    total_pages = (total_signals + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    # Create tabs for pagination - always use tabs instead of dropdown
    if total_signals <= CARDS_PER_PAGE:
        # If all signals fit in one page, just display them
        display_potential_strategy_cards_page(df, title, tab_context)
    else:
        # Generate tab labels
        tab_labels = []
        for i in range(total_pages):
            start_idx = i * CARDS_PER_PAGE + 1
            end_idx = min((i + 1) * CARDS_PER_PAGE, total_signals)
            tab_labels.append(f"#{start_idx}-{end_idx}")

        # Create tabs for all pages
        tabs = st.tabs(tab_labels)
        for i, tab in enumerate(tabs):
            with tab:
                start_idx = i * CARDS_PER_PAGE
                end_idx = min((i + 1) * CARDS_PER_PAGE, total_signals)
                page_df = df.iloc[start_idx:end_idx]
                st.markdown(f"**Showing signals {start_idx + 1} to {end_idx} of {total_signals}**")
                # Add pagination context to make keys unique across pagination tabs
                pagination_context = f"{tab_context}_page{i}"
                display_potential_strategy_cards_page(page_df, title, pagination_context)


def display_potential_strategy_cards_page(df: pd.DataFrame, title: str, tab_context: str = "") -> None:
    """Display strategy cards for potential signals on a given page with scrollable container."""
    if len(df) == 0:
        st.warning("No data to display on this page.")
        return

    # Add custom CSS for scrollable container
    st.markdown(SCROLLABLE_CONTAINER_CSS, unsafe_allow_html=True)

    # Get data fetch date for holding period calculation
    fetch_date = _get_data_fetch_date()

    # Create scrollable container for cards
    with st.container(height=600, border=True):
        # Display strategy cards in scrollable area
        for card_num, (idx, row) in enumerate(df.iterrows()):
            # Extract data from row
            symbol = str(row.get("Symbol", "")).strip()
            function_name = str(row.get("Function", "Unknown")).strip()
            signal_type = str(row.get("Signal_Type", "")).strip()
            interval = str(row.get("Interval", "")).strip()
            signal_date = str(row.get("Signal_Date", "")).strip()
            signal_price = row.get("Signal_Price", "N/A")
            today_price = row.get("Today_Price", "N/A")
            status = row.get("Status", "Open")
            exit_date = str(row.get("Exit_Date", "")).strip() if pd.notna(row.get("Exit_Date")) else ""
            exit_price = row.get("Exit_Price", "N/A")
            
            # Win rate
            win_rate_display = row.get("Win_Rate_Display", "")
            if not win_rate_display and pd.notna(row.get("Win_Rate")):
                win_rate_display = f"{float(row.get('Win_Rate')):.2f}%"
            if not win_rate_display:
                win_rate_display = "N/A"
            
            # Strategy metrics
            strategy_cagr = row.get("Strategy_CAGR", "N/A")
            if pd.notna(strategy_cagr) and strategy_cagr != "N/A":
                try:
                    strategy_cagr = f"{float(strategy_cagr):.2f}%"
                except (ValueError, TypeError):
                    strategy_cagr = "N/A"
            
            strategy_sharpe = row.get("Strategy_Sharpe", "N/A")
            if pd.notna(strategy_sharpe) and strategy_sharpe != "N/A":
                try:
                    strategy_sharpe = f"{float(strategy_sharpe):.2f}"
                except (ValueError, TypeError):
                    strategy_sharpe = "N/A"
            
            # Calculate profit/loss
            profit_display = "N/A"
            try:
                sig_price = float(signal_price) if pd.notna(signal_price) else None
                sig_type_upper = signal_type.upper()
                
                if status == "Closed" and pd.notna(exit_price):
                    ex_price = float(exit_price)
                    if sig_price and sig_price > 0:
                        profit = ((ex_price - sig_price) / sig_price) * 100
                        if sig_type_upper == "SHORT":
                            profit = -profit
                        profit_display = f"{profit:.2f}%"
                elif status == "Open" and pd.notna(today_price):
                    curr_price = float(today_price)
                    if sig_price and sig_price > 0:
                        profit = ((curr_price - sig_price) / sig_price) * 100
                        if sig_type_upper == "SHORT":
                            profit = -profit
                        profit_display = f"{profit:.2f}%"
            except (ValueError, TypeError):
                profit_display = "N/A"
            
            # Calculate holding period
            holding_days_display = "N/A"
            try:
                sig_date = datetime.strptime(signal_date, "%Y-%m-%d").date() if signal_date else None
                if sig_date:
                    if status == "Closed" and exit_date:
                        ex_date = datetime.strptime(exit_date, "%Y-%m-%d").date()
                        holding_days = (ex_date - sig_date).days
                        holding_days_display = f"{holding_days} days"
                    elif fetch_date:
                        holding_days = (fetch_date - sig_date).days
                        holding_days_display = f"{holding_days} days"
            except Exception:
                holding_days_display = "N/A"
            
            # Fundamentals
            fundamentals = {
                "PE_Ratio": row.get("PE_Ratio", "N/A"),
                "Industry_PE": row.get("Industry_PE", "N/A"),
                "Last_Quarter_Profit": row.get("Last_Quarter_Profit", "N/A"),
                "Last_Year_Same_Quarter_Profit": row.get("Last_Year_Same_Quarter_Profit", "N/A"),
            }
            
            # Format signal price
            signal_price_display = f"{float(signal_price):.2f}" if pd.notna(signal_price) else "N/A"
            today_price_display = f"{float(today_price):.2f}" if pd.notna(today_price) else "N/A"
            exit_price_display = f"{float(exit_price):.2f}" if pd.notna(exit_price) and status == "Closed" else "N/A"
            
            # Create expander title
            expander_title = f"🔍 {function_name} - {symbol} | {interval} | {signal_type} | {signal_date}"
            
            with st.expander(expander_title, expanded=False):
                # Buy button at the top
                buy_key = f"buy_potential_{tab_context}_{card_num}_{idx}"
                if st.button("🛒 Buy", key=buy_key, type="primary"):
                    # Convert row to dict
                    trade_dict = row.to_dict()
                    result = _add_to_bought_trades(trade_dict)
                    if result == "added":
                        st.success(f"✅ Added {symbol} to Bought Trades!")
                        st.info("Navigate to 🛒 Trades Bought page to view your bought trades.")
                    elif result == "updated":
                        st.success(f"✅ Updated {symbol} in Bought Trades!")
                        st.info("Navigate to 🛒 Trades Bought page to view your bought trades.")
                    else:
                        st.error(f"❌ Error processing {symbol}. Please try again.")
                
                st.markdown("**📋 Key Trade Information**")
                
                # Create four columns
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown("**🎯 Trade Details**")
                    st.write(f"**Symbol:** {symbol}")
                    st.write(f"**Function:** {function_name}")
                    st.write(f"**Interval:** {interval}")
                    st.write(f"**Signal:** {signal_type}")
                    st.write(f"**Signal Date:** {signal_date}")
                    st.write(f"**Signal Price:** {signal_price_display}")
                    st.write(f"**Win Rate:** {win_rate_display}")
                
                with col2:
                    st.markdown("**📊 Status & Performance**")
                    st.write(f"**Status:** {status}")
                    st.write(f"**Today Price:** {today_price_display}")
                    if status == "Closed":
                        st.write(f"**Exit Date:** {exit_date}")
                        st.write(f"**Exit Price:** {exit_price_display}")
                    st.write(f"**Current P&L:** {profit_display}")
                    st.write(f"**Strategy CAGR:** {strategy_cagr}")
                    st.write(f"**Strategy Sharpe:** {strategy_sharpe}")
                
                with col3:
                    st.markdown("**⚠️ Risk & Timing**")
                    st.write(f"**Holding Period:** {holding_days_display}")
                
                with col4:
                    st.markdown("**📈 Fundamentals**")
                    pe = fundamentals.get("PE_Ratio", "N/A")
                    ind_pe = fundamentals.get("Industry_PE", "N/A")
                    last_q = fundamentals.get("Last_Quarter_Profit", "N/A")
                    same_q = fundamentals.get("Last_Year_Same_Quarter_Profit", "N/A")
                    st.write(f"**PE Ratio:** {_format_fundamental_value(pe)}")
                    st.write(f"**Industry PE:** {_format_fundamental_value(ind_pe)}")
                    st.write(f"**Last Quarter Profit (Net Inc):** {_format_fundamental_value(last_q)}")
                    st.write(f"**Same Qtr Prior Yr (Net Inc):** {_format_fundamental_value(same_q)}")


def show_potential_entry_exit() -> None:
    """Streamlit page: Potential Entry & Exit."""
    st.title("📌 Potential Entry & Exit")
    st.markdown("---")

    # Load data
    entry_records = _load_potential_from_csv(POTENTIAL_ENTRY_CSV)
    exit_records = _load_potential_from_csv(POTENTIAL_EXIT_CSV)

    if not entry_records and not exit_records:
        st.info("No potential entry or exit signals found yet. Run 'Generate signals & refresh' first.")
        return

    df_entry = _prepare_dataframe(entry_records)
    df_exit = _prepare_dataframe(exit_records)

    # Build combined DataFrame for filter options
    combined = pd.concat(
        [df_entry.assign(Source="Entry"), df_exit.assign(Source="Exit")],
        ignore_index=True,
    )

    # Sidebar filters
    st.sidebar.markdown("### 🔍 Filters")

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
        max_value=int(WIN_RATE_SLIDER_MAX),
        value=0,
        help="Minimum win rate threshold",
        key="potential_win_rate_slider",
    )

    # Sharpe ratio filter (if present, otherwise ignored in filtering)
    min_sharpe_ratio = st.sidebar.slider(
        "Min Strategy Sharpe Ratio",
        min_value=float(SHARPE_SLIDER_MIN),
        max_value=float(SHARPE_SLIDER_MAX),
        value=float(DEFAULT_MIN_SHARPE),
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
            # Summary metrics
            display_monitored_trades_metrics(df_entry_f, "All Intervals", "Potential Entry")
            
            # Strategy cards
            st.markdown("---")
            create_potential_strategy_cards(df_entry_f, "Potential Entry", "entry")
            
            # Detailed table
            st.markdown("---")
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
            # Summary metrics
            display_monitored_trades_metrics(df_exit_f, "All Intervals", "Potential Exit")
            
            # Strategy cards
            st.markdown("---")
            create_potential_strategy_cards(df_exit_f, "Potential Exit", "exit")
            
            # Detailed table
            st.markdown("---")
            st.markdown("### 📋 Detailed Data Table — Potential Exit")
            display_trades_table_potential(df_exit_f, "Potential Exit")

