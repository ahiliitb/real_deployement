"""
Enrich bought trades with latest data from Trendline/Distance files.

This module updates trades_bought.csv by:
1. Finding matching entries in all_signals.csv by key (Symbol, Signal_Date, Function, Interval)
2. Updating fields like Win_Rate, Exit signals, PE ratios, Strategy metrics, etc.
3. Keeping all trade data synchronized with latest signals
"""

import os
from typing import Dict, Any, List, Optional

import pandas as pd

from config import (
    TRADES_BOUGHT_CSV,
    ALL_SIGNALS_CSV,
    TRADE_DEDUP_COLUMNS,
)


def get_trade_dedup_key_from_record(record: Dict[str, Any]) -> str:
    """
    Build deduplication key using TRADE_DEDUP_COLUMNS.
    """
    parts: List[str] = []
    for col in TRADE_DEDUP_COLUMNS:
        val = str(record.get(col, "")).strip()
        if col == "Signal_Type":
            val = "Short" if "short" in val.lower() else "Long"
        parts.append(val)
    return "|".join(parts)


def load_bought_trades() -> List[Dict[str, Any]]:
    """Load bought trades from CSV."""
    if not os.path.exists(TRADES_BOUGHT_CSV):
        return []
    if os.path.getsize(TRADES_BOUGHT_CSV) == 0:
        return []
    try:
        df = pd.read_csv(TRADES_BOUGHT_CSV)
        if df.empty:
            return []
        return df.to_dict("records")
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return []


def load_all_signals() -> Dict[str, Dict[str, Any]]:
    """
    Load all_signals.csv and create a lookup dictionary keyed by Dedup_Key.
    """
    if not os.path.exists(ALL_SIGNALS_CSV):
        return {}
    if os.path.getsize(ALL_SIGNALS_CSV) == 0:
        return {}
    try:
        df = pd.read_csv(ALL_SIGNALS_CSV)
        if df.empty:
            return {}
        
        lookup: Dict[str, Dict[str, Any]] = {}
        for record in df.to_dict("records"):
            # Generate dedup key if not present
            if not record.get("Dedup_Key"):
                record["Dedup_Key"] = get_trade_dedup_key_from_record(record)
            
            dedup_key = record["Dedup_Key"]
            if dedup_key:
                lookup[dedup_key] = record
        
        return lookup
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return {}


