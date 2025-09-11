#!/usr/bin/env python3
"""Simple sitemap health checker.

This script parses ``frontend/public/sitemap.xml`` for all ``<loc>`` entries
and requests each URL. Any URL that does not return a HTTP 200 response or
raises a request exception is reported and the process exits with a non-zero
status code. It is intended for lightweight smoke tests in CI pipelines.
"""
from __future__ import annotations

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import requests


SITEMAP_PATH = (
    Path(__file__).resolve().parents[1] / "frontend" / "public" / "sitemap.xml"
)


def iter_sitemap_urls() -> list[str]:
    """Return a list of URLs from the sitemap."""
    tree = ET.parse(SITEMAP_PATH)
    root = tree.getroot()
    # The sitemap uses the standard namespace
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [
        elem.text.strip() for elem in root.findall("sm:url/sm:loc", ns) if elem.text
    ]


def check_urls(urls: list[str]) -> list[str]:
    """Request each URL and return those that didn't respond with HTTP 200."""
    failures: list[str] = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"{url} -> {resp.status_code}")
                failures.append(url)
            else:
                print(f"{url} -> OK")
        except requests.RequestException as exc:  # pragma: no cover - network failure
            print(f"{url} -> ERROR: {exc}")
            failures.append(url)
    return failures


def main() -> int:
    urls = iter_sitemap_urls()
    failures = check_urls(urls)
    if failures:
        print(f"{len(failures)} URL(s) failed")
        return 1
    print("All sitemap URLs responded with HTTP 200")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
