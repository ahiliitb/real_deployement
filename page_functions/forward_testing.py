import streamlit as st
import os
from config import DATA_FILES
from utils.data_loader import load_csv

def show_forward_testing(selected_function="All", selected_interval="All"):
    """Show the forward testing performance page"""
    st.title("📊 Forward Testing Performance")

    forward_file = DATA_FILES["forward_testing"]

    if os.path.exists(forward_file):
        df_forward = load_csv(forward_file)

        if df_forward is not None:
            # Apply filters
            filtered_df = df_forward.copy()
            if selected_function != "All":
                filtered_df = filtered_df[filtered_df['Function'] == selected_function]
            if selected_interval != "All":
                filtered_df = filtered_df[filtered_df['Interval'] == selected_interval]

            # Show the total records info
            if len(filtered_df) != len(df_forward):
                st.write(f"**Filtered Results:** {len(filtered_df)} records (from {len(df_forward)} total)")
            else:
                st.write(f"**Total Performance Records:** {len(df_forward)}")

            # Show the forward testing data as a clean table
            st.subheader("📊 Performance Analysis Table")
            st.dataframe(
                filtered_df,
                use_container_width=True,
                height=600
            )

        else:
            st.error("Failed to load forward testing data")
    else:
        st.error(f"File not found: {forward_file}")