import streamlit as st
import os
from config import DATA_FILES, INDIA_DATA_DIR
from utils.data_loader import load_csv, get_latest_dated_file_path
from components.summary_cards import create_summary_cards
from components.cards import create_strategy_cards


def _symbol_from_row(row):
    """Extract symbol from first column (e.g. 'ETH-USD, Long, 2026-02-06 (Price: 1978)')."""
    if len(row) == 0:
        return ""
    cell = str(row.iloc[0])
    if not cell or cell == "nan":
        return ""
    if ", " in cell:
        return cell.split(", ")[0].strip('"').strip()
    return cell.strip('"').strip()


def show_distance_signals(min_win_rate=70.0, min_sharpe=-5.0):
    """Show the distance trading signals page"""
    st.title("📏 Distance Trading Signals")

    distance_file = get_latest_dated_file_path(INDIA_DATA_DIR, DATA_FILES["distance_suffix"])

    if distance_file and os.path.exists(distance_file):
        df_distance = load_csv(distance_file)

        if df_distance is not None:
            # Build list of unique symbols from data
            available_symbols = sorted({
                _symbol_from_row(row) for _, row in df_distance.iterrows()
                if _symbol_from_row(row)
            })

            # Sidebar: symbol filter (same pattern as Monitored Trades)
            st.sidebar.markdown("---")
            st.sidebar.markdown("#### 🔍 Filters")
            st.sidebar.markdown("**Symbols:**")
            all_symbols_label = "All Symbols"
            symbol_options = [all_symbols_label] + available_symbols

            if "selected_symbols_distance" not in st.session_state:
                st.session_state["selected_symbols_distance"] = list(available_symbols)
            stored = st.session_state.get("selected_symbols_distance", list(available_symbols))
            valid_stored = [s for s in stored if s in available_symbols]
            missing = [s for s in available_symbols if s not in valid_stored]
            if missing:
                valid_stored = sorted(set(valid_stored) | set(missing))
                st.session_state["selected_symbols_distance"] = valid_stored

            symbols = st.sidebar.multiselect(
                "Select Symbols",
                options=symbol_options,
                default=valid_stored,
                key="symbols_multiselect_distance",
                help="Choose one or more symbols. Select 'All Symbols' to include all.",
            )
            if all_symbols_label in symbols or not symbols:
                selected_symbols = set(available_symbols)
                st.session_state["selected_symbols_distance"] = list(available_symbols)
            else:
                selected_symbols = set(s for s in symbols if s in available_symbols)
                st.session_state["selected_symbols_distance"] = list(selected_symbols)

            # Apply symbol, win rate, and sharpe filters
            filtered_indices = []
            for idx, row in df_distance.iterrows():
                symbol = _symbol_from_row(row)
                symbol_ok = (symbol in selected_symbols) if selected_symbols else True

                win_rate_ok = False
                win_rate_info = str(row.iloc[3]) if len(row) > 3 else ""
                if win_rate_info and win_rate_info != "nan":
                    if ", " in win_rate_info:
                        parts = win_rate_info.split(", ")
                        if len(parts) >= 1:
                            try:
                                win_rate_pct = float(parts[0].strip('"').strip("%"))
                                if win_rate_pct >= min_win_rate:
                                    win_rate_ok = True
                            except Exception:
                                win_rate_ok = True
                    else:
                        win_rate_ok = True

                sharpe_ok = False
                if len(row) > 15 and str(row.iloc[15]) != "nan":
                    try:
                        sharpe_value = float(row.iloc[15])
                        if sharpe_value >= min_sharpe:
                            sharpe_ok = True
                    except Exception:
                        sharpe_ok = True

                if symbol_ok and win_rate_ok and sharpe_ok:
                    filtered_indices.append(idx)

            df_filtered = df_distance.loc[filtered_indices]

            if len(df_filtered) != len(df_distance):
                st.write(f"**Filtered Results:** {len(df_filtered)} signals (from {len(df_distance)} total)")

            st.subheader("📊 Summary Metrics")
            create_summary_cards(df_filtered, "Distance Signals")

            st.subheader("🎯 Strategy Cards")
            create_strategy_cards(df_filtered, "Distance Signals", "distance")

            st.subheader("📊 Detailed Data Table")
            # Hide fundamentals columns in table (shown only in strategy cards)
            table_cols_hide = ["PE_Ratio", "Industry_PE", "Last_Quarter_Profit", "Last_Year_Same_Quarter_Profit"]
            df_table = df_filtered.drop(columns=[c for c in table_cols_hide if c in df_filtered.columns], errors="ignore")
            st.dataframe(
                df_table,
                use_container_width=True,
                height=600,
            )
        else:
            st.error("Failed to load Distance data")
    else:
        st.error(f"File not found: no dated Distance CSV in {INDIA_DATA_DIR}. Run 'Generate signals & refresh' to copy data.")