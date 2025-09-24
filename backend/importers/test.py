"""Utility importer used by smoke tests.

This importer is intentionally minimal: it accepts any payload and produces an
empty set of holdings.  The smoke tests only validate that the endpoint
responds successfully, so a stub importer keeps the behaviour predictable
without depending on provider-specific fixtures.
"""

from __future__ import annotations

from typing import List

from backend.routes.transactions import Transaction


def parse(_data: bytes) -> List[Transaction]:
    """Return an empty list of transactions for smoke testing purposes."""

    return []
