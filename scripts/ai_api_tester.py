#!/usr/bin/env python3
"""Run HTTP endpoints from a YAML config and summarize results with GPT."""

import argparse
from pathlib import Path
from typing import Any

import requests
import yaml
from openai import OpenAI


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load test cases from a YAML file."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError("Config file must contain a list of test cases")
    return data


def run_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Execute each test case and collect responses or exceptions."""
    results: list[dict[str, Any]] = []
    for idx, case in enumerate(cases, start=1):
        method = case.get("method", "GET")
        url = case.get("url")
        kwargs = {
            k: case[k] for k in ("headers", "params", "json", "data") if k in case
        }
        entry: dict[str, Any] = {"id": idx, "method": method, "url": url}
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            entry["status"] = response.status_code
            entry["body"] = response.text
        except Exception as exc:  # noqa: BLE001
            entry["exception"] = str(exc)
        results.append(entry)
    return results


def write_log(results: list[dict[str, Any]], path: Path) -> str:
    """Write raw results to a log file and return its text."""
    lines: list[str] = []
    for entry in results:
        lines.append(f"Case {entry['id']}: {entry['method']} {entry['url']}")
        if "status" in entry:
            lines.append(f"Status: {entry['status']}")
            lines.append(f"Body: {entry['body']}")
        if "exception" in entry:
            lines.append(f"Exception: {entry['exception']}")
        lines.append("---")
    log_text = "\n".join(lines)
    path.write_text(log_text, encoding="utf-8")
    return log_text


def summarize_with_ai(log_text: str) -> str:
    """Generate a concise summary using the OpenAI SDK."""
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Summarize the following API test log concisely.",
            },
            {"role": "user", "content": log_text},
        ],
    )
    return response.choices[0].message.content.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run API test cases from YAML")
    default_config = Path(__file__).resolve().parent.parent / "api_test_cases.yaml"
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help="YAML file containing test case definitions.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("api_test_results.log"),
        help="File to write raw API responses.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("api_test_summary.txt"),
        help="File to write AI-generated summary.",
    )
    args = parser.parse_args()

    try:
        cases = load_cases(args.config)
    except FileNotFoundError:
        print(f"Config file not found at {args.config}. Use --config to specify its location.")
        raise SystemExit(1)
    results = run_cases(cases)
    log_text = write_log(results, args.log)
    summary = summarize_with_ai(log_text)
    args.summary.write_text(summary, encoding="utf-8")
    print(f"Summary written to {args.summary}")


if __name__ == "__main__":
    main()