def enrich_bought_trade(bought_record: Dict[str, Any], signal_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a bought trade record with latest data from signal record.
    
    Updates:
    - Win_Rate, Number_Of_Trades, Win_Rate_Display
    - Strategy_CAGR, Strategy_Sharpe
    - PE_Ratio, Industry_PE, Last_Quarter_Profit, Last_Year_Same_Quarter_Profit
    - Exit_Signal_Raw, Exit_Date, Exit_Price
    - TrendPulse fields
    - Today_Price (from signal if available)
    """
    enriched = bought_record.copy()
    
    # Fields to update from signal data
    fields_to_update = [
        "Win_Rate",
        "Number_Of_Trades",
        "Win_Rate_Display",
        "Strategy_CAGR",
        "Strategy_Sharpe",
        "PE_Ratio",
        "Industry_PE",
        "Last_Quarter_Profit",
        "Last_Year_Same_Quarter_Profit",
        "Exit_Signal_Raw",
        "Exit_Date",
        "Exit_Price",
        "TrendPulse_Start_End",
        "TrendPulse_Start_Price",
        "TrendPulse_End_Price",
        "Today_Price",
        "Today_vs_Signal_Pct",
        "Today_vs_Signal_Pct_Signed",
    ]
    
    for field in fields_to_update:
        if field in signal_record:
            enriched[field] = signal_record[field]
    
    # Ensure Dedup_Key is preserved/updated
    if "Dedup_Key" in signal_record:
        enriched["Dedup_Key"] = signal_record["Dedup_Key"]
    
    return enriched


def save_bought_trades(records: List[Dict[str, Any]]) -> None:
    """Save bought trades back to CSV."""
    if not records:
        pd.DataFrame().to_csv(TRADES_BOUGHT_CSV, index=False)
        return
    
    df = pd.DataFrame(records)
    
    # Define column order
    preferred_columns = [
        "Symbol",
        "Signal_Type",
        "Signal_Date",
        "Signal_Price",
        "Today_Price",
        "Win_Rate",
        "Number_Of_Trades",
        "Win_Rate_Display",
        "Strategy_CAGR",
        "Strategy_Sharpe",
        "Exit_Signal_Raw",
        "Exit_Date",
        "Exit_Price",
        "Function",
        "Interval",
        "PE_Ratio",
        "Industry_PE",
        "Last_Quarter_Profit",
        "Last_Year_Same_Quarter_Profit",
        "TrendPulse_Start_End",
        "TrendPulse_Start_Price",
        "TrendPulse_End_Price",
        "Today_vs_Signal_Pct",
        "Today_vs_Signal_Pct_Signed",
        "Dedup_Key",
    ]
    
    # Reorder columns (only include those that exist)
    existing_cols = [c for c in preferred_columns if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in existing_cols]
    final_cols = existing_cols + remaining_cols
    
    df = df[final_cols]
    df.to_csv(TRADES_BOUGHT_CSV, index=False)


def enrich_bought_trades_from_signals() -> Dict[str, Any]:
    """
    Main function to enrich bought trades with latest signal data.
    
    Returns a dictionary with statistics:
    - total_bought: Total number of bought trades
    - matched: Number of trades matched and updated
    - unmatched: Number of trades with no matching signal
    - unmatched_symbols: List of symbols that couldn't be matched
    """
    # Load data
    bought_trades = load_bought_trades()
    all_signals_lookup = load_all_signals()
    
    if not bought_trades:
        return {
            "total_bought": 0,
            "matched": 0,
            "unmatched": 0,
            "unmatched_symbols": [],
        }
    
    matched_count = 0
    unmatched_count = 0
    unmatched_symbols = []
    enriched_trades = []
    
    for bought_record in bought_trades:
        # Generate dedup key for this bought trade
        if not bought_record.get("Dedup_Key"):
            bought_record["Dedup_Key"] = get_trade_dedup_key_from_record(bought_record)
        
        dedup_key = bought_record["Dedup_Key"]
        
        # Look up matching signal
        if dedup_key and dedup_key in all_signals_lookup:
            # Match found - enrich the bought trade
            signal_record = all_signals_lookup[dedup_key]
            enriched_record = enrich_bought_trade(bought_record, signal_record)
            enriched_trades.append(enriched_record)
            matched_count += 1
        else:
            # No match - keep the bought trade as-is
            enriched_trades.append(bought_record)
            unmatched_count += 1
            symbol = bought_record.get("Symbol", "Unknown")
            unmatched_symbols.append(symbol)
    
    # Save enriched trades back to CSV
    save_bought_trades(enriched_trades)
    
    return {
        "total_bought": len(bought_trades),
        "matched": matched_count,
        "unmatched": unmatched_count,
        "unmatched_symbols": unmatched_symbols,
    }


def main() -> None:
    """Command-line entry point."""
    print("🔄 Enriching bought trades with latest signal data...")
    
    stats = enrich_bought_trades_from_signals()
    
    print(f"   📊 Total bought trades: {stats['total_bought']}")
    print(f"   ✅ Matched and updated: {stats['matched']}")
    print(f"   ⚠️  Unmatched (no signal found): {stats['unmatched']}")
    
    if stats['unmatched_symbols']:
        print(f"   📝 Unmatched symbols: {', '.join(set(stats['unmatched_symbols']))}")
    
    if stats['matched'] > 0:
        print("   ✅ Bought trades enriched successfully!")
    else:
        print("   ℹ️  No bought trades were updated (no matches found)")


if __name__ == "__main__":
    main()
