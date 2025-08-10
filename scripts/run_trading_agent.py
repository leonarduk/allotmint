import argparse

from trading_agent import run as run_trading_agent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the trading agent")
    parser.add_argument(
        "--use-openai",
        action="store_true",
        help="Enable OpenAI powered decision making",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_trading_agent(use_openai=args.use_openai)


if __name__ == "__main__":
    main()
