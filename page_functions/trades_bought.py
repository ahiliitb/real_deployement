"""
Trades Bought Page

Displays trades that have been manually marked as "bought" by the user.
Similar structure to Potential Entry/Exit page with:
- Summary metrics
- Strategy cards
- Detailed data table
- Ability to remove trades
"""

import os
import json
from datetime import datetime, date
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

from config import (
    TRADES_BOUGHT_CSV,
    DATA_FETCH_DATETIME_JSON,
    WIN_RATE_SLIDER_MAX,
    SHARPE_SLIDER_MIN,
    SHARPE_SLIDER_MAX,
    DEFAULT_MIN_SHARPE,
    CARDS_PER_PAGE,
    SCROLLABLE_CONTAINER_CSS,
)
from utils import (
    fetch_current_price_yfinance,
    display_monitored_trades_metrics,
)


def _load_bought_from_csv(path: str) -> List[Dict[str, Any]]:
    """Load trades bought from CSV."""
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


def _save_bought_to_csv(path: str, records: List[Dict[str, Any]]) -> None:
    """Save trades bought back to CSV."""
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


def _update_bought_prices(progress_callback=None) -> None:
    """
    Update Today_Price for all symbols in trades_bought CSV
    using latest prices from stock_data/INDIA.
    """
    records = _load_bought_from_csv(TRADES_BOUGHT_CSV)
    
    total = len(records)
    if total == 0:
        raise ValueError("No bought trades to update.")

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

    # Write back to CSV (drop any transient columns)
    for rec in records:
        rec.pop("Current_Price", None)
    _save_bought_to_csv(TRADES_BOUGHT_CSV, records)


def _prepare_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert list of dicts to DataFrame with extra computed columns."""
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Ensure required columns exist
    for col in ["Function", "Symbol", "Signal_Type", "Interval"]:
        if col not in df.columns:
            df[col] = ""

    # Add Bought_Date if not present (for legacy records)
    if "Bought_Date" not in df.columns:
        df["Bought_Date"] = datetime.now().strftime("%Y-%m-%d")

    # Status: all bought trades are "Open" unless they have Exit_Date
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

    # Numeric conversions for key fields
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


def display_trades_table_bought(df: pd.DataFrame, title: str) -> None:
    """
    Display trades table for bought trades.
    Similar to potential signals table.
    """
    if df.empty:
        st.warning(f"No {title.lower()} to display")
        return

    fetch_date = _get_data_fetch_date()

    custom_data = []
    for _, row in df.iterrows():
        # Calculate profit/loss
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

        # Holding period
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
            "Bought_Date": row.get("Bought_Date", ""),
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

    # Format numeric columns
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


def create_bought_strategy_cards(df: pd.DataFrame, title: str, tab_context: str = "") -> None:
    """
    Create individual strategy cards with pagination for bought trades.
    Includes a "Remove" button to remove trades from the bought list.
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

    # Create tabs for pagination
    if total_signals <= CARDS_PER_PAGE:
        display_bought_strategy_cards_page(df, title, tab_context)
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
                pagination_context = f"{tab_context}_page{i}"
                display_bought_strategy_cards_page(page_df, title, pagination_context)


def display_bought_strategy_cards_page(df: pd.DataFrame, title: str, tab_context: str = "") -> None:
    """Display strategy cards for bought trades on a given page with scrollable container."""
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
            bought_date = str(row.get("Bought_Date", "")).strip()
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
            
            # Format prices
            signal_price_display = f"{float(signal_price):.2f}" if pd.notna(signal_price) else "N/A"
            today_price_display = f"{float(today_price):.2f}" if pd.notna(today_price) else "N/A"
            exit_price_display = f"{float(exit_price):.2f}" if pd.notna(exit_price) and status == "Closed" else "N/A"
            
            # Create expander title
            expander_title = f"🔍 {function_name} - {symbol} | {interval} | {signal_type} | {signal_date}"
            
            with st.expander(expander_title, expanded=False):
                # Remove button at the top
                remove_key = f"remove_bought_{tab_context}_{card_num}_{idx}"
                if st.button("🗑️ Remove from Bought", key=remove_key, type="secondary"):
                    # Remove this trade from bought list
                    records = _load_bought_from_csv(TRADES_BOUGHT_CSV)
                    # Find and remove the matching record
                    dedup_key = row.get("Dedup_Key", "")
                    if dedup_key:
                        records = [r for r in records if r.get("Dedup_Key") != dedup_key]
                    else:
                        # Fallback: match by multiple fields
                        records = [
                            r for r in records
                            if not (
                                r.get("Symbol") == symbol
                                and r.get("Signal_Date") == signal_date
                                and r.get("Function") == function_name
                                and r.get("Interval") == interval
                            )
                        ]
                    _save_bought_to_csv(TRADES_BOUGHT_CSV, records)
                    st.success(f"Removed {symbol} from bought trades")
                    st.rerun()
                
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
                    st.write(f"**Bought Date:** {bought_date}")
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


