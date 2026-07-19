"""Shared helpers for Ollama-based code review scripts."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def get_ollama_endpoint() -> str:
    """Return the Ollama server endpoint, defaulting to localhost:11434."""
    return os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")


def get_ollama_model() -> str:
    """Return the Ollama model to use for reviews.

    Defaults to 'qwen2.5-coder:14b' (a lightweight coder model). Override with
    OLLAMA_MODEL environment variable.
    """
    return os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")


def list_available_models(endpoint: str) -> list[str]:
    """Fetch list of available models from Ollama API.

    Returns model names, or empty list if Ollama is unreachable.
    """
    try:
        url = f"{endpoint}/api/tags"
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read())
            return [model["name"] for model in data.get("models", [])]
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError):
        return []


def validate_ollama_connection(endpoint: str) -> bool:
    """Check if Ollama is reachable."""
    models = list_available_models(endpoint)
    return len(models) > 0


def extract_ollama_review(data: dict[str, Any]) -> str:
    """Extract review text from Ollama generate response.

    Ollama's generate API returns responses in streaming JSON format.
    The `response` field contains the accumulated text.
    """
    return data.get("response", "").strip()


def fetch_ollama_review(endpoint: str, model: str, prompt: str) -> str:
    """Call Ollama and return the advisory review body.

    The Ollama API uses the generate endpoint with streaming responses.
    We collect all response chunks into a single review string.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,  # Get complete response in one call
        "temperature": 0.2,
    }

    url = f"{endpoint}/api/generate"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        # 5 min timeout for local LLM
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read()
            print(f"INFO: Ollama API responded with {len(raw)} bytes", file=sys.stderr)
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"ERROR: Ollama API returned {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"ERROR: Ollama API request failed: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc
    except json.JSONDecodeError as exc:
        print(f"ERROR: Ollama API returned non-JSON response: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    review = extract_ollama_review(data)
    if not review.strip():
        print("WARNING: Ollama API returned an empty review body", file=sys.stderr)
    return review
