#!/usr/bin/env python3
"""Command-line helper to run the trading agent."""

import argparse
from typing import Iterable, Optional

from backend.agent.trading_agent import run


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the trading agent")
    parser.add_argument(
        "--tickers", nargs="+", help="List of tickers to analyse", default=None
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    run(tickers=args.tickers)


if __name__ == "__main__":
    main()
