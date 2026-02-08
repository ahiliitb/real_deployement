import streamlit as st

def create_summary_cards(df, page_name="Unknown"):
    """Create summary metric cards"""
    # Parse data from CSV columns
    win_rates = []
    cagr_values = []
    sharpe_values = []

    # Determine column indices based on page type
    if "Trendline" in page_name:
        cagr_col = 18
        sharpe_col = 21
    else:
        cagr_col = 12
        sharpe_col = 15

    for idx, row in df.iterrows():
        # Column 3: Win Rate [%], History Tested, Number of Trades
        win_rate_info = str(row.iloc[3]) if len(row) > 3 else ""
        if win_rate_info and win_rate_info != 'nan':
            if ', ' in win_rate_info:
                parts = win_rate_info.split(', ')
                if len(parts) >= 1:
                    try:
                        win_rate_pct = float(parts[0].strip('"').strip('%'))
                        win_rates.append(win_rate_pct)
                    except:
                        pass

        # Backtested Strategy CAGR [%]
        if len(row) > cagr_col and str(row.iloc[cagr_col]) != 'nan':
            try:
                cagr_str = str(row.iloc[cagr_col]).strip('%')
                cagr_values.append(float(cagr_str))
            except:
                pass

        # Backtested Strategy Sharpe Ratio
        if len(row) > sharpe_col and str(row.iloc[sharpe_col]) != 'nan':
            try:
                sharpe_values.append(float(row.iloc[sharpe_col]))
            except:
                pass

    # Calculate averages
    avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
    avg_cagr = sum(cagr_values) / len(cagr_values) if cagr_values else 0
    avg_sharpe = sum(sharpe_values) / len(sharpe_values) if sharpe_values else 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{avg_win_rate:.1f}%</p>
            <p class="metric-label">Average Win Rate</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        total_trades = len(df)
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{total_trades}</p>
            <p class="metric-label">Total Trades</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        color_class = "positive" if avg_cagr > 0 else "negative"
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value {color_class}">{avg_cagr:.1f}%</p>
            <p class="metric-label">Average Strategy CAGR</p>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{avg_sharpe:.2f}</p>
            <p class="metric-label">Average Sharpe Ratio</p>
        </div>
        """, unsafe_allow_html=True)