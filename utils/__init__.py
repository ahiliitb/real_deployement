"""
Utils package.

Re-exports commonly used helpers so callers can simply:

    from utils import fetch_current_price_yfinance, display_monitored_trades_metrics

Uses lazy imports so CLI scripts (e.g. enrich_trendline_distance_fundamentals) can run
without loading streamlit.
"""

__all__ = ["fetch_current_price_yfinance", "display_monitored_trades_metrics"]


def __getattr__(name):
    if name == "fetch_current_price_yfinance":
        from .trade import fetch_current_price_yfinance
        return fetch_current_price_yfinance
    if name == "display_monitored_trades_metrics":
        from .trade import display_monitored_trades_metrics
        return display_monitored_trades_metrics
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
