#!/bin/bash

# Script: 1) Run emailscript_india.sh (signal generation), 2) Copy trade files from MindWealth, 3) Enrich Trendline/Distance with fundamentals

set -e  # Exit on any error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔄 Starting trade update (email script + file copy)..."
echo "📁 Working directory: $SCRIPT_DIR"

# Step 1: Run emailscript_india.sh (signal generation) from MindWealth folder
MINDWEALTH_DIR="$SCRIPT_DIR/../MindWealth"
EMAIL_SCRIPT="$MINDWEALTH_DIR/emailscript_india.sh"
if [ -f "$EMAIL_SCRIPT" ]; then
    echo "📧 Running signal generation (emailscript_india.sh) from MindWealth..."
    set +e
    ( cd "$MINDWEALTH_DIR" && bash emailscript_india.sh )
    _ret=$?
    set -e
    cd "$SCRIPT_DIR"
    if [ $_ret -eq 0 ]; then
        echo "   ✅ emailscript_india.sh completed"
    else
        echo "   ⚠️  emailscript_india.sh exited with code $_ret (continuing with file copy)"
    fi
else
    echo "   ⚠️  emailscript_india.sh not found at $EMAIL_SCRIPT, skipping signal generation"
fi

echo ""
echo "📂 Copying trade files from MindWealth to this project..."

# Define directories
SOURCE_INDIA_DIR="../MindWealth/trade_store/INDIA"
TARGET_INDIA_DIR="trade_store/INDIA"

# Check if source directory exists
if [ ! -d "$SOURCE_INDIA_DIR" ]; then
    echo "❌ Error: Source directory $SOURCE_INDIA_DIR does not exist!"
    exit 1
fi

# Create target directory if it doesn't exist
mkdir -p "$TARGET_INDIA_DIR"
echo "📂 Target directory: $TARGET_INDIA_DIR"

# Delete only the three trade data files from current project (do NOT touch monitored_trades.csv)
echo "🗑️  Removing old Distance, Trendline, and forward_testing CSV from this project..."
if [ -d "$TARGET_INDIA_DIR" ]; then
    for f in "$TARGET_INDIA_DIR"/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_Distance.csv; do
        [ -f "$f" ] && rm -f "$f" && echo "   Removed $(basename "$f")"
    done
    for f in "$TARGET_INDIA_DIR"/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_Trendline.csv; do
        [ -f "$f" ] && rm -f "$f" && echo "   Removed $(basename "$f")"
    done
    if [ -f "$TARGET_INDIA_DIR/forward_testing.csv" ]; then
        rm -f "$TARGET_INDIA_DIR/forward_testing.csv" && echo "   Removed forward_testing.csv"
    fi
    echo "   ✅ monitored_trades.csv left unchanged"
fi

# Copy latest dated Distance.csv (e.g. 2026-02-06_Distance.csv)
echo "📊 Copying Distance CSV..."
latest_distance=$(find "$SOURCE_INDIA_DIR" -maxdepth 1 -type f -name "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_Distance.csv" 2>/dev/null | sort -r | head -1)
if [ -n "$latest_distance" ] && [ -f "$latest_distance" ]; then
    cp "$latest_distance" "$TARGET_INDIA_DIR/"
    echo "   ✅ $(basename "$latest_distance")"
else
    echo "   ⚠️  No dated Distance CSV found in $SOURCE_INDIA_DIR"
fi

# Copy latest dated Trendline.csv (e.g. 2026-02-06_Trendline.csv)
echo "📊 Copying Trendline CSV..."
latest_trendline=$(find "$SOURCE_INDIA_DIR" -maxdepth 1 -type f -name "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_Trendline.csv" 2>/dev/null | sort -r | head -1)
if [ -n "$latest_trendline" ] && [ -f "$latest_trendline" ]; then
    cp "$latest_trendline" "$TARGET_INDIA_DIR/"
    echo "   ✅ $(basename "$latest_trendline")"
else
    echo "   ⚠️  No dated Trendline CSV found in $SOURCE_INDIA_DIR"
fi

# Copy forward_testing.csv
echo "📊 Copying Forward Testing CSV..."
if [ -f "$SOURCE_INDIA_DIR/forward_testing.csv" ]; then
    cp "$SOURCE_INDIA_DIR/forward_testing.csv" "$TARGET_INDIA_DIR/forward_testing.csv"
    echo "   ✅ forward_testing.csv"
else
    echo "   ⚠️  forward_testing.csv not found in $SOURCE_INDIA_DIR"
fi

# Copy data_fetch_datetime.json (used for "Data fetched" banner on each page)
echo "📅 Copying data_fetch_datetime.json..."
if [ -f "$SOURCE_INDIA_DIR/data_fetch_datetime.json" ]; then
    cp "$SOURCE_INDIA_DIR/data_fetch_datetime.json" "$TARGET_INDIA_DIR/data_fetch_datetime.json"
    echo "   ✅ data_fetch_datetime.json"
else
    echo "   ⚠️  data_fetch_datetime.json not found in $SOURCE_INDIA_DIR"
fi

echo "✅ Trade update (file copy) completed!"

# Step 3: Enrich Trendline and Distance CSVs with PE_Ratio, Industry_PE, Last_Quarter_Profit, Last_Year_Same_Quarter_Profit
echo ""
echo "📈 Enriching Trendline and Distance CSVs with fundamentals (PE_Ratio, Industry_PE, etc.)..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi
if python3 enrich_trendline_distance_fundamentals.py; then
    echo "   ✅ Fundamentals enrichment completed"
else
    echo "   ⚠️  Fundamentals enrichment had warnings (see above)"
fi

# Step 4: Build / update potential_entry.csv and potential_exit.csv from latest Distance/Trendline files
echo ""
echo "📌 Updating potential entry/exit CSVs..."
if python3 entry_exit_fetcher.py; then
    echo "   ✅ Potential entry/exit CSVs updated"
else
    echo "   ⚠️  Potential entry/exit update had warnings (see above)"
fi

# Step 5: Update Today Price for potential_entry.csv and potential_exit.csv (same logic as Potential page button)
echo ""
echo "💰 Updating Today Price for potential entry/exit..."
python3 - << 'PY'
import sys
import os

sys.path.insert(0, '.')

from page_functions.potential_signals import _update_potential_prices

try:
    _update_potential_prices()
    print("   ✅ Today Price updated for potential_entry.csv and potential_exit.csv")
except Exception as e:
    print(f"   ⚠️  Failed to update Today Price for potential CSVs: {e}")
PY

echo ""
echo "✅ Report generation completed!"
echo "💡 Data: Distance/Trendline CSVs, forward_testing.csv, data_fetch_datetime.json, fundamentals enrichment, potential entry/exit CSVs with updated Today Price."
