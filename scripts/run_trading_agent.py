#!/usr/bin/env python3
"""Command-line helper to run the trading agent."""

import argparse

from backend.agent.trading_agent import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the trading agent")
    parser.add_argument(
        "--tickers", nargs="+", help="List of tickers to analyse", default=None
    )
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        help="Threshold values for each ticker",
        default=None,
    )
    parser.add_argument(
        "--indicator",
        type=str,
        help="Technical indicator to use",
        default=None,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(tickers=args.tickers)


if __name__ == "__main__":
    main()
