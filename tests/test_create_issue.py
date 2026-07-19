"""Unit tests for the local-LLM review step in scripts/developer_tools/b_create_issue.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "developer_tools"))

from b_create_issue import (  # noqa: E402
    build_review_prompt,
    offer_local_llm_review,
    parse_review_response,
)


class TestBuildReviewPrompt:
    def test_includes_title_and_body(self):
        prompt = build_review_prompt("My title", "## What\n\nSomething")
        assert "My title" in prompt
        assert "## What" in prompt
        assert "TITLE:" in prompt
        assert "BODY:" in prompt


class TestParseReviewResponse:
    def test_parses_title_and_body(self):
        response = "TITLE: Better title\nBODY:\n## What\n\nImproved text\n"
        title, body = parse_review_response(response, "orig title", "orig body")
        assert title == "Better title"
        assert body.startswith("## What")
        assert "Improved text" in body

    def test_falls_back_on_unparseable_response(self):
        title, body = parse_review_response("not the expected format", "orig title", "orig body")
        assert title == "orig title"
        assert body == "orig body"

    def test_falls_back_on_empty_title_or_body(self):
        response = "TITLE: \nBODY:\n\n"
        title, body = parse_review_response(response, "orig title", "orig body")
        assert title == "orig title"
        assert body == "orig body"


class TestOfferLocalLlmReview:
    @mock.patch("builtins.input", return_value="n")
    def test_declines_llm_review(self, _mock_input):
        title, body = offer_local_llm_review("orig title", "orig body")
        assert (title, body) == ("orig title", "orig body")

    @mock.patch("b_create_issue.validate_ollama_connection", return_value=False)
    @mock.patch("builtins.input", return_value="y")
    def test_falls_back_when_ollama_unreachable(self, _mock_input, _mock_validate):
        title, body = offer_local_llm_review("orig title", "orig body")
        assert (title, body) == ("orig title", "orig body")

    @mock.patch("b_create_issue.fetch_ollama_review", return_value="")
    @mock.patch("b_create_issue.validate_ollama_connection", return_value=True)
    @mock.patch("builtins.input", return_value="y")
    def test_falls_back_on_empty_llm_response(self, _mock_input, _mock_validate, _mock_fetch):
        title, body = offer_local_llm_review("orig title", "orig body")
        assert (title, body) == ("orig title", "orig body")

    @mock.patch(
        "b_create_issue.fetch_ollama_review",
        return_value="TITLE: New title\nBODY:\n## What\n\nNew body\n",
    )
    @mock.patch("b_create_issue.validate_ollama_connection", return_value=True)
    @mock.patch("builtins.input", side_effect=["y", "y"])
    def test_applies_accepted_suggestion(self, _mock_input, _mock_validate, _mock_fetch):
        title, body = offer_local_llm_review("orig title", "orig body")
        assert title == "New title"
        assert "New body" in body

    @mock.patch(
        "b_create_issue.fetch_ollama_review",
        return_value="TITLE: New title\nBODY:\n## What\n\nNew body\n",
    )
    @mock.patch("b_create_issue.validate_ollama_connection", return_value=True)
    @mock.patch("builtins.input", side_effect=["y", "n"])
    def test_keeps_original_when_suggestion_rejected(
        self, _mock_input, _mock_validate, _mock_fetch
    ):
        title, body = offer_local_llm_review("orig title", "orig body")
        assert (title, body) == ("orig title", "orig body")
