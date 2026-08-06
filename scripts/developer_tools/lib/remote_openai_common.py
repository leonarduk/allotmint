"""Shared helpers for remote OpenAI-compatible LLM endpoint code review scripts.

This module models a generic OpenAI-compatible HTTP client that talks to any
inference server exposing a ``/v1/chat/completions`` endpoint — vLLM, SGLang,
TGI, and similar engines all speak the same schema. It is NOT engine-specific;
the caller configures endpoint, model name, and API key via environment
variables so the same module works with whatever engine the user has rented.

Mirrors ``ollama_common.py``'s contract and error-handling conventions
(explicit ``URLError`` / ``HTTPError`` / ``TimeoutError`` /
``JSONDecodeError`` handling, ``SystemExit(1)`` on failure).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def get_remote_llm_endpoint() -> str:
    """Return the remote LLM endpoint URL (no default; must be configured)."""
    return os.environ.get("REMOTE_LLM_ENDPOINT", "")


def get_remote_llm_model() -> str:
    """Return the model name to send in chat-completions requests.

    Defaults to a generic placeholder so the user gets an obvious error if
    they forget to set it, rather than a confusing engine-specific "model not
    found" message.
    """
    return os.environ.get("REMOTE_LLM_MODEL", "set-REMOTE_LLM_MODEL")


def get_remote_llm_api_key() -> str:
    """Return the API key / bearer token for the remote endpoint."""
    return os.environ.get("REMOTE_LLM_API_KEY", "")


def extract_remote_openai_review(data: dict[str, Any]) -> str:
    """Extract review text from an OpenAI-compatible chat-completions response.

    The standard response shape is
    ``{"choices": [{"message": {"content": "<string>"}}]}``.
    """
    choices = data.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    return content.strip() if isinstance(content, str) else ""


def fetch_remote_openai_review(
    endpoint: str,
    model: str,
    api_key: str,
    prompt: str,
) -> str:
    """POST a prompt to a remote OpenAI-compatible endpoint and return the response.

    Calls ``{endpoint}/v1/chat/completions`` with a standard chat-completions
    payload. Returns the extracted content string, or exits with code 1 on any
    transport / HTTP / parse error (same contract as ``fetch_ollama_review``).
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    url = f"{endpoint.rstrip('/')}/v1/chat/completions"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )

    try:
        # 5 min timeout — same as ollama_common for consistency
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read()
            print(
                f"INFO: Remote LLM API responded with {len(raw)} bytes",
                file=sys.stderr,
            )
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(
            f"ERROR: Remote LLM API returned {exc.code}: {body}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(
            f"ERROR: Remote LLM API request failed: {exc.reason}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except TimeoutError as exc:
        # A stall mid-read after the connection succeeds raises a bare
        # TimeoutError rather than being wrapped in URLError, so it needs its
        # own handler to avoid propagating as an uncaught exception.
        print(
            f"ERROR: Remote LLM API request timed out: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: Remote LLM API returned non-JSON response: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    review = extract_remote_openai_review(data)
    if not review.strip():
        print(
            "WARNING: Remote LLM API returned an empty review body",
            file=sys.stderr,
        )
    return review
