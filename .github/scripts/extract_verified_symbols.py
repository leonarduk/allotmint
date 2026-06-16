"""Extract class/function names from changed files and verify they exist in the codebase."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys


def extract_symbols_from_diff(diff_text: str) -> set[str]:
    """Extract potential class and function names from a diff."""
    symbols = set()

    # Match class definitions: class ClassName
    class_pattern = r'^\+.*?class\s+([A-Z]\w+)'
    # Match function definitions: def function_name or export function/const
    function_pattern = r'^\+.*?(?:def|async\s+def|export\s+(?:const|function)\s+)([a-z_][a-zA-Z0-9_]*)'

    for line in diff_text.splitlines():
        # Look at added lines only
        if line.startswith('+') and not line.startswith('+++'):
            class_match = re.search(class_pattern, line)
            if class_match:
                symbols.add(class_match.group(1))

            func_match = re.search(function_pattern, line)
            if func_match:
                symbols.add(func_match.group(1))

    return symbols


def verify_symbol_exists(symbol: str) -> bool:
    """Check if a symbol exists in the codebase using grep."""
    try:
        result = subprocess.run(
            ['grep', '-r', f'\\b{re.escape(symbol)}\\b', '--include=*.py', '--include=*.ts', '--include=*.tsx', '--include=*.js'],
            capture_output=True,
            timeout=5,
            cwd='.',
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main() -> int:
    """Extract symbols and generate a verified facts entry."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--diff', required=True, help='The PR diff text')
    args = parser.parse_args()

    symbols = extract_symbols_from_diff(args.diff)
    if not symbols:
        print("")
        return 0

    # Verify each symbol exists (limit to top 5 to avoid excessive output)
    verified = []
    for symbol in sorted(symbols)[:5]:
        if verify_symbol_exists(symbol):
            verified.append(f"`{symbol}`")

    if verified:
        facts = "**Classes/functions confirmed present in codebase:** " + ", ".join(verified) + "."
        print(facts)
    else:
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
