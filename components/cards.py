import streamlit as st
import pandas as pd
from config import CARDS_PER_PAGE, SCROLLABLE_CONTAINER_CSS
from utils.helpers import (
    parse_symbol_signal_info,
    parse_interval_info,
    parse_win_rate_info,
)


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


def create_strategy_cards(df, page_name="Unknown", tab_context=""):
    """Create individual strategy cards with pagination for large datasets"""
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
        display_strategy_cards_page(df, page_name, tab_context)
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

                display_strategy_cards_page(page_df, page_name, pagination_context)

def display_strategy_cards_page(df, page_name="Unknown", tab_context=""):
    """Display strategy cards for a given page with scrollable container"""
    if len(df) == 0:
        st.warning("No data to display on this page.")
        return

    # Add custom CSS for scrollable container
    st.markdown(SCROLLABLE_CONTAINER_CSS, unsafe_allow_html=True)

    # Create scrollable container for cards (30 per tab, same height — scroll to see all)
    with st.container(height=600, border=True):
        # Display strategy cards in scrollable area
        for card_num, (idx, row) in enumerate(df.iterrows()):
            # Initialize variables
            trendpulse_start_end = None

            # Parse the CSV data properly from the columns
            # Column 0: Symbol, Signal, Signal Date/Price[$]
            symbol_signal_info = str(row.iloc[0]) if len(row) > 0 else ""
            symbol, signal_type, signal_date, signal_price = parse_symbol_signal_info(symbol_signal_info)

            # Column 4: Interval, Confirmation Status
            interval_info = str(row.iloc[4]) if len(row) > 4 else ""
            interval_display = parse_interval_info(interval_info)

            # Column 3: Win Rate [%], History Tested, Number of Trades
            win_rate_info = str(row.iloc[3]) if len(row) > 3 else ""
            win_rate_display = parse_win_rate_info(win_rate_info)
            try:
                win_rate = float(win_rate_display.rstrip('%')) if win_rate_display != "N/A" else None
            except (ValueError, AttributeError):
                win_rate = None

            # Column 2: Current Mark to Market and Holding Period
            current_mtm = str(row.iloc[2]) if len(row) > 2 else "N/A"
            if current_mtm == 'nan':
                current_mtm = "N/A"

            # Determine column indices based on page type (Trendline vs Distance have different structures)
            if "Trendline" in page_name:
                cagr_col, sharpe_col, holding_col, targets_col, returns_col = 18, 21, 16, 23, 14
            else:
                cagr_col, sharpe_col, holding_col, targets_col, returns_col = 12, 15, 10, 17, 8

            backtested_returns = str(row.iloc[returns_col]) if len(row) > returns_col else "N/A"
            if backtested_returns == 'nan':
                backtested_returns = "N/A"

            strategy_cagr = "N/A"
            if len(row) > cagr_col and str(row.iloc[cagr_col]) != 'nan':
                try:
                    strategy_cagr = f"{float(str(row.iloc[cagr_col]).strip('%')):.2f}%"
                except (ValueError, TypeError):
                    pass

            strategy_sharpe = "N/A"
            if len(row) > sharpe_col and str(row.iloc[sharpe_col]) != 'nan':
                try:
                    strategy_sharpe = f"{float(row.iloc[sharpe_col]):.2f}"
                except (ValueError, TypeError):
                    pass

            holding_period_info = str(row.iloc[holding_col]) if len(row) > holding_col else ""
            if holding_period_info == 'nan':
                holding_period_info = "N/A"

            targets_info = str(row.iloc[targets_col]) if len(row) > targets_col else "N/A"
            if targets_info == 'nan':
                targets_info = "N/A"

            if "Trendline" in page_name and len(row) > 13:
                tp = str(row.iloc[13])
                trendpulse_start_end = None if tp == 'nan' else tp
            else:
                trendpulse_start_end = None

            function_name = "Trendline" if "Trendline" in page_name else "Distance"
            expander_title = f"🔍 {function_name} - {symbol} | {interval_display} | {signal_type} | {signal_date}"

            with st.expander(expander_title, expanded=False):
                st.markdown("**📋 Key Trade Information**")

                fundamentals = {
                    "PE_Ratio": row.get("PE_Ratio", "N/A"),
                    "Industry_PE": row.get("Industry_PE", "N/A"),
                    "Last_Quarter_Profit": row.get("Last_Quarter_Profit", "N/A"),
                    "Last_Year_Same_Quarter_Profit": row.get("Last_Year_Same_Quarter_Profit", "N/A"),
                }

                # Create four columns when we have fundamentals
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.markdown("**🎯 Trade Details**")
                    st.write(f"**Symbol:** {symbol}")
                    st.write(f"**Function:** {function_name}")
                    st.write(f"**Interval:** {interval_display}")
                    st.write(f"**Signal:** {signal_type}")
                    st.write(f"**Signal Date:** {signal_date}")
                    st.write(f"**Signal Price:** {signal_price}")
                    st.write(f"**Win Rate:** {win_rate}")

                with col2:
                    st.markdown("**📊 Status & Performance**")

                    st.write(f"**Current MTM:** {current_mtm}")
                    st.write(f"**Strategy CAGR:** {strategy_cagr}")
                    st.write(f"**Strategy Sharpe:** {strategy_sharpe}")
                    st.write(f"**Backtested Returns:** {backtested_returns}")

                with col3:
                    st.markdown("**⚠️ Risk & Timing**")

                    st.write(f"**Targets:** {targets_info}")
                    st.write(f"**Holding Period:** {holding_period_info}")

                    # Add TrendPulse Start/End information for Trendline signals
                    if trendpulse_start_end:
                        st.write(f"**TrendPulse Start/End:** {trendpulse_start_end}")

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