import os
import re

import pandas as pd
import streamlit as st


def get_latest_dated_file_path(directory, suffix):
    """
    Find the latest file in directory matching YYYY-MM-DD_<suffix> (same pattern as update_trade.sh).
    Returns full path to the file, or None if none found.
    """
    if not directory or not os.path.isdir(directory):
        return None
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}_" + re.escape(suffix) + r"$")
    matching = [f for f in os.listdir(directory) if pattern.match(f)]
    if not matching:
        return None
    matching.sort(reverse=True)
    return os.path.join(directory, matching[0])


def load_csv(file_path):
    """Load CSV file and return DataFrame"""
    try:
        df = pd.read_csv(file_path, sep=',', quotechar='"', encoding='utf-8')
        return df
    except Exception as e:
        st.error(f"Error loading {file_path}: {str(e)}")
        return None