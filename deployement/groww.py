import base64
import os
import csv
from typing import Dict, Any, List, Optional
from datetime import date

import pyotp
from dotenv import load_dotenv
from growwapi import GrowwAPI


class GrowwTradingClient:
    """
    High-level wrapper around the Groww Python SDK.

    This class:
    - Authenticates using `GROWW_API_KEY` and `GROWW_TOTP_SECRET` (TOTP-based)
      or `GROWW_ACCESS_TOKEN` (direct token) from `.env`.
    - Provides methods to fetch holdings, cash, and today's trades.
    - Computes a *net holdings* view (holdings adjusted for today's trades).
    - Can place simple BUY/SELL equity orders.
    """

    def __init__(self) -> None:
        """
        Initialise the underlying `GrowwAPI` client using environment variables.

        Expected environment variables
        ------------------------------
        Option 1 (TOTP-based, recommended):
            GROWW_API_KEY : str
                API key generated from the Groww Trading API dashboard.
            GROWW_TOTP_SECRET : str
                TOTP secret for generating 6-digit codes (used with pyotp).

        Option 2 (direct token):
            GROWW_ACCESS_TOKEN : str
                Pre-fetched access token. If set, API_KEY and TOTP_SECRET
                are not required.

        Raises
        ------
        RuntimeError
            If required env vars are missing.
        """
        load_dotenv()

        access_token = os.getenv("GROWW_ACCESS_TOKEN")
        if access_token:
            # Use provided access token directly
            self.api = GrowwAPI(access_token)
            return

        api_key = os.getenv("GROWW_API_KEY")
        totp_secret = os.getenv("GROWW_TOTP_SECRET")

        if not api_key or not totp_secret:
            raise RuntimeError(
                "Set either GROWW_ACCESS_TOKEN, or both GROWW_API_KEY and "
                "GROWW_TOTP_SECRET in your .env file."
            )

        # TOTP secret must be Base32 (A-Z, 2-7). Sanitize and handle common variants.
        totp_secret = totp_secret.strip().replace(" ", "").replace("-", "")

        # If secret looks like hex (e.g. Groww format), convert to Base32
        if all(c in "0123456789abcdefABCDEF" for c in totp_secret) and len(totp_secret) >= 16:
            try:
                raw_bytes = bytes.fromhex(totp_secret)
                totp_secret = base64.b32encode(raw_bytes).decode("ascii").rstrip("=")
            except ValueError:
                pass  # Not valid hex, fall through to try as Base32

        totp_secret = totp_secret.upper()
        # Groww uses Base32 variant with 0/1 - map to O/I for standard Base32
        totp_secret = totp_secret.replace("0", "O").replace("1", "I")

        try:
            totp_gen = pyotp.TOTP(totp_secret)
            current_otp = totp_gen.now()
        except Exception as e:
            raise RuntimeError(
                f"Invalid GROWW_TOTP_SECRET format. TOTP secrets must be Base32 "
                f"(only letters A-Z and digits 2-7). Remove spaces and ensure no "
                f"invalid characters. Original error: {e}"
            ) from e

        access_token = GrowwAPI.get_access_token(api_key=api_key, totp=current_otp)
        self.api = GrowwAPI(access_token)

    # --------------------------------------------------------------------- #
    # Data access helpers
    # --------------------------------------------------------------------- #

    def fetch_open_holdings(self) -> List[Dict[str, Any]]:
        """
        Fetch all current equity holdings for the user from Groww.

        This calls `self.api.get_holdings_for_user()` and filters the raw
        payload so that only *active* holdings are returned. A holding is
        treated as active if any of the following quantities is non‑zero:

        - `quantity` (net quantity as shown in the DEMAT account)
        - `t1_quantity` (T+1 quantity for recent buys that have not yet
          moved to DEMAT)
        - `demat_free_quantity` (free DEMAT quantity that is not locked or
          pledged)

        Returns
        -------
        list[dict]
            List of holding dicts in the Groww API format.
        """
        response = self.api.get_holdings_for_user(timeout=5)
        holdings = response.get("holdings", response)

        open_holdings: List[Dict[str, Any]] = []
        for h in holdings:
            qty = float(h.get("quantity", 0) or 0)
            t1_qty = float(h.get("t1_quantity", 0) or 0)
            demat_free_qty = float(h.get("demat_free_quantity", 0) or 0)

            if any(v != 0.0 for v in (qty, t1_qty, demat_free_qty)):
                open_holdings.append(h)
        return open_holdings

    def fetch_available_cash(self) -> Dict[str, float]:
        """
        Retrieve the user's available cash and CNC equity balance.

        Returns a dict with:

        - `clear_cash`: total clear cash available in the trading account.
        - `cnc_balance_available`: cash available specifically for CNC
          (delivery) trades.
        """
        margin = self.api.get_available_margin_details()

        clear_cash = float(margin.get("clear_cash", 0.0))
        equity_details = margin.get("equity_margin_details", {}) or {}
        cnc_balance_available = float(equity_details.get("cnc_balance_available", 0.0))

        return {
            "clear_cash": clear_cash,
            "cnc_balance_available": cnc_balance_available,
        }

    def fetch_today_trades(self) -> List[Dict[str, Any]]:
        """
        Fetch all executed CASH-segment trades for the current trading day.

        This uses `self.api.get_order_list(segment=CASH)` and filters to
        orders that:

        - Have `order_status` in {"EXECUTED", "PARTIALLY_EXECUTED"}, and
        - Have `trade_date` equal to today's calendar date.

        Returns
        -------
        list[dict]
            List of order dictionaries representing today's executed BUY/SELL
            trades in the CASH segment.
        """
        resp = self.api.get_order_list(
            segment=self.api.SEGMENT_CASH,
            page=0,
            page_size=100,
        )
        orders = resp.get("order_list", resp)

        today_str = date.today().isoformat()  # "YYYY-MM-DD"
        executed_statuses = {"EXECUTED", "PARTIALLY_EXECUTED"}

        trades_today: List[Dict[str, Any]] = []
        for o in orders:
            status = o.get("order_status")
            trade_dt_raw = o.get("trade_date") or ""
            trade_date_str = trade_dt_raw[:10]  # first 10 chars = YYYY-MM-DD

            if status in executed_statuses and trade_date_str == today_str:
                trades_today.append(o)

        return trades_today

    def fetch_ltps_for_instruments(
        self,
        instruments: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """
        Fetch LTPs for a list of instruments described by exchange+symbol.

        Parameters
        ----------
        instruments :
            List of dicts containing:
            - `exchange`: e.g. `"NSE"` or `"BSE"`.
            - `trading_symbol`: e.g. `"RELIANCE"`, `"HDFCBANK"`.

        Returns
        -------
        dict[str, float]
            Mapping from `"EXCHANGE_SYMBOL"` (e.g. `"NSE_RELIANCE"`) to LTP.
        """
        if not instruments:
            return {}

        symbols = sorted({
            f"{p['exchange']}_{p['trading_symbol']}"
            for p in instruments
            if p.get("exchange") and p.get("trading_symbol")
        })

        ltps: Dict[str, float] = {}
        BATCH_SIZE = 50

        for i in range(0, len(symbols), BATCH_SIZE):
            batch = symbols[i:i + BATCH_SIZE]
            arg = batch[0] if len(batch) == 1 else tuple(batch)
            resp = self.api.get_ltp(
                segment=self.api.SEGMENT_CASH,
                exchange_trading_symbols=arg,
            )
            ltps.update({k: float(v) for k, v in resp.items()})

        return ltps

    # --------------------------------------------------------------------- #
    # Trading helpers (BUY / SELL)
    # --------------------------------------------------------------------- #

    def place_equity_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        exchange: Optional[str] = None,
        product: Optional[str] = None,
        validity: Optional[str] = None,
        trigger_price: Optional[float] = None,
        order_reference_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a simple equity order in the CASH segment.

        Parameters
        ----------
        symbol :
            Trading symbol, e.g. `"HDFCBANK"`, `"RELIANCE"`.
        quantity :
            Number of shares to BUY or SELL.
        side :
            One of `self.api.TRANSACTION_TYPE_BUY` or
            `self.api.TRANSACTION_TYPE_SELL`.
        order_type :
            One of `MARKET`, `LIMIT`, `STOP_LOSS`, `STOP_LOSS_MARKET`.
            Defaults to `"MARKET"`.
        price :
            Limit price when using a LIMIT / STOP_LOSS order.
        exchange :
            Exchange code. Defaults to NSE.
        product :
            Product type. Defaults to CNC (delivery).
        validity :
            Order validity. Defaults to DAY.
        trigger_price :
            Optional trigger price where applicable.
        order_reference_id :
            Optional client reference ID.

        Returns
        -------
        dict
            Response from `place_order` containing `groww_order_id` etc.
        """
        exchange = exchange or self.api.EXCHANGE_NSE
        product = product or self.api.PRODUCT_CNC
        validity = validity or self.api.VALIDITY_DAY

        # Map string order_type to SDK constant
        order_type_map = {
            "MARKET": self.api.ORDER_TYPE_MARKET,
            "LIMIT": self.api.ORDER_TYPE_LIMIT,
            "STOP_LOSS": self.api.ORDER_TYPE_STOP_LOSS,
            "STOP_LOSS_MARKET": self.api.ORDER_TYPE_STOP_LOSS_MARKET,
        }
        ot = order_type_map.get(order_type.upper(), self.api.ORDER_TYPE_MARKET)

        kwargs: Dict[str, Any] = dict(
            trading_symbol=symbol,
            quantity=int(quantity),
            validity=validity,
            exchange=exchange,
            segment=self.api.SEGMENT_CASH,
            product=product,
            order_type=ot,
            transaction_type=side,
        )
        if price is not None:
            kwargs["price"] = float(price)
        if trigger_price is not None:
            kwargs["trigger_price"] = float(trigger_price)
        if order_reference_id:
            kwargs["order_reference_id"] = order_reference_id

        return self.api.place_order(**kwargs)

    def buy_equity(
        self,
        symbol: str,
        quantity: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Convenience method to place an equity BUY order.

        Parameters are the same as `place_equity_order` except that
        `side` is fixed to BUY.
        """
        return self.place_equity_order(
            symbol=symbol,
            quantity=quantity,
            side=self.api.TRANSACTION_TYPE_BUY,
            order_type=order_type,
            price=price,
            **kwargs,
        )

    def sell_equity(
        self,
        symbol: str,
        quantity: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Convenience method to place an equity SELL order.

        Parameters are the same as `place_equity_order` except that
        `side` is fixed to SELL.
        """
        return self.place_equity_order(
            symbol=symbol,
            quantity=quantity,
            side=self.api.TRANSACTION_TYPE_SELL,
            order_type=order_type,
            price=price,
            **kwargs,
        )

    # --------------------------------------------------------------------- #
    # Net holdings report
    # --------------------------------------------------------------------- #

    def generate_net_holdings_report(
        self,
        csv_filename: str = "net_holdings.csv",
    ) -> None:
        """
        Compute and print the net holdings, and write them to a CSV file.

        Steps:
        - Fetch holdings and today's CASH-segment trades.
        - Compute per-symbol net quantity as:
          holdings quantity +/- today's BUY/SELL quantity.
        - Drop symbols whose net quantity becomes zero.
        - Fetch LTPs and compute invested value, market value, and P&L
          for each net holding.
        - Print a tabular summary to stdout.
        - Write a CSV file with per-symbol details.
        """
        holdings = self.fetch_open_holdings()
        today_trades = self.fetch_today_trades()

        holdings_by_symbol: Dict[str, Dict[str, Any]] = {
            h["trading_symbol"]: h for h in holdings
        }

        # Aggregate locked quantity information directly from holdings
        total_locked_quantity = 0.0
        total_locked_value = 0.0
        for h in holdings:
            locked_qty = float(h.get("groww_locked_quantity", 0) or 0)
            if locked_qty == 0.0:
                continue
            avg_price_holding = float(h.get("average_price", 0.0) or 0.0)
            total_locked_quantity += locked_qty
            total_locked_value += locked_qty * avg_price_holding

        # Aggregate today's net quantity change and BUY VWAP per symbol
        trade_agg: Dict[str, Dict[str, float]] = {}
        for t in today_trades:
            symbol = t["trading_symbol"]
            side = t.get("transaction_type", "").upper()
            qty = float(t.get("filled_quantity", 0) or 0)
            avg_fill = float(t.get("average_fill_price", 0) or 0)

            if symbol not in trade_agg:
                trade_agg[symbol] = {
                    "net_qty_delta": 0.0,
                    "buy_qty": 0.0,
                    "buy_value": 0.0,
                }
            agg = trade_agg[symbol]

            if side == "BUY":
                agg["net_qty_delta"] += qty
                agg["buy_qty"] += qty
                agg["buy_value"] += qty * avg_fill
            elif side == "SELL":
                agg["net_qty_delta"] -= qty

        # Build net holdings = base holdings +/- today's net trade quantity
        net_holdings: List[Dict[str, Any]] = []
        all_symbols = set(holdings_by_symbol.keys()) | set(trade_agg.keys())

        for symbol in sorted(all_symbols):
            base = holdings_by_symbol.get(symbol)
            base_qty = float(base.get("quantity", 0) or 0) if base else 0.0

            delta = trade_agg.get(symbol, {}).get("net_qty_delta", 0.0)
            net_qty = base_qty + delta

            if net_qty == 0.0:
                continue

            if base:
                avg_price = float(base.get("average_price", 0.0) or 0.0)
            else:
                agg = trade_agg.get(symbol, {})
                buy_qty = agg.get("buy_qty", 0.0)
                if buy_qty > 0:
                    avg_price = agg.get("buy_value", 0.0) / buy_qty
                else:
                    avg_price = 0.0

            net_holdings.append(
                {
                    "trading_symbol": symbol,
                    "quantity": net_qty,
                    "average_price": avg_price,
                }
            )

        # Prepare list for LTP lookups
        ltp_inputs: List[Dict[str, Any]] = []
        for nh in net_holdings:
            ltp_inputs.append(
                {
                    "exchange": "NSE",
                    "trading_symbol": nh["trading_symbol"],
                }
            )

        margin = self.fetch_available_cash()
        ltps = self.fetch_ltps_for_instruments(ltp_inputs)

        total_net_value = 0.0
        total_invested_value = 0.0

        print("=== Groww Net Holdings (Holdings ± Today's Trades) ===")
        if not net_holdings:
            print("No net holdings after applying today's trades.")
        else:
            for nh in net_holdings:
                symbol = nh["trading_symbol"]
                exchange = "NSE"
                qty = float(nh.get("quantity", 0) or 0)
                avg_price = float(nh.get("average_price", 0.0) or 0.0)

                exch_sym = f"{exchange}_{symbol}"
                ltp = float(ltps.get(exch_sym, avg_price))
                invested_value = abs(qty) * avg_price
                position_value = abs(qty) * ltp

                total_invested_value += invested_value
                total_net_value += position_value

                print(
                    f"{exchange:<4} {symbol:<20} "
                    f"qty={qty:>8.2f} "
                    f"avg={avg_price:>10.2f} "
                    f"ltp={ltp:>10.2f} "
                    f"inv={invested_value:>12.2f} "
                    f"pnl={(position_value - invested_value):>12.2f}"
                )

        # Write net holdings to CSV
        with open(csv_filename, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "symbol",
                    "quantity",
                    "avg_price",
                    "ltp",
                    "invested_value",
                    "market_value",
                    "pnl",
                ]
            )
            for nh in net_holdings:
                symbol = nh["trading_symbol"]
                exchange = "NSE"
                qty = float(nh.get("quantity", 0) or 0)
                avg_price = float(nh.get("average_price", 0.0) or 0.0)

                exch_sym = f"{exchange}_{symbol}"
                ltp = float(ltps.get(exch_sym, avg_price))
                invested_value = abs(qty) * avg_price
                market_value = abs(qty) * ltp
                pnl = market_value - invested_value

                writer.writerow(
                    [
                        symbol,
                        f"{qty:.2f}",
                        f"{avg_price:.2f}",
                        f"{ltp:.2f}",
                        f"{invested_value:.2f}",
                        f"{market_value:.2f}",
                        f"{pnl:.2f}",
                    ]
                )

        total_account_value = total_invested_value + margin["cnc_balance_available"]

        print("\n=== Summary ===")
        print(f"Number of net holdings: {len(net_holdings)}")
        print(f"Total invested value (net holdings): {total_invested_value:.2f} INR")
        print(f"Total value of net holdings: {total_net_value:.2f} INR")
        print(f"Total P&L (net holdings): {total_net_value - total_invested_value:.2f} INR")
        print(
            f"Equity CNC balance available: "
            f"{margin['cnc_balance_available']:.2f} INR"
        )
        print(f"Total account value (invested +  Equity CNC balance): {total_account_value:.2f} INR")
        print(f"Net holdings written to: {csv_filename}")


def main() -> None:
    """
    Script entry point for command-line usage.

    Creates a `GrowwTradingClient` and generates the net holdings report,
    writing it to `net_holdings.csv` in the deployement folder.
    """
    client = GrowwTradingClient()
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "net_holdings.csv")
    client.generate_net_holdings_report(csv_filename=csv_path)


if __name__ == "__main__":
    main()