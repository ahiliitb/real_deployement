import streamlit as st
import hashlib
import pandas as pd
from config import CARDS_PER_PAGE, SCROLLABLE_CONTAINER_CSS
from utils.helpers import (
    parse_symbol_signal_info, parse_interval_info,
    parse_win_rate_info, parse_exit_signal_info, generate_unique_hash
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

            # Handle different data structures (CSV vs Monitored signals)
            if "Monitored" in page_name:
                # Monitored signals have a different structure with capitalized keys
                symbol = row.get('Symbol', 'Unknown')
                signal_type = row.get('Signal_Type', 'Unknown')
                signal_date = row.get('Signal_Date', 'Unknown')
                signal_price = str(row.get('Signal_Price', 'N/A'))
                win_rate = row.get('Win_Rate_Display', row.get('Win_Rate', 'N/A'))
                current_mtm = row.get('Current_MTM', 'N/A')
                strategy_cagr = row.get('Strategy_CAGR', 'N/A')
                strategy_sharpe = row.get('Strategy_Sharpe', 'N/A')
                backtested_returns = row.get('Backtested_Returns', 'N/A')
                targets_info = row.get('Targets', 'N/A')
                holding_period_info = row.get('Holding_Period', 'N/A')
                function_name = row.get('Function', 'Monitored')
                interval_display = row.get('Interval', 'Monitored')
                trendpulse_start_end = row.get('trendpulse_start_end', None)

                expander_title = f"🔍 {function_name} - {symbol} | {interval_display} | {signal_type} | {signal_date}"
            else:
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
                # Extract numeric win rate for calculations
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
                    # Trendline CSV structure
                    cagr_col = 18  # Backtested Strategy CAGR [%]
                    sharpe_col = 21  # Backtested Strategy Sharpe Ratio
                    holding_col = 16  # Backtested Holding Period(Win Trades) (days) (Max/Min/Avg)
                    targets_col = 23  # Targets column
                    returns_col = 14  # Backtested Returns
                else:
                    # Distance CSV structure
                    cagr_col = 12  # Backtested Strategy CAGR [%]
                    sharpe_col = 15  # Backtested Strategy Sharpe Ratio
                    holding_col = 10  # Backtested Holding Period(Win Trades) (days) (Max/Min/Avg)
                    targets_col = 17  # Targets column
                    returns_col = 8   # Backtested Returns

                # Backtested Returns(Win Trades) [%] (Max/Min/Avg) - show full Max/Min/Avg
                backtested_returns = str(row.iloc[returns_col]) if len(row) > returns_col else "N/A"
                if backtested_returns == 'nan':
                    backtested_returns = "N/A"

                # Backtested Strategy CAGR [%]
                strategy_cagr = "N/A"
                if len(row) > cagr_col and str(row.iloc[cagr_col]) != 'nan':
                    try:
                        cagr_value = str(row.iloc[cagr_col]).strip('%')
                        strategy_cagr = f"{float(cagr_value):.2f}%"
                    except (ValueError, TypeError):
                        strategy_cagr = "N/A"

                # Backtested Strategy Sharpe Ratio
                strategy_sharpe = "N/A"
                if len(row) > sharpe_col and str(row.iloc[sharpe_col]) != 'nan':
                    try:
                        strategy_sharpe = f"{float(row.iloc[sharpe_col]):.2f}"
                    except (ValueError, TypeError):
                        strategy_sharpe = "N/A"

                # Backtested Holding Period(Win Trades) (days) (Max/Min/Avg)
                holding_period_info = str(row.iloc[holding_col]) if len(row) > holding_col else ""
                if holding_period_info == 'nan':
                    holding_period_info = "N/A"

                # Targets column
                targets_info = str(row.iloc[targets_col]) if len(row) > targets_col else "N/A"
                if targets_info == 'nan':
                    targets_info = "N/A"

                # TrendPulse info for trendline signals
                trendpulse_start_end = None
                if "Trendline" in page_name:
                    trendpulse_start_end_col = 13
                    if len(row) > trendpulse_start_end_col:
                        trendpulse_start_end = str(row.iloc[trendpulse_start_end_col])
                        if trendpulse_start_end == 'nan':
                            trendpulse_start_end = None

                function_name = "Trendline" if "Trendline" in page_name else "Distance"
                expander_title = f"🔍 {function_name} - {symbol} | {interval_display} | {signal_type} | {signal_date}"

            with st.expander(expander_title, expanded=False):
                st.markdown("**📋 Key Trade Information**")

                # Create unique identifier for buttons
                unique_str = f"{page_name}_{tab_context}_{card_num}_{symbol}_{signal_date}_{interval_display}_{signal_type}_{idx}"
                unique_hash = generate_unique_hash(unique_str)

                # Button logic - different for monitored vs regular signals
                if "Monitored" in page_name:
                    # Remove from Monitored button for monitored signals
                    remove_key = f"remove_monitored_{unique_hash}_{card_num}"
                    if st.button("🗑️ Remove from Monitored", key=remove_key, type="secondary"):
                        from page_functions.monitored_signals import remove_signal_from_monitored
                        if remove_signal_from_monitored(card_num):
                            st.success(f"✅ Removed {symbol} from Monitored Signals!")
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to remove signal")
                else:
                    # Add to Monitored button for regular signals
                    button_key = f"add_monitored_{unique_hash}_{card_num}"
                    if st.button("⭐ Add to Monitored", key=button_key, help="Add this signal to monitored signals"):
                        # Import here to avoid circular imports
                        from page_functions.monitored_signals import add_signal_to_monitored

                        # Prepare comprehensive signal data for monitoring
                        # Convert prices to numeric values
                        try:
                            numeric_signal_price = float(signal_price) if signal_price != 'N/A' and signal_price != '' else None
                        except (ValueError, TypeError):
                            numeric_signal_price = None

                        try:
                            numeric_win_rate = float(win_rate) if win_rate != 'N/A' and win_rate != '' and win_rate is not None else None
                        except (ValueError, TypeError):
                            numeric_win_rate = None

                        # Parse exit date/price from CSV when trade has already exited (column 1: Exit Signal Date/Price)
                        exit_date_parsed, exit_price_parsed = None, None
                        if len(row) > 1:
                            exit_date_parsed, exit_price_parsed = parse_exit_signal_info(row.iloc[1])

                        # Signal Open Price from last column (both Distance and Trendline CSVs) - distinct from Signal_Price
                        numeric_signal_open_price = None
                        if len(row) > 0:
                            try:
                                raw_open = row.iloc[-1]
                                if raw_open is not None and str(raw_open).strip() not in ('', 'nan'):
                                    numeric_signal_open_price = float(str(raw_open).strip())
                            except (ValueError, TypeError):
                                pass

                        signal_data = {
                            'Symbol': symbol,
                            'Signal_Type': signal_type,
                            'Signal_Date': signal_date,
                            'Signal_Price': numeric_signal_price,       # Price from signal date (first col)
                            'Signal_Open_Price': numeric_signal_open_price,  # Entry price (last col) - distinct
                            'Win_Rate': numeric_win_rate,  # Numeric backtested win rate for calculations
                            'Win_Rate_Display': win_rate_display,  # Display version with %
                            'Current_Price': None,  # Will be updated later
                            'Exit_Price': exit_price_parsed,     # From CSV when trade already exited
                            'Exit_Date': exit_date_parsed,      # From CSV when trade already exited
                            'Current_MTM': current_mtm,
                            'Strategy_CAGR': strategy_cagr,
                            'Strategy_Sharpe': strategy_sharpe,
                            'Backtested_Returns': backtested_returns,
                            'Targets': targets_info,
                            'Holding_Period': holding_period_info,
                            'Function': function_name,
                            'Interval': interval_display,
                            'Raw_Data': row.to_dict() if hasattr(row, 'to_dict') else {}
                        }
                        # Use 4 fundamentals from row when present (Trendline/Distance enriched CSV) — no recalculation when adding to monitored
                        if "PE_Ratio" in row.index:
                            signal_data['PE_Ratio'] = row.get("PE_Ratio", "N/A")
                            signal_data['Industry_PE'] = row.get("Industry_PE", "N/A")
                            signal_data['Last_Quarter_Profit'] = row.get("Last_Quarter_Profit", "N/A")
                            signal_data['Last_Year_Same_Quarter_Profit'] = row.get("Last_Year_Same_Quarter_Profit", "N/A")

                        if trendpulse_start_end:
                            signal_data['trendpulse_start_end'] = trendpulse_start_end

                        if add_signal_to_monitored(signal_data):
                            st.success(f"✅ Added {symbol} to Monitored Signals!")
                        else:
                            st.warning(f"⚠️ {symbol} is already in Monitored Signals")


                # Fundamentals: from row only (Monitored + Trendline/Distance; Trendline/Distance get 4 cols from enrich script at update_trade time)
                fundamentals = None
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

                    if "Monitored" not in page_name:
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
                    if fundamentals:
                        pe = fundamentals.get("PE_Ratio", "N/A")
                        ind_pe = fundamentals.get("Industry_PE", "N/A")
                        last_q = fundamentals.get("Last_Quarter_Profit", "N/A")
                        same_q = fundamentals.get("Last_Year_Same_Quarter_Profit", "N/A")
                        st.write(f"**PE Ratio:** {_format_fundamental_value(pe)}")
                        st.write(f"**Industry PE:** {_format_fundamental_value(ind_pe)}")
                        st.write(f"**Last Quarter Profit (Net Inc):** {_format_fundamental_value(last_q)}")
                        st.write(f"**Same Qtr Prior Yr (Net Inc):** {_format_fundamental_value(same_q)}")
                    else:
                        st.write("No Data")