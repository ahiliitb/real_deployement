"""
Trade-related shared utilities used across pages.

Contains:
- fetch_current_price_yfinance: fetch latest price for a symbol from local stock_data/INDIA files
- display_monitored_trades_metrics: summary metrics block reused on multiple pages
"""

from __future__ import annotations

import json
import os
from datetime import datetime, date
from typing import Any

import pandas as pd
import streamlit as st


from config import DATA_FETCH_DATETIME_JSON

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDIA_STOCK_DATA_DIR = os.path.join(ROOT_DIR, "stock_data", "INDIA")
INDIA_TODAY_JSON = os.path.join(INDIA_STOCK_DATA_DIR, "today_date.json")


def _load_today_date_mapping() -> dict[str, str]:
    """Load mapping of symbol -> latest date from today_date.json."""
    try:
        if not os.path.isfile(INDIA_TODAY_JSON):
            return {}
        with open(INDIA_TODAY_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}
    except Exception:
        return {}


_TODAY_DATE_MAP: dict[str, str] | None = None


def fetch_current_price_yfinance(symbol: str | Any) -> float | None:
    """
    Fetch latest price for a symbol **from local stock_data/INDIA**, not yfinance.

    Rules:
    - Symbols are expected in Yahoo-style format (e.g. "HCLTECH.NS").
    - We first look up the expected "today" date in stock_data/INDIA/today_date.json.
    - Then we read stock_data/INDIA/{symbol}.csv and take the Close on that date.
    - If that exact date row is missing, we fall back to the last available Close.
    """
    global _TODAY_DATE_MAP

    if not symbol or not str(symbol).strip():
        return None
    sym = str(symbol).strip()

    # Lazy‑load today_date.json mapping once
    if _TODAY_DATE_MAP is None:
        _TODAY_DATE_MAP = _load_today_date_mapping()

    csv_path = os.path.join(INDIA_STOCK_DATA_DIR, f"{sym}.csv")
    if not os.path.isfile(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return None

    if df.empty or "Close" not in df.columns:
        return None

    # If we know the expected "today" date for this symbol, try to use that row
    target_date = None
    if _TODAY_DATE_MAP:
        target_date = _TODAY_DATE_MAP.get(sym)

    if target_date and "Date" in df.columns:
        try:
            row = df.loc[df["Date"] == target_date]
            if not row.empty:
                val = row.iloc[0]["Close"]
                return float(val)
        except Exception:
            # Fall back to last available row below
            pass

    # Fallback: use the last available row's Close
    try:
        last_row = df.iloc[-1]
        return float(last_row["Close"])
    except Exception:
        return None


def _get_data_fetch_date() -> date | None:
    """Return data-fetch date from data_fetch_datetime.json, or None if missing."""
    if not os.path.isfile(DATA_FETCH_DATETIME_JSON):
        return None
    try:
        with open(DATA_FETCH_DATETIME_JSON, encoding="utf-8") as f:
            data = json.load(f)
        d = data.get("date") or (data.get("datetime", "")[:10] if data.get("datetime") else None)
        if not d:
            return None
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def display_monitored_trades_metrics(
    df: pd.DataFrame, interval: str, position_name: str
) -> None:
    """
    Display summary metrics for a set of trades.

    This is reused by the Monitored, Potential, and All Signals pages.
    """
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        total_trades = len(df)
        st.metric("Total Trades", total_trades)

    with col2:
        # Actual win rate:
        # - Closed trades: based on realized profit (exit vs signal)
        # - Open trades: based on mark-to-market (current vs signal)
        winning_trades = 0
        total_trades_counted = 0

        for _, row in df.iterrows():
            signal_price = row.get("Signal_Price", 0)
            signal_type = str(row.get("Signal_Type", "")).upper()

            try:
                signal_price = (
                    float(signal_price)
                    if signal_price not in ("N/A", "", None)
                    else 0.0
                )
            except (ValueError, TypeError):
                signal_price = 0.0

            if signal_price <= 0:
                continue

            if row.get("Status") == "Closed":
                exit_price = row.get("Exit_Price")
                if (
                    pd.notna(exit_price)
                    and exit_price not in ("N/A", "", None)
                ):
                    try:
                        exit_price = float(exit_price)
                        total_trades_counted += 1
                        pnl = ((exit_price - signal_price) / signal_price) * 100
                        if signal_type == "SHORT":
                            pnl = -pnl
                        if pnl > 0:
                            winning_trades += 1
                    except (ValueError, TypeError):
                        pass
            elif row.get("Status") == "Open":
                # Potential/All Signals use Today_Price; Monitored uses Current_Price
                current_price = row.get("Current_Price") or row.get("Today_Price")
                if (
                    pd.notna(current_price)
                    and current_price not in ("N/A", "", None)
                ):
                    try:
                        current_price = float(current_price)
                        total_trades_counted += 1
                        mtm = ((current_price - signal_price) / signal_price) * 100
                        if signal_type == "SHORT":
                            mtm = -mtm
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
        # Average profit (realized for closed, unrealized for open)
        profits = []
        for _, row in df.iterrows():
            try:
                if (
                    row.get("Status") == "Closed"
                    and pd.notna(row.get("Exit_Price"))
                    and row.get("Exit_Price") not in ("N/A", "", None)
                ):
                    exit_price = row.get("Exit_Price")
                    signal_price = row.get("Signal_Price")
                    signal_type = str(row.get("Signal_Type", "")).upper()

                    try:
                        exit_price = float(exit_price)
                        signal_price = (
                            float(signal_price)
                            if signal_price not in ("N/A", "", None)
                            else 0.0
                        )
                    except (ValueError, TypeError):
                        continue

                    if signal_price > 0:
                        pnl = ((exit_price - signal_price) / signal_price) * 100
                        if signal_type == "SHORT":
                            pnl = -pnl
                        profits.append(pnl)
                elif row.get("Status") == "Open":
                    # Potential/All Signals use Today_Price; Monitored uses Current_Price
                    current_price = row.get("Current_Price") or row.get("Today_Price")
                    if (
                        pd.notna(current_price)
                        and current_price not in ("N/A", "", None)
                    ):
                        signal_price = row.get("Signal_Price")
                        signal_type = str(row.get("Signal_Type", "")).upper()

                        try:
                            current_price = float(current_price)
                            signal_price = (
                                float(signal_price)
                                if signal_price not in ("N/A", "", None)
                                else 0.0
                            )
                        except (ValueError, TypeError):
                            continue

                        if signal_price > 0:
                            pnl = ((current_price - signal_price) / signal_price) * 100
                            if signal_type == "SHORT":
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
        # Average holding period (days)
        fetch_date = _get_data_fetch_date() or date.today()
        holding_days_list = []
        for _, row in df.iterrows():
            try:
                sig_date_str = row.get("Signal_Date")
                if not sig_date_str or pd.isna(sig_date_str):
                    continue
                sig_date = datetime.strptime(str(sig_date_str)[:10], "%Y-%m-%d").date()
                if row.get("Status") == "Closed":
                    exit_date_str = row.get("Exit_Date")
                    if exit_date_str and str(exit_date_str).strip() and str(exit_date_str).lower() != "nan":
                        exit_d = datetime.strptime(str(exit_date_str)[:10], "%Y-%m-%d").date()
                        holding_days_list.append((exit_d - sig_date).days)
                else:
                    holding_days_list.append((fetch_date - sig_date).days)
            except (ValueError, TypeError):
                pass
        if holding_days_list:
            avg_holding = sum(holding_days_list) / len(holding_days_list)
            st.metric("Avg Holding Period", f"{avg_holding:.1f} days")
        else:
            st.metric("Avg Holding Period", "N/A")

    with col5:
        # Average backtested win rate
        if "Win_Rate" in df.columns:
            win_rates = []
            for rate in df["Win_Rate"]:
                try:
                    if (
                        pd.notna(rate)
                        and rate not in ("N/A", "", None)
                    ):
                        numeric_rate = float(str(rate).strip("%"))
                        win_rates.append(numeric_rate)
                except (ValueError, TypeError):
                    pass

            if win_rates:
                avg_win_rate = sum(win_rates) / len(win_rates)
                st.metric("Avg Backtested Win Rate", f"{avg_win_rate:.2f}%")
            else:
                st.metric("Avg Backtested Win Rate", "N/A")
        else:
            st.metric("Avg Backtested Win Rate", "N/A")

    st.markdown("---")

