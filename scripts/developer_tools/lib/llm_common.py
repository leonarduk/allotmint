"""Shared local/cloud/remote model dispatch for developer_tools scripts.

n_review_issue.py (#5721) introduced a LOCAL/CLOUD model-source switch that let
a script fall back to a cloud model (DeepSeek) when a heavier review benefits
from it. #6149 added a REMOTE source that talks to any self-hosted OpenAI-
compatible inference server (vLLM/SGLang/TGI). This module centralizes that
switch -- the argparse wiring, the interactive prompt, connection/credential
validation, and the actual dispatch -- so every other developer_tools script
that calls an LLM (issue creation, issue triage, local/PR review, commit-
message generation) can offer the same choice without re-implementing it
(#5768).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add .github/scripts (for deepseek_review) to sys.path so this works both as
# an importable module and when a caller script is invoked directly, where the
# repo root is not on sys.path. ollama_common is a sibling in this same lib/
# dir, so it needs no path insertion.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".github" / "scripts"))
from deepseek_review import fetch_deepseek_review  # noqa: E402
from ollama_common import (  # noqa: E402
    fetch_ollama_review,
    get_ollama_endpoint,
    get_ollama_model,
    validate_ollama_connection,
)
from remote_openai_common import (  # noqa: E402
    fetch_remote_openai_review,
    get_remote_llm_endpoint,
    get_remote_llm_model,
)

LOCAL = "local"
CLOUD = "cloud"
REMOTE = "remote"
MODEL_SOURCES = (LOCAL, CLOUD, REMOTE)


def add_model_source_arg(parser, default: str = LOCAL) -> None:
    """Add a ``--model-source {local,cloud,remote}`` option to an argparse parser."""
    parser.add_argument(
        "--model-source",
        choices=MODEL_SOURCES,
        default=default,
        help=(
            "Which LLM to use: 'local' (Ollama), 'cloud' (DeepSeek), "
            "or 'remote' (self-hosted OpenAI-compatible). "
            f"Default: {default}."
        ),
    )


def prompt_for_model_source() -> str:
    """Interactively prompt for which model source to use."""
    print()
    print("Model source:")
    print("  [l] Local (Ollama)")
    print("  [c] Cloud (DeepSeek)")
    print("  [r] Remote (self-hosted OpenAI-compatible)")
    try:
        choice = input("> ").strip().lower()
    except EOFError:
        choice = "l"
    if choice in ("c", "cloud"):
        return CLOUD
    if choice in ("r", "remote"):
        return REMOTE
    return LOCAL


def describe_model_source(model_source: str) -> str:
    """Human-readable description of the chosen model, for INFO logs."""
    if model_source == LOCAL:
        return f"local model '{get_ollama_model()}' at {get_ollama_endpoint()}"
    if model_source == REMOTE:
        return f"remote model '{get_remote_llm_model()}' at {get_remote_llm_endpoint()}"
    return "cloud model (DeepSeek)"


def validate_model_source(model_source: str) -> bool:
    """Return True if the chosen model source is actually usable right now.

    Prints an actionable error to stderr and returns False otherwise, so
    callers can bail out with a single `if not validate_model_source(...)`.
    """
    if model_source == LOCAL:
        endpoint = get_ollama_endpoint()
        if not validate_ollama_connection(endpoint):
            print(
                f"ERROR: Ollama is not reachable at {endpoint}. "
                "Start Ollama or set OLLAMA_ENDPOINT.",
                file=sys.stderr,
            )
            return False
        return True

    if model_source == REMOTE:
        endpoint = get_remote_llm_endpoint()
        if not endpoint:
            print(
                "ERROR: REMOTE_LLM_ENDPOINT is not set; "
                "cannot use the remote model.",
                file=sys.stderr,
            )
            return False
        return True

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print(
            "ERROR: DEEPSEEK_API_KEY is not set; cannot use the cloud model.",
            file=sys.stderr,
        )
        return False
    return True


def fetch_review(model_source: str, prompt: str) -> str:
    """Dispatch a prompt to the chosen model source and return its response.

    Mirrors `fetch_ollama_review`'s contract: returns "" on an empty/failed
    response rather than raising, so callers keep a single failure check
    regardless of which model source is active.
    """
    if model_source == LOCAL:
        endpoint = get_ollama_endpoint()
        model = get_ollama_model()
        return fetch_ollama_review(endpoint, model, prompt)

    if model_source == REMOTE:
        endpoint = get_remote_llm_endpoint()
        model = get_remote_llm_model()
        api_key = os.environ.get("REMOTE_LLM_API_KEY", "")
        return fetch_remote_openai_review(endpoint, model, api_key, prompt)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    return fetch_deepseek_review(api_key, prompt)
