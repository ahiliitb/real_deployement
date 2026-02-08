# Configuration settings for the trading signals dashboard

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
    "👁️ Monitored Signals",
    "📊 Forward Testing Performance"
]

# Card pagination settings (cards per tab; container height fixed, scroll to see all)
CARDS_PER_PAGE = 30

# Trade deduplication: columns used to build unique key (same key = duplicate trade)
TRADE_DEDUP_COLUMNS = [
    "Function",      # function name
    "Symbol",        # asset name
    "Signal_Date",
    "Signal_Type",   # Long or Short
    "Interval",
]

# Chart enabled pages
CHART_ENABLED_PAGES = [
    "Band Matrix", "DeltaDrift", "Fractal Track", "BaselineDiverge",
    "Altitude Alpha", "Oscillator Delta", "SigmaShell", "PulseGauge",
    "TrendPulse"
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