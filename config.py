# Configuration settings for the trading signals dashboard

import os

# Page configuration
PAGE_CONFIG = {
    "page_title": "Trade Store Tables",
    "page_icon": "📊",
    "layout": "wide"
}

# File paths (trends/distance use latest dated file in INDIA dir; see utils.data_loader.get_latest_dated_file_path)
INDIA_DATA_DIR = "trade_store/INDIA"
DATA_FILES = {
    "trends_suffix": "Trendline.csv",   # latest file: YYYY-MM-DD_Trendline.csv
    "distance_suffix": "Distance.csv",  # latest file: YYYY-MM-DD_Distance.csv
    "forward_testing": "trade_store/INDIA/forward_testing.csv"
}

# Navigation options
PAGE_OPTIONS = [
    "📈 Trendline Signals",
    "📏 Distance Signals",
    "📚 All Signals",
    "📌 Potential Entry & Exit",
    "🛒 Trades Bought",
    "📊 Forward Testing Performance",
]

# Card pagination settings (cards per tab; container height fixed, scroll to see all)
CARDS_PER_PAGE = 30

# Data file paths (derived from INDIA_DATA_DIR)
POTENTIAL_ENTRY_CSV = os.path.join(INDIA_DATA_DIR, "potential_entry.csv")
POTENTIAL_EXIT_CSV = os.path.join(INDIA_DATA_DIR, "potential_exit.csv")
TRADES_BOUGHT_CSV = os.path.join(INDIA_DATA_DIR, "trades_bought.csv")
ALL_SIGNALS_CSV = os.path.join(INDIA_DATA_DIR, "all_signals.csv")
DATA_FETCH_DATETIME_JSON = os.path.join(INDIA_DATA_DIR, "data_fetch_datetime.json")

# Entry/Exit conditions (used by utils.entry_exit_fetcher)
ENTRY_EXIT_MIN_WIN_RATE = 80.0
ENTRY_EXIT_MIN_NUM_TRADES = 6
ENTRY_PRICE_BAND_PCT_ABOVE = 1.0  # Reject if today price >= this % above signal price
ENTRY_PRICE_BAND_PCT_BELOW = -3.0  # Reject if today price <= this % below signal price
ENTRY_EXIT_MAX_PE_RATIO = 50.0
ENTRY_EXIT_PROFIT_RATIO = 0.5  # Last_Quarter_Profit > this * Last_Year_Same_Quarter_Profit
EXIT_RECENCY_DAYS = 3  # Exit_Date must be within this many days of fetch date

# Filter defaults (Trendline/Distance sidebar sliders)
DEFAULT_MIN_WIN_RATE = 70.0
DEFAULT_MIN_SHARPE = -5.0
WIN_RATE_SLIDER_MAX = 100.0
SHARPE_SLIDER_MIN = -10.0
SHARPE_SLIDER_MAX = 5.0

# Script/process settings
SUBPROCESS_TIMEOUT_SECONDS = 600
YFINANCE_RATE_LIMIT_DELAY = 0.5

# Trade deduplication: columns used to build unique key (same key = duplicate trade)
TRADE_DEDUP_COLUMNS = [
    "Function",      # function name
    "Symbol",        # asset name
    "Signal_Date",
    "Signal_Type",   # Long or Short
    "Interval",
]

# CSS for metric cards
METRIC_CARD_CSS = """
<style>
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px;
    border-radius: 10px;
    text-align: center;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    margin: 10px 0;
}
.metric-value {
    font-size: 2em;
    font-weight: bold;
    margin: 0;
}
.positive {
    color: #4CAF50;
}
.negative {
    color: #f44336;
}
.metric-label {
    font-size: 0.9em;
    margin: 5px 0 0 0;
    opacity: 0.9;
}
</style>
"""

# CSS for scrollable containers
SCROLLABLE_CONTAINER_CSS = """
<style>
/* Custom scrollbar styling for strategy cards */
.stContainer {
    max-height: 70vh;
    overflow-y: auto;
    overflow-x: hidden;
}
.stContainer::-webkit-scrollbar {
    width: 12px;
}
.stContainer::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 10px;
    margin: 5px;
}
.stContainer::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 10px;
}
.stContainer::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
}
</style>
"""