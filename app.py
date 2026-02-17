import json
import streamlit as st
import time
import os
import subprocess
from config import (
    PAGE_CONFIG,
    METRIC_CARD_CSS,
    PAGE_OPTIONS,
    INDIA_DATA_DIR,
    DATA_FETCH_DATETIME_JSON,
    DEFAULT_MIN_WIN_RATE,
    DEFAULT_MIN_SHARPE,
    WIN_RATE_SLIDER_MAX,
    SHARPE_SLIDER_MIN,
    SHARPE_SLIDER_MAX,
    SUBPROCESS_TIMEOUT_SECONDS,
)
from page_functions.trendline_signals import show_trendline_signals
from page_functions.distance_signals import show_distance_signals
from page_functions.forward_testing import show_forward_testing
from page_functions.potential_signals import show_potential_entry_exit
from page_functions.trades_bought import show_trades_bought
from page_functions.all_signals import show_all_signals

# Project root (directory where app.py lives)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Set page configuration
st.set_page_config(**PAGE_CONFIG)

# Add custom CSS for metric cards
st.markdown(METRIC_CARD_CSS, unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.title("📊 Navigation")
st.sidebar.markdown("---")

# Button: Generate signals & refresh (runs update_trade.sh: signals, files, enrichment, price updates)
if st.sidebar.button(
    "🔄 Generate signals & refresh",
    key="generate_signals_refresh_btn",
    help="Run update_trade.sh: signal generation, file sync, fundamentals enrichment, bought trades update, and fresh price updates for all CSVs",
):
    progress = st.sidebar.empty()
    try:
        progress.info("Running update_trade.sh (signals + files + enrichment + prices)...")
        r = subprocess.run(
            ["bash", "update_trade.sh"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        if r.returncode != 0:
            st.sidebar.warning(f"update_trade.sh exited with code {r.returncode}. Continuing.")
            if r.stderr:
                st.sidebar.code(r.stderr[:800], language="text")
        progress.success("✅ Data refresh completed (including all price updates)!")
    except subprocess.TimeoutExpired:
        progress.error("Script timed out. Please try again or run update_trade.sh manually.")
    except Exception as e:
        progress.error(f"Error: {e}")
    else:
        time.sleep(0.5)
        st.rerun()

st.sidebar.markdown("---")

# Check if we need to navigate (e.g. after adding to monitored)
if "navigate_to_page" in st.session_state:
    target = st.session_state.pop("navigate_to_page")
    page_index = PAGE_OPTIONS.index(target) if target in PAGE_OPTIONS else 0
else:
    page_index = 0

selected_page = st.sidebar.selectbox(
    "Select Page",
    PAGE_OPTIONS,
    index=page_index
)

# Refresh in the same window (rerun refetches data from CSV)
if st.sidebar.button(
    "🔄 Refresh page",
    key="refresh_page_btn",
    help="Reload the app and fetch latest data from CSV files (same window)",
):
    st.rerun()
st.sidebar.markdown("---")

# Initialize filter variables
selected_function = "All"
selected_interval = "All"
min_win_rate = DEFAULT_MIN_WIN_RATE
min_sharpe = DEFAULT_MIN_SHARPE

# Add filters to sidebar based on selected page
if selected_page == "📊 Forward Testing Performance":
    from utils.data_loader import load_csv
    from config import DATA_FILES

    # Load forward testing data to get filter options
    forward_df = load_csv(DATA_FILES["forward_testing"])
    if forward_df is not None:
        st.sidebar.markdown("**🔍 Filters**")

        # Filter by Function
        functions = ["All"] + sorted(forward_df['Function'].unique().tolist())
        selected_function = st.sidebar.selectbox("Filter by Function", functions, key="forward_function")

        # Filter by Interval
        intervals = ["All"] + sorted(forward_df['Interval'].unique().tolist())
        selected_interval = st.sidebar.selectbox("Filter by Interval", intervals, key="forward_interval")

        st.sidebar.markdown("---")

elif selected_page in ["📈 Trendline Signals", "📏 Distance Signals"]:
    from config import DATA_FILES, INDIA_DATA_DIR
    from utils.data_loader import load_csv, get_latest_dated_file_path

    # Resolve latest dated file (same pattern as update_trade.sh)
    if selected_page == "📈 Trendline Signals":
        data_file = get_latest_dated_file_path(INDIA_DATA_DIR, DATA_FILES["trends_suffix"])
    else:
        data_file = get_latest_dated_file_path(INDIA_DATA_DIR, DATA_FILES["distance_suffix"])

    df = load_csv(data_file) if data_file else None

    if df is not None:
        st.sidebar.markdown("**🔍 Filters**")

        # Win Rate filter (>= threshold)
        min_available_win_rate = 0.0
        if 'Win_Rate' in df.columns:
            win_rates = df['Win_Rate'].dropna()
            if len(win_rates) > 0:
                min_available_win_rate = win_rates.min()

        min_win_rate = st.sidebar.slider(
            "Min Win Rate (%)",
            min_value=float(min_available_win_rate),
            max_value=float(WIN_RATE_SLIDER_MAX),
            value=float(DEFAULT_MIN_WIN_RATE),
            step=1.0,
            help="Filter signals with win rate above this threshold",
            key="win_rate_slider"
        )

        # Sharpe Ratio filter (>= threshold)
        min_available_sharpe = float(SHARPE_SLIDER_MIN)
        if 'Strategy_Sharpe' in df.columns:
            sharpe_values = df['Strategy_Sharpe'].dropna()
            if len(sharpe_values) > 0:
                min_available_sharpe = float(sharpe_values.min())

        min_sharpe = st.sidebar.slider(
            "Min Sharpe Ratio",
            min_value=float(min_available_sharpe),
            max_value=float(SHARPE_SLIDER_MAX),
            value=float(DEFAULT_MIN_SHARPE),
            step=0.1,
            help="Filter signals with Sharpe ratio above this threshold",
            key="sharpe_slider"
        )

        st.sidebar.markdown("---")

# Data fetch datetime banner (top of main content on every page)
if os.path.isfile(DATA_FETCH_DATETIME_JSON):
    try:
        with open(DATA_FETCH_DATETIME_JSON, "r", encoding="utf-8") as f:
            fetch_info = json.load(f)
        dt_str = fetch_info.get("datetime", "")
        tz_str = fetch_info.get("timezone", "")
        if dt_str:
            if tz_str:
                st.markdown(f"📅 **Data fetched:** {dt_str} ({tz_str})", help="Timestamp when trade data was last generated")
            else:
                st.markdown(f"📅 **Data fetched:** {dt_str}", help="Timestamp when trade data was last generated")
    except Exception:
        pass

# Main app logic - route to selected page
if selected_page == "📈 Trendline Signals":
    show_trendline_signals(min_win_rate=min_win_rate, min_sharpe=min_sharpe)

elif selected_page == "📏 Distance Signals":
    show_distance_signals(min_win_rate=min_win_rate, min_sharpe=min_sharpe)

elif selected_page == "📚 All Signals":
    show_all_signals()

elif selected_page == "📌 Potential Entry & Exit":
    show_potential_entry_exit()

elif selected_page == "🛒 Trades Bought":
    show_trades_bought()

elif selected_page == "📊 Forward Testing Performance":
    show_forward_testing(selected_function=selected_function, selected_interval=selected_interval)