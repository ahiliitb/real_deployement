import argparse
import os

from groww import GrowwTradingClient

_DEPLOYEMENT_DIR = os.path.dirname(os.path.abspath(__file__))


def _parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for basic Groww actions.

    Supported modes
    ---------------
    - No subcommand: generate a net holdings report and write `net_holdings.csv`.
    - `buy SYMBOL QTY` : place a market BUY order for the given symbol.
    - `sell SYMBOL QTY`: place a market SELL order for the given symbol.
    """
    parser = argparse.ArgumentParser(
        description="CLI helper around GrowwTradingClient."
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    buy_parser = subparsers.add_parser("buy", help="Place a market BUY order")
    buy_parser.add_argument("symbol", type=str, help="Trading symbol, e.g. HCLTECH")
    buy_parser.add_argument("quantity", type=int, help="Quantity to buy")

    sell_parser = subparsers.add_parser("sell", help="Place a market SELL order")
    sell_parser.add_argument("symbol", type=str, help="Trading symbol, e.g. HCLTECH")
    sell_parser.add_argument("quantity", type=int, help="Quantity to sell")

    return parser.parse_args()


def main() -> None:
    """
    Main entry point for running Groww tasks from the `deployement` folder.

    Examples
    --------
    Generate net holdings CSV and print summary:
        python main.py

    Place a market BUY order:
        python main.py buy HCLTECH 10

    Place a market SELL order:
        python main.py sell HCLTECH 5
    """
    args = _parse_args()
    client = GrowwTradingClient()

    if args.command == "buy":
        resp = client.buy_equity(symbol=args.symbol, quantity=args.quantity)
        print("BUY order response:", resp)
    elif args.command == "sell":
        resp = client.sell_equity(symbol=args.symbol, quantity=args.quantity)
        print("SELL order response:", resp)
    else:
        # Default behaviour: generate the net holdings report
        client.generate_net_holdings_report(
            csv_filename=os.path.join(_DEPLOYEMENT_DIR, "net_holdings.csv")
        )


if __name__ == "__main__":
    main()

