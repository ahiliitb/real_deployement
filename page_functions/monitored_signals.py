"""
Monitored Trades Page - Personal Portfolio Analysis
Displays and manages user's monitored trades with daily price updates
Similar structure to Virtual Trading page
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
import os
import yfinance as yf
import time

from config import TRADE_DEDUP_COLUMNS

# CSV file for persistent storage of monitored signals
MONITORED_TRADES_CSV = "trade_store/INDIA/monitored_trades.csv"

def load_monitored_signals_from_csv():
    """Load monitored signals from CSV file"""
    try:
        if not os.path.exists(MONITORED_TRADES_CSV):
            os.makedirs(os.path.dirname(MONITORED_TRADES_CSV), exist_ok=True)
            return []
        # Handle empty file (e.g. after saving empty list) — pandas raises EmptyDataError
        if os.path.getsize(MONITORED_TRADES_CSV) == 0:
            return []
        try:
            df = pd.read_csv(MONITORED_TRADES_CSV)
        except pd.errors.EmptyDataError:
            return []
        if df.empty or len(df.columns) == 0:
            return []
        # Convert to list of dictionaries
        signals = df.to_dict('records')
        # Convert numeric columns
        for signal in signals:
            for key in ['Signal_Price', 'Signal_Open_Price', 'Current_Price', 'Exit_Price', 'Win_Rate', 'Strategy_Sharpe']:
                if key in signal and pd.notna(signal[key]):
                    try:
                        signal[key] = float(signal[key])
                    except (ValueError, TypeError):
                        pass
        return signals
    except Exception as e:
        st.error(f"Error loading monitored signals: {e}")
        return []

# Column order for monitored CSV (used when saving empty list so file stays readable)
MONITORED_CSV_COLUMNS = [
    "Symbol", "Signal_Type", "Signal_Date", "Signal_Price", "Signal_Open_Price",
    "Win_Rate", "Win_Rate_Display", "Current_Price", "Exit_Price", "Exit_Date",
    "Current_MTM", "Strategy_CAGR", "Strategy_Sharpe", "Backtested_Returns",
    "Targets", "Holding_Period", "Function", "Interval", "Raw_Data",
    "PE_Ratio", "Industry_PE", "Last_Quarter_Profit", "Last_Year_Same_Quarter_Profit",
]

def save_monitored_signals_to_csv(signals):
    """Save monitored signals to CSV file"""
    try:
        if not signals:
            # Write header-only CSV so load_monitored_signals_from_csv can read it back
            df = pd.DataFrame(columns=MONITORED_CSV_COLUMNS)
        else:
            df = pd.DataFrame(signals)
        df.to_csv(MONITORED_TRADES_CSV, index=False)
        return True
    except Exception as e:
        st.error(f"Error saving monitored signals: {e}")
        return False

def get_trade_dedup_key(signal_data):
    """Build deduplication key from TRADE_DEDUP_COLUMNS"""
    parts = []
    for col in TRADE_DEDUP_COLUMNS:
        val = str(signal_data.get(col, '')).strip()
        if col == 'Signal_Type':
            val = 'SHORT' if 'SHORT' in val.upper() else 'LONG'
        parts.append(val)
    return "|".join(parts)


def add_signal_to_monitored(signal_data):
    """Add a signal to the monitored list and save to CSV"""
    signals = load_monitored_signals_from_csv()

    current_key = get_trade_dedup_key(signal_data)

    for existing in signals:
        existing_key = get_trade_dedup_key(existing)
        if existing_key == current_key:
            return False  # Already exists

    # Current price: fetch live. Fundamentals (PE_Ratio, etc.): never refetched here — use only what's in signal_data (from Trendline/Distance row when adding from cards)
    symbol = signal_data.get('Symbol', '').strip()
    if symbol:
        current_price = fetch_current_price_yfinance(symbol)
        if current_price is not None:
            signal_data['Current_Price'] = current_price
            print(f"Set current price for {symbol}: ${current_price:.2f}")

    signals.append(signal_data)
    return save_monitored_signals_to_csv(signals)

def remove_signal_from_monitored(signal_index):
    """Remove a signal from the monitored list and update CSV"""
    signals = load_monitored_signals_from_csv()

    if 0 <= signal_index < len(signals):
        removed_signal = signals.pop(signal_index)
        save_monitored_signals_to_csv(signals)
        return True
    return False


def remove_signals_from_monitored_by_indices(indices_to_remove):
    """Remove multiple signals by their list indices and save CSV once."""
    if not indices_to_remove:
        return 0
    signals = load_monitored_signals_from_csv()
    # Remove in descending order so indices stay valid
    for idx in sorted(indices_to_remove, reverse=True):
        if 0 <= idx < len(signals):
            signals.pop(idx)
    save_monitored_signals_to_csv(signals)
    return len(indices_to_remove)

def fetch_additional_stock_data(symbol):
    """Fetch additional financial data for a stock symbol using yfinance"""
    try:
        # Add delay to avoid rate limiting
        time.sleep(0.5)

        ticker = yf.Ticker(symbol)

        # Get basic info
        info = ticker.info

        # PE Ratio
        pe_ratio = info.get('trailingPE') or info.get('forwardPE') or 'N/A'

        # Industry/Sector for Industry PE calculation
        industry = info.get('industry', 'Unknown')
        sector = info.get('sector', 'Unknown')

        # Calculate Industry PE (simplified approach with predefined averages)
        industry_pe_ratios = {
            # Technology
            'Semiconductors': 25.0, 'Software': 30.0, 'Consumer Electronics': 20.0,
            'Computer Hardware': 22.0, 'Information Technology Services': 28.0,

            # Healthcare
            'Biotechnology': 35.0, 'Drug Manufacturers': 18.0, 'Medical Devices': 25.0,
            'Healthcare Plans': 15.0, 'Medical Diagnostics & Research': 30.0,

            # Financial Services
            'Banks': 12.0, 'Insurance': 14.0, 'Asset Management': 16.0,
            'Credit Services': 10.0, 'Capital Markets': 18.0,

            # Consumer Goods
            'Beverages': 20.0, 'Food': 18.0, 'Household & Personal Products': 22.0,
            'Tobacco': 15.0, 'Apparel': 25.0,

            # Energy
            'Oil & Gas': 8.0, 'Utilities': 16.0,

            # Industrials
            'Aerospace': 20.0, 'Engineering': 22.0, 'Manufacturing': 18.0,

            # Default
            'Unknown': 20.0
        }

        industry_pe = industry_pe_ratios.get(industry, industry_pe_ratios.get(sector, 20.0))

        # Get quarterly financials for profit data
        quarterly_financials = ticker.quarterly_financials

        last_quarter_profit = 'N/A'
        last_year_same_quarter_profit = 'N/A'

        if not quarterly_financials.empty and 'Net Income' in quarterly_financials.index:
            net_income_series = quarterly_financials.loc['Net Income']

            # Find last available quarter with valid Net Income (e.g. if Q3 has no data, use Q2)
            last_available_idx = None
            for i in range(len(net_income_series)):
                val = net_income_series.iloc[i]
                if pd.notna(val) and str(val).strip() not in ('', 'nan', 'N/A'):
                    try:
                        float(val)
                        last_available_idx = i
                        break
                    except (ValueError, TypeError):
                        continue

            if last_available_idx is not None:
                last_quarter_profit = net_income_series.iloc[last_available_idx]
                # Same fiscal quarter, prior year (4 quarters back from last_available)
                prior_year_idx = last_available_idx + 4
                if prior_year_idx < len(net_income_series):
                    last_year_same_quarter_profit = net_income_series.iloc[prior_year_idx]

        # Convert 'N/A' and NaN to 'No Data' for consistency
        def clean_value(val):
            if val == 'N/A' or (hasattr(val, 'isna') and val.isna()) or str(val).lower() == 'nan':
                return 'No Data'
            return val

        result = {
            'PE_Ratio': clean_value(pe_ratio),
            'Industry_PE': clean_value(industry_pe),
            'Last_Quarter_Profit': clean_value(last_quarter_profit),
            'Last_Year_Same_Quarter_Profit': clean_value(last_year_same_quarter_profit)
        }

        return result

    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return {
            'PE_Ratio': 'No Data',
            'Industry_PE': 'No Data',
            'Last_Quarter_Profit': 'No Data',
            'Last_Year_Same_Quarter_Profit': 'No Data'
        }

def fetch_current_price_yfinance(symbol):
    """Fetch current/latest price for a symbol using yfinance API. Returns float or None."""
    if not symbol or not str(symbol).strip():
        return None
    symbol = str(symbol).strip()
    try:
        time.sleep(0.3)  # Avoid rate limiting
        ticker = yf.Ticker(symbol)
        # Prefer fast_info for speed; fallback to info or history
        try:
            fast = getattr(ticker, 'fast_info', None)
            if fast is not None:
                last = getattr(fast, 'last_price', None)
                if last is not None and not (hasattr(last, 'isna') and last.isna()):
                    return float(last)
        except Exception:
            pass
        info = ticker.info
        for key in ('regularMarketPrice', 'currentPrice', 'previousClose'):
            val = info.get(key)
            if val is not None and not (hasattr(val, 'isna') and val.isna()):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        hist = ticker.history(period="5d")
        if not hist.empty and 'Close' in hist.columns:
            return float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"Warning: Could not fetch price for {symbol}: {e}")
    return None


def update_monitored_signal_prices(progress_callback=None):
    """Update current prices for all monitored signals using yfinance API.

    progress_callback: optional callable(processed, total, symbol, success, price).
                       Called after each symbol; processed/total are 1-based counts.
    """
    signals = load_monitored_signals_from_csv()
    total = len(signals)
    updated_count = 0
    processed = 0

    for signal in signals:
        symbol = signal.get('Symbol', '').strip()
        if not symbol:
            if progress_callback and total:
                processed += 1
                progress_callback(processed, total, symbol or "(empty)", False, None)
            continue
        price = fetch_current_price_yfinance(symbol)
        success = price is not None
        if success:
            signal['Current_Price'] = price
            updated_count += 1
            print(f"Updated {symbol}: ${price:.2f}")
        else:
            print(f"❌ Could not fetch price for {symbol} - price not updated")
        processed += 1
        if progress_callback:
            progress_callback(processed, total, symbol, success, price)

    if updated_count == 0 and total > 0:
        raise ValueError(
            "No symbols could be updated. Check internet connection and that symbols are valid (e.g. AAPL, MSFT)."
        )

    save_monitored_signals_to_csv(signals)
    print(f"✅ Updated prices for {updated_count} symbols via yfinance")

def show_monitored_signals():
    """Show the monitored trading signals page"""
    # Info button at the top
    if st.button("ℹ️ Info About Page", key="info_monitored_trades", help="Click to learn about this page"):
        st.session_state['show_info_monitored_trades'] = not st.session_state.get('show_info_monitored_trades', False)

    if st.session_state.get('show_info_monitored_trades', False):
        with st.expander("📖 Monitored Trades Information", expanded=True):
            st.markdown("""
            ### What is this page?
            The Monitored Trades page is your personal portfolio tracker where you can add and monitor specific trades that interest you.

            ### Why is it used?
            - **Personal Tracking**: Monitor trades you're personally interested in or invested in
            - **Portfolio Management**: Keep track of your selected positions in one place
            - **Price Updates**: Get live price updates via yfinance when you click Update Prices
            - **Performance Analysis**: Track individual trade performance over time

            ### How to use?
            1. **Add Trades**: Use the "⭐ Add to Monitored" button on Outstanding Signals or New Signals pages
            2. **Update Prices**: Click "🔄 Update Prices" in sidebar to fetch current prices via yfinance
            3. **View Status**: Switch between All Trades, Open Trades, and Closed Trades tabs
            4. **Apply Filters**: Use sidebar filters to focus on specific functions, symbols, or intervals
            5. **Remove Trades**: Remove trades you no longer want to monitor

            ### Key Features:
            - Personal portfolio tracking
            - Live price updates via yfinance API
            - Integration with outstanding signals for exit detection
            - Open vs closed trade segregation
            - Real-time profit/loss tracking
            - Customizable watchlist
            """)

    st.title("⭐ Monitored Trades")

    # Display data fetch datetime at top of page
    st.markdown("### Personal Portfolio Analysis")
    st.markdown("---")

    # Load monitored trades from CSV
    monitored_signals = load_monitored_signals_from_csv()

    if not monitored_signals:
        st.info("📋 No monitored trades yet. Add trades from the 'Outstanding Signals' or 'New Signals' page using the '⭐ Add to Monitored' button.")
        return

    # Convert monitored signals to DataFrame for display
    df = pd.DataFrame(monitored_signals)

    # Ensure all signals have proper data types
    for signal in monitored_signals:
        # Convert prices to numeric if they're strings
        if 'Signal_Price' in signal and signal['Signal_Price'] is not None:
            try:
                if isinstance(signal['Signal_Price'], str):
                    signal['Signal_Price'] = float(signal['Signal_Price']) if signal['Signal_Price'] != 'N/A' else None
            except (ValueError, TypeError):
                signal['Signal_Price'] = None

        if 'Win_Rate' in signal and signal['Win_Rate'] is not None:
            try:
                if isinstance(signal['Win_Rate'], str):
                    signal['Win_Rate'] = float(signal['Win_Rate'].strip('%')) if signal['Win_Rate'] != 'N/A' else None
            except (ValueError, TypeError):
                signal['Win_Rate'] = None

    # Re-create DataFrame with updated data
    df = pd.DataFrame(monitored_signals)

    # Sidebar controls
    st.sidebar.markdown("### 🔧 Controls")

    # Update prices button
    if st.sidebar.button("🔄 Update Prices", help="Fetch current prices via yfinance API"):
        total = len(load_monitored_signals_from_csv())
        if total == 0:
            st.sidebar.warning("No monitored trades to update.")
        else:
            progress_placeholder = st.sidebar.empty()
            progress_bar = st.sidebar.progress(0, text="Starting...")
            status_text = st.sidebar.empty()

            def on_progress(processed, total_n, symbol, success, price):
                pct = processed / total_n if total_n else 0
                progress_bar.progress(pct, text=f"Updating {processed}/{total_n}")
                if success and price is not None:
                    status_text.caption(f"✓ {symbol}: ${price:.2f} — {processed} of {total_n} updated")
                else:
                    status_text.caption(f"— {symbol}: no price — {processed}/{total_n} processed")

            try:
                update_monitored_signal_prices(progress_callback=on_progress)
                progress_bar.progress(1.0, text="Done!")
                status_text.caption(f"✅ All done — {total} signals processed.")
                progress_placeholder.success("✅ Prices updated!")
            except Exception as e:
                progress_placeholder.error(f"Update failed: {e}")
            st.rerun()

    # Prepare data - determine open/closed status
    df['Status'] = df.apply(
        lambda row: 'Closed' if pd.notna(row.get('Exit_Date')) and str(row.get('Exit_Date')).strip() else 'Open',
        axis=1
    )

    # Ensure numeric columns are properly typed
    numeric_cols = ['Signal_Price', 'Current_Price', 'Exit_Price', 'Win_Rate', 'Strategy_Sharpe']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Handle Win_Rate_Display as string
    if 'Win_Rate_Display' in df.columns:
        df['Win_Rate_Display'] = df['Win_Rate_Display'].fillna('N/A')

    # Note: Current prices should be set by the update script
    # If no current price is available, calculations will use available data or show N/A
    # No random/demo prices are generated

    # Ensure required columns exist
    if 'Interval' in df.columns:
        df['Interval'] = df['Interval'].fillna('Unknown')
    else:
        df['Interval'] = 'Unknown'

    if 'Function' in df.columns:
        df['Function'] = df['Function'].fillna('Unknown')
    else:
        df['Function'] = 'Unknown'

    if 'Symbol' in df.columns:
        df['Symbol'] = df['Symbol'].fillna('')
    else:
        df['Symbol'] = ''

    if 'Signal_Type' in df.columns:
        df['Signal_Type'] = df['Signal_Type'].fillna('Unknown')
    else:
        df['Signal_Type'] = 'Unknown'

    # Determine position type (Long/Short)
    df['Position'] = df['Signal_Type'].apply(
        lambda x: 'Long' if str(x).upper() == 'LONG' else ('Short' if str(x).upper() == 'SHORT' else 'Long')
    )

    # Main tabs for trade status
    main_tab1, main_tab2, main_tab3 = st.tabs(["📊 All Trades", "Open Trades", "Closed Trades"])

    # Sidebar filters
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 🔍 Filters")

    # Function filter
    st.sidebar.markdown("**Functions:**")
    available_functions = sorted(df['Function'].unique())

    all_functions_label = "All Functions"
    function_options_with_all = [all_functions_label] + list(available_functions)

    if 'selected_functions_mt' not in st.session_state:
        st.session_state['selected_functions_mt'] = list(available_functions)

    stored_functions = st.session_state.get('selected_functions_mt', list(available_functions))
    valid_stored_functions = [f for f in stored_functions if f in available_functions]

    functions = st.sidebar.multiselect(
        "Select Functions",
        options=function_options_with_all,
        default=valid_stored_functions,
        key="functions_multiselect_mt",
        help=f"Choose one or more functions. Select '{all_functions_label}' to include all."
    )

    if all_functions_label in functions or not functions:
        st.session_state['selected_functions_mt'] = list(available_functions)
    else:
        st.session_state['selected_functions_mt'] = [f for f in functions if f in available_functions]

    functions = st.session_state['selected_functions_mt']

    # Symbol filter
    st.sidebar.markdown("**Symbols:**")
    available_symbols = sorted(df['Symbol'].unique())

    all_symbols_label = "All Symbols"
    symbol_options_with_all = [all_symbols_label] + list(available_symbols)

    if 'selected_symbols_mt' not in st.session_state:
        st.session_state['selected_symbols_mt'] = list(available_symbols)

    stored_symbols = st.session_state.get('selected_symbols_mt', list(available_symbols))
    valid_stored_symbols = [s for s in stored_symbols if s in available_symbols]

    symbols = st.sidebar.multiselect(
        "Select Symbols",
        options=symbol_options_with_all,
        default=valid_stored_symbols,
        key="symbols_multiselect_mt",
        help=f"Choose one or more symbols. Select '{all_symbols_label}' to include all."
    )

    if all_symbols_label in symbols or not symbols:
        st.session_state['selected_symbols_mt'] = list(available_symbols)
    else:
        st.session_state['selected_symbols_mt'] = [s for s in symbols if s in available_symbols]

    symbols = st.session_state['selected_symbols_mt']

    # Win rate filter (slider) - more permissive defaults
    min_win_rate = st.sidebar.slider(
        "Min Win Rate (%)",
        min_value=0,
        max_value=100,
        value=0,  # Changed from 70 to 0 for less restrictive filtering
        help="Minimum win rate threshold",
        key="win_rate_slider_mt"
    )

    # Sharpe ratio filter - more permissive defaults
    min_sharpe_ratio = st.sidebar.slider(
        "Min Strategy Sharpe Ratio",
        min_value=-5.0,
        max_value=5.0,
        value=-5.0,  # Changed from 0.5 to -5.0 for less restrictive filtering
        step=0.1,
        help="Minimum Strategy Sharpe Ratio threshold",
        key="sharpe_ratio_slider_mt"
    )

    # Process each main tab
    with main_tab1:
        st.subheader("📊 All Trades")
        display_monitored_trades_content(df, "All Trades", functions, symbols, min_win_rate, min_sharpe_ratio)

    with main_tab2:
        st.subheader("Open Trades")
        df_open = df[df['Status'] == 'Open']
        display_monitored_trades_content(df_open, "Open Trades", functions, symbols, min_win_rate, min_sharpe_ratio)

    with main_tab3:
        st.subheader("Closed Trades")
        df_closed = df[df['Status'] != 'Open']
        display_monitored_trades_content(df_closed, "Closed Trades", functions, symbols, min_win_rate, min_sharpe_ratio)

def display_monitored_trades_content(df, tab_name, selected_functions, selected_symbols, min_win_rate, min_sharpe_ratio=-5.0):
    """Display monitored trades content with position and interval tabs"""

    if df.empty:
        st.warning(f"No data available for {tab_name}")
        return

    # Debug: Show current filter values
    # st.write(f"DEBUG - Selected functions: {selected_functions}")
    # st.write(f"DEBUG - Selected symbols: {selected_symbols}")
    # st.write(f"DEBUG - Min win rate: {min_win_rate}")
    # st.write(f"DEBUG - Min sharpe: {min_sharpe_ratio}")

    # Apply filters
    filtered_df = df[
        (df['Function'].isin(selected_functions)) &
        (df['Symbol'].isin(selected_symbols))
    ]

    # st.write(f"DEBUG - After function/symbol filter: {len(filtered_df)} rows")

    # Apply win rate filter if column exists
    if 'Win_Rate' in filtered_df.columns and min_win_rate > 0:
        filtered_df = filtered_df[filtered_df['Win_Rate'].fillna(0) >= min_win_rate]
        # st.write(f"DEBUG - After win rate filter: {len(filtered_df)} rows")

    # Apply Sharpe ratio filter if column exists
    if 'Strategy_Sharpe' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Strategy_Sharpe'].fillna(-999) >= min_sharpe_ratio]
        # st.write(f"DEBUG - After sharpe filter: {len(filtered_df)} rows")

    if filtered_df.empty:
        st.warning(f"No data matches the current filters for {tab_name}")
        # Show what filters are active
        st.info(f"Active filters: Functions={selected_functions[:3]}..., Symbols={selected_symbols[:3]}..., Min Win Rate={min_win_rate}%, Min Sharpe={min_sharpe_ratio}")
        return

    # Create position tabs (Long/Short/All)
    position_tab1, position_tab2, position_tab3 = st.tabs(["📈 Long Positions", "📉 Short Positions", "📊 ALL Positions"])

    with position_tab1:
        df_long = filtered_df[filtered_df['Position'] == 'Long']
        display_interval_tabs(df_long, "Long Positions", tab_name)

    with position_tab2:
        df_short = filtered_df[filtered_df['Position'] == 'Short']
        display_interval_tabs(df_short, "Short Positions", tab_name)

    with position_tab3:
        display_interval_tabs(filtered_df, "All Positions", tab_name)

def display_interval_tabs(df, position_name, trade_status):
    """Display interval tabs for monitored trades data"""

    if df.empty:
        st.info(f"No {position_name} available for {trade_status}")
        return

    # Get unique intervals and create tabs
    unique_intervals = sorted([i for i in df['Interval'].unique() if pd.notna(i) and str(i) != 'Unknown'])
    intervals = ['ALL Intervals'] + unique_intervals

    # Create interval tabs
    interval_tabs = st.tabs(intervals)

    for i, interval in enumerate(intervals):
        with interval_tabs[i]:
            if interval == 'ALL Intervals':
                interval_df = df
            else:
                interval_df = df[df['Interval'] == interval]

            if interval_df.empty:
                st.info(f"No data available for {interval}")
                continue

            # Display summary metrics
            display_monitored_trades_metrics(interval_df, interval, position_name)

            # Search and remove trades interface
            display_trade_removal_interface(interval_df, f"{position_name} - {interval}", f"{trade_status}_{position_name}_{interval}")

            # Display detailed data table
            st.markdown("### 📋 Detailed Data Table")
            display_trades_table(interval_df, f"{position_name} - {interval}")

def display_trade_removal_interface(df, title, unique_key_suffix=""):
    """Display select interface for removing trades"""
    st.markdown("### 🗑️ Remove Trades")

    if df.empty:
        st.info("No trades available to remove")
        return

    # Create unique identifiers for each trade
    trade_options = []
    trade_id_to_index = {}

    for idx, row in df.iterrows():
        symbol = row.get('Symbol', 'Unknown')
        signal_type = row.get('Signal_Type', 'Unknown')
        signal_date = row.get('Signal_Date', 'Unknown')
        function = row.get('Function', 'Unknown')
        interval = row.get('Interval', 'Unknown')

        # Create a readable option name
        option_name = f"{symbol} | {function} | {signal_type} | {interval} | {signal_date}"
        trade_options.append(option_name)
        trade_id_to_index[option_name] = idx

    # Create unique keys using the suffix
    base_key = f"select_trades_{title.replace(' ', '_')}_{unique_key_suffix.replace(' ', '_')}"

    # Multiselect for trades to remove
    selected_trades = st.multiselect(
        "Select trades to remove:",
        options=trade_options,
        default=[],
        key=base_key,
        help="Select one or more trades to remove from monitored list"
    )

    # Session state key for pending removal (so confirmation works across reruns)
    pending_key = f"pending_removal_{unique_key_suffix.replace(' ', '_')}"

    # Remove button: store pending indices and rerun so user can confirm
    remove_button_key = f"remove_button_{title.replace(' ', '_')}_{unique_key_suffix.replace(' ', '_')}"
    confirm_checkbox_key = f"confirm_remove_{title.replace(' ', '_')}_{unique_key_suffix.replace(' ', '_')}"

    if st.button(f"🗑️ Remove Selected Trades ({len(selected_trades)})", key=remove_button_key):
        if not selected_trades:
            st.warning("Please select at least one trade to remove")
        else:
            indices_to_remove = [trade_id_to_index[trade] for trade in selected_trades]
            st.session_state[pending_key] = indices_to_remove
            st.rerun()

    # Show confirmation and perform removal when user checks the box (on a later run)
    if pending_key in st.session_state:
        indices_to_remove = st.session_state[pending_key]
        trade_names = []
        for opt in trade_options:
            if trade_id_to_index.get(opt) in indices_to_remove:
                trade_names.append(f"• {opt}")
        st.markdown(f"**Trades to remove ({len(indices_to_remove)}):**")
        for name in trade_names:
            st.markdown(name)
        if st.checkbox("✅ Confirm removal — these will be deleted from the monitored CSV", key=confirm_checkbox_key):
            removed_count = remove_signals_from_monitored_by_indices(indices_to_remove)
            del st.session_state[pending_key]
            st.success(f"✅ Successfully removed {removed_count} trade(s) from monitored list!")
            st.rerun()
        if st.button("Cancel", key=f"cancel_removal_{unique_key_suffix.replace(' ', '_')}"):
            del st.session_state[pending_key]
            st.rerun()

    st.markdown("---")

def display_monitored_trades_metrics(df, interval, position_name):
    """Display summary metrics for monitored trades"""

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_trades = len(df)
        st.metric("Total Trades", total_trades)

    with col2:
        # Calculate actual win rate:
        # - For closed trades: based on actual profit (exit price vs signal price)
        # - For open trades: based on current mark to market (today price vs signal price)
        winning_trades = 0
        total_trades_counted = 0

        for _, row in df.iterrows():
            signal_price = row.get('Signal_Price', 0)
            signal_type = str(row.get('Signal_Type', '')).upper()

            try:
                signal_price = float(signal_price) if signal_price != 'N/A' and signal_price != '' else 0
            except (ValueError, TypeError):
                signal_price = 0

            if signal_price <= 0:
                continue

            if row['Status'] == 'Closed':
                # For closed trades: use exit price to calculate profit
                exit_price = row.get('Exit_Price')
                if pd.notna(exit_price) and exit_price != 'N/A' and exit_price != '':
                    try:
                        exit_price = float(exit_price)
                        total_trades_counted += 1
                        # Calculate profit percentage
                        pnl = ((exit_price - signal_price) / signal_price) * 100
                        # For short positions, invert the P&L
                        if signal_type == 'SHORT':
                            pnl = -pnl
                        # If profit > 0, it's a winning trade
                        if pnl > 0:
                            winning_trades += 1
                    except (ValueError, TypeError):
                        pass
            elif row['Status'] == 'Open':
                # For open trades: use today price to calculate mark to market
                current_price = row.get('Current_Price')
                if pd.notna(current_price) and current_price != 'N/A' and current_price != '':
                    try:
                        current_price = float(current_price)
                        total_trades_counted += 1
                        # Calculate mark to market percentage
                        mtm = ((current_price - signal_price) / signal_price) * 100
                        # For short positions, invert the MTM
                        if signal_type == 'SHORT':
                            mtm = -mtm
                        # If MTM > 0, it's currently a winning trade
                        if mtm > 0:
                            winning_trades += 1
                    except (ValueError, TypeError):
                        pass

        if total_trades_counted > 0:
            actual_win_rate = (winning_trades / total_trades_counted) * 100
            st.metric("Actual Win Rate", f"{actual_win_rate:.2f}%")
        else:
            st.metric("Actual Win Rate", "N/A")

    with col3:
        # Calculate average profit (for all trades - realized for closed, unrealized for open)
        profits = []

        for _, row in df.iterrows():
            try:
                if row['Status'] == 'Closed' and pd.notna(row.get('Exit_Price')) and row.get('Exit_Price') != 'N/A':
                    # Realized profit
                    exit_price = row.get('Exit_Price')
                    signal_price = row.get('Signal_Price')
                    signal_type = str(row.get('Signal_Type', '')).upper()

                    try:
                        exit_price = float(exit_price)
                        signal_price = float(signal_price) if signal_price != 'N/A' and signal_price != '' else 0
                    except (ValueError, TypeError):
                        continue

                    if signal_price > 0:
                        pnl = ((exit_price - signal_price) / signal_price) * 100
                        if signal_type == 'SHORT':
                            pnl = -pnl
                        profits.append(pnl)
                elif row['Status'] == 'Open' and pd.notna(row.get('Current_Price')) and row.get('Current_Price') != 'N/A':
                    # Unrealized profit
                    current_price = row.get('Current_Price')
                    signal_price = row.get('Signal_Price')
                    signal_type = str(row.get('Signal_Type', '')).upper()

                    try:
                        current_price = float(current_price)
                        signal_price = float(signal_price) if signal_price != 'N/A' and signal_price != '' else 0
                    except (ValueError, TypeError):
                        continue

                    if signal_price > 0:
                        pnl = ((current_price - signal_price) / signal_price) * 100
                        if signal_type == 'SHORT':
                            pnl = -pnl
                        profits.append(pnl)
            except Exception:
                pass

        if profits:
            avg_profit = sum(profits) / len(profits)
            st.metric("Avg Profit", f"{avg_profit:.2f}%")
        else:
            st.metric("Avg Profit", "N/A")

    with col4:
        # Calculate average backtested win rate
        if 'Win_Rate' in df.columns:
            win_rates = []
            for rate in df['Win_Rate']:
                try:
                    if pd.notna(rate) and rate != 'N/A' and rate != '':
                        numeric_rate = float(str(rate).strip('%'))
                        win_rates.append(numeric_rate)
                except (ValueError, TypeError):
                    pass

            if len(win_rates) > 0:
                avg_win_rate = sum(win_rates) / len(win_rates)
                st.metric("Avg Backtested Win Rate", f"{avg_win_rate:.2f}%")
            else:
                st.metric("Avg Backtested Win Rate", "N/A")
        else:
            st.metric("Avg Backtested Win Rate", "N/A")

    st.markdown("---")

def display_trades_table(df: pd.DataFrame, title: str):
    """Display trades in a formatted table - custom format for monitored trades"""
    if df.empty:
        st.warning(f"No {title.lower()} to display")
        return

    # Create a custom dataframe with key information, Function as first column
    custom_data = []
    for _, row in df.iterrows():
        # Calculate profit/loss
        profit = None
        try:
            signal_price = row.get('Signal_Price')
            signal_type = str(row.get('Signal_Type', '')).upper()

            if row.get('Status') == 'Closed':
                # Realized profit for closed trades
                exit_price = row.get('Exit_Price')
                if pd.notna(signal_price) and pd.notna(exit_price) and signal_price != '' and exit_price != '':
                    signal_price = float(signal_price)
                    exit_price = float(exit_price)
                    if signal_price > 0:
                        profit = ((exit_price - signal_price) / signal_price) * 100
                        # For short positions, invert the P&L
                        if signal_type == 'SHORT':
                            profit = -profit
            elif row.get('Status') == 'Open':
                # Unrealized profit for open trades
                current_price = row.get('Current_Price')
                if pd.notna(signal_price) and pd.notna(current_price) and signal_price != '' and current_price != '':
                    signal_price = float(signal_price)
                    current_price = float(current_price)
                    if signal_price > 0:
                        profit = ((current_price - signal_price) / signal_price) * 100
                        # For short positions, invert the P&L
                        if signal_type == 'SHORT':
                            profit = -profit
        except (ValueError, TypeError):
            profit = None

        custom_row = {
            'Function': row.get('Function', 'Unknown'),
            'Symbol': row.get('Symbol', ''),
            'Signal_Type': row.get('Signal_Type', ''),
            'Interval': row.get('Interval', ''),
            'Signal_Date': row.get('Signal_Date', ''),
            'Signal_Price': row.get('Signal_Price', ''),
            'Current_Price': row.get('Current_Price', ''),
            'Profit (%)': profit,
            'Status': row.get('Status', ''),
            'Exit_Date': row.get('Exit_Date', ''),
            'Exit_Price': row.get('Exit_Price', ''),
            'Win_Rate': row.get('Win_Rate_Display', row.get('Win_Rate', '')),
            'Strategy_CAGR': row.get('Strategy_CAGR', ''),
            'Strategy_Sharpe': row.get('Strategy_Sharpe', ''),
            'PE_Ratio': row.get('PE_Ratio', 'N/A'),
            'Industry_PE': row.get('Industry_PE', 'N/A'),
            'Last Qtr Profit (Net Inc)': row.get('Last_Quarter_Profit', 'N/A'),  # Most recent quarter
            'Same Qtr Prior Yr (Net Inc)': row.get('Last_Year_Same_Quarter_Profit', 'N/A'),  # Same quarter, last year
        }
        custom_data.append(custom_row)

    custom_df = pd.DataFrame(custom_data)

    # Format numeric columns
    for col in ['Signal_Price', 'Current_Price', 'Profit (%)', 'PE_Ratio', 'Industry_PE', 'Last Qtr Profit (Net Inc)', 'Same Qtr Prior Yr (Net Inc)', 'Exit_Price', 'Win_Rate', 'Strategy_CAGR', 'Strategy_Sharpe']:
        if col in custom_df.columns:
            def format_value(x):
                if pd.isna(x) or x == '' or x is None or str(x).lower() == 'no data':
                    return str(x) if str(x).lower() == 'no data' else ''
                try:
                    # Try to convert to float and format
                    numeric_val = float(x)
                    # Profit (%) column: 2 decimal places
                    if col == 'Profit (%)':
                        return f"{numeric_val:.2f}"
                    # Last_Qtr_Profit, Last_Year_Qtr_Profit: large numbers with commas
                    elif 'Net Inc' in col or 'Profit' in col:
                        return f"{numeric_val:,.0f}"
                    else:
                        return f"{numeric_val:.2f}"
                except (ValueError, TypeError):
                    # If it can't be converted to float, return as string
                    return str(x)
            custom_df[col] = custom_df[col].apply(format_value)

    # Display with better formatting
    st.dataframe(
        custom_df,
        use_container_width=True,
        height=400
    )