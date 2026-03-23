from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_CONTRACT = ROOT / "backend" / "contracts_spa.py"
TYPESCRIPT_CONTRACT = ROOT / "frontend" / "src" / "contracts" / "spa.ts"
VERSION_PATTERN = re.compile(
    r'SPA_RESPONSE_CONTRACT_VERSION\s*=\s*["\']([^"\']+)["\']'
)


def extract_contract_version(path: Path) -> str:
    match = VERSION_PATTERN.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(
            f"Could not find SPA_RESPONSE_CONTRACT_VERSION in {path.relative_to(ROOT)}"
        )
    return match.group(1)


def main() -> int:
    try:
        python_version = extract_contract_version(PYTHON_CONTRACT)
        typescript_version = extract_contract_version(TYPESCRIPT_CONTRACT)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if python_version != typescript_version:
        print(
            "ERROR: SPA contract version mismatch — "
            f"Python ({PYTHON_CONTRACT.relative_to(ROOT)}): {python_version!r}, "
            f"TypeScript ({TYPESCRIPT_CONTRACT.relative_to(ROOT)}): {typescript_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"OK: SPA contract version in sync ({python_version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