def show_trades_bought() -> None:
    """Streamlit page: Trades Bought."""
    st.title("🛒 Trades Bought")
    st.markdown("---")

    # Load data
    bought_records = _load_bought_from_csv(TRADES_BOUGHT_CSV)

    if not bought_records:
        st.info("No bought trades yet. Use the 'Buy' button on Potential Entry/Exit cards to add trades here.")
        return

    df_bought = _prepare_dataframe(bought_records)

    # Sidebar controls
    st.sidebar.markdown("### 🔧 Controls (Bought Trades)")

    if st.sidebar.button(
        "🔄 Update Prices (Bought)",
        key="update_bought_prices_btn",
        help="Fetch latest prices for all bought trades",
    ):
        total_records = len(df_bought)
        if total_records == 0:
            st.sidebar.warning("No bought trades to update.")
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
                _update_bought_prices(progress_callback=on_progress)
                progress_bar.progress(1.0, text="Done!")
                progress_placeholder.success("✅ Prices updated for bought trades.")
            except Exception as e:
                progress_placeholder.error(f"Update failed: {e}")
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 🔍 Filters")

    # Function filter
    available_functions = sorted(
        [f for f in df_bought["Function"].dropna().unique() if str(f).strip()]
    )
    all_functions_label = "All Functions"
    function_options = [all_functions_label] + available_functions

    selected_functions = st.sidebar.multiselect(
        "Select Functions",
        options=function_options,
        default=function_options,
        key="bought_functions_multiselect",
        help=f"Choose one or more functions. Select '{all_functions_label}' to include all.",
    )

    if all_functions_label in selected_functions or not selected_functions:
        active_functions = available_functions
    else:
        active_functions = [f for f in selected_functions if f in available_functions]

    # Symbol filter
    available_symbols = sorted(
        [s for s in df_bought["Symbol"].dropna().unique() if str(s).strip()]
    )
    all_symbols_label = "All Symbols"
    symbol_options = [all_symbols_label] + available_symbols

    selected_symbols = st.sidebar.multiselect(
        "Select Symbols",
        options=symbol_options,
        default=symbol_options,
        key="bought_symbols_multiselect",
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
        key="bought_win_rate_slider",
    )

    # Sharpe ratio filter
    min_sharpe_ratio = st.sidebar.slider(
        "Min Strategy Sharpe Ratio",
        min_value=float(SHARPE_SLIDER_MIN),
        max_value=float(SHARPE_SLIDER_MAX),
        value=float(DEFAULT_MIN_SHARPE),
        step=0.1,
        help="Minimum Strategy Sharpe Ratio threshold",
        key="bought_sharpe_slider",
    )

    # Apply filters
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

    df_bought_f = _apply_filters(df_bought)

    st.subheader("🛒 Bought Trades")
    if df_bought_f.empty:
        st.info("No bought trades match the current filters.")
    else:
        # Sort newest first by Bought_Date if present, else Signal_Date
        if "Bought_Date" in df_bought_f.columns:
            df_bought_f = df_bought_f.sort_values(
                by="Bought_Date", ascending=False, na_position="last"
            )
        elif "Signal_Date" in df_bought_f.columns:
            df_bought_f = df_bought_f.sort_values(
                by="Signal_Date", ascending=False, na_position="last"
            )
        
        # Summary metrics
        display_monitored_trades_metrics(df_bought_f, "All Intervals", "Bought Trades")
        
        # Strategy cards
        st.markdown("---")
        create_bought_strategy_cards(df_bought_f, "Bought Trades", "bought")
        
        # Detailed table
        st.markdown("---")
        st.markdown("### 📋 Detailed Data Table — Bought Trades")
        display_trades_table_bought(df_bought_f, "Bought Trades")
