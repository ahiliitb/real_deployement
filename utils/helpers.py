import re
import hashlib


def generate_unique_hash(unique_str):
    """Generate a unique hash for session state keys"""
    return hashlib.md5(unique_str.encode()).hexdigest()[:8]

def parse_symbol_signal_info(symbol_signal_info):
    """Parse symbol, signal type, date and price from CSV column"""
    symbol = "Unknown"
    signal_type = "Unknown"
    signal_date = "Unknown"
    signal_price = "N/A"

    if symbol_signal_info and symbol_signal_info != 'nan':
        # Parse: "ETH-USD, Long, 2026-02-06 (Price: 1978.0664)"
        if ', ' in symbol_signal_info:
            parts = symbol_signal_info.split(', ')
            if len(parts) >= 3:
                symbol = parts[0].strip('"')
                signal_type = parts[1].strip()
                # Extract date and price from the third part
                date_price_part = parts[2].strip(')"')
                if ' (Price: ' in date_price_part:
                    date_part, price_part = date_price_part.split(' (Price: ')
                    signal_date = date_part.strip()
                    signal_price = price_part.strip()

    return symbol, signal_type, signal_date, signal_price

def parse_interval_info(interval_info):
    """Parse interval from CSV column"""
    interval_display = "Unknown"
    if interval_info and interval_info != 'nan':
        if ', ' in interval_info:
            interval_display = interval_info.split(', ')[0].strip('"')
        else:
            interval_display = interval_info.strip('"')
    return interval_display

def parse_win_rate_info(win_rate_info):
    """Parse win rate from CSV column"""
    win_rate = "N/A"
    if win_rate_info and win_rate_info != 'nan':
        if ', ' in win_rate_info:
            parts = win_rate_info.split(', ')
            if len(parts) >= 1:
                win_rate = parts[0].strip('"') + "%"
    return win_rate


def parse_exit_signal_info(exit_str):
    """
    Parse Exit Signal Date/Price column from CSV.
    Returns (exit_date, exit_price) - both None if 'No Exit Yet' or unparseable.
    Example: "2026-02-06 (Price: 168.45), 1.51% above" -> ("2026-02-06", 168.45)
    """
    if not exit_str or str(exit_str).strip() == 'nan':
        return None, None
    s = str(exit_str).strip()
    if s.lower().startswith('no exit'):
        return None, None
    # Match YYYY-MM-DD (Price: NNN.NNN)
    match = re.search(r'(\d{4}-\d{2}-\d{2})\s*\(Price:\s*([\d.]+)\)', s)
    if match:
        exit_date = match.group(1)
        try:
            exit_price = float(match.group(2))
            return exit_date, exit_price
        except (ValueError, TypeError):
            return exit_date, None
    return None, None