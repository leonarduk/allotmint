"""Unit tests for remote_openai_common helpers."""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest

# Import the module under test
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent.parent.parent / "scripts" / "developer_tools" / "lib"),
)
from remote_openai_common import (
    extract_remote_openai_review,
    fetch_remote_openai_review,
    get_remote_llm_api_key,
    get_remote_llm_endpoint,
    get_remote_llm_model,
)


class TestGetRemoteLlmEndpoint:
    def test_default_empty(self):
        """Should return empty string when env var not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert get_remote_llm_endpoint() == ""

    def test_custom_endpoint(self):
        """Should return custom endpoint from env var."""
        with mock.patch.dict(
            os.environ, {"REMOTE_LLM_ENDPOINT": "https://my-instance.example.com"}
        ):
            assert get_remote_llm_endpoint() == "https://my-instance.example.com"


class TestGetRemoteLlmModel:
    def test_default_fallback(self):
        """Should return fallback placeholder when env var not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert get_remote_llm_model() == "set-REMOTE_LLM_MODEL"

    def test_custom_model(self):
        """Should return custom model from env var."""
        with mock.patch.dict(
            os.environ, {"REMOTE_LLM_MODEL": "deepseek-v4-flash"}
        ):
            assert get_remote_llm_model() == "deepseek-v4-flash"


class TestGetRemoteLlmApiKey:
    def test_default_empty(self):
        """Should return empty string when env var not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert get_remote_llm_api_key() == ""

    def test_custom_api_key(self):
        """Should return API key from env var."""
        with mock.patch.dict(
            os.environ, {"REMOTE_LLM_API_KEY": "sk-abc123"}
        ):
            assert get_remote_llm_api_key() == "sk-abc123"


class TestExtractRemoteOpenAiReview:
    def test_extract_content(self):
        """Should extract review from choices[0].message.content."""
        data = {
            "choices": [
                {"message": {"content": "  This code looks good.  \n"}}
            ]
        }
        assert extract_remote_openai_review(data) == "This code looks good."

    def test_empty_content(self):
        """Should return empty string for empty content."""
        data = {"choices": [{"message": {"content": ""}}]}
        assert extract_remote_openai_review(data) == ""

    def test_no_choices(self):
        """Should return empty string when choices list is empty."""
        data = {"choices": []}
        assert extract_remote_openai_review(data) == ""

    def test_missing_message(self):
        """Should return empty string when message key is missing."""
        data = {"choices": [{}]}
        assert extract_remote_openai_review(data) == ""

    def test_content_is_none(self):
        """Should return empty string when content is None."""
        data = {"choices": [{"message": {"content": None}}]}
        assert extract_remote_openai_review(data) == ""


class TestFetchRemoteOpenAiReview:
    @mock.patch("urllib.request.urlopen")
    def test_successful_review(self, mock_urlopen):
        """Should POST to the endpoint and return extracted content."""
        response_data = {
            "choices": [
                {
                    "message": {
                        "content": "This PR looks good.\n\nNo issues found."
                    }
                }
            ]
        }
        mock_response = mock.MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        review = fetch_remote_openai_review(
            "https://my-instance.example.com",
            "deepseek-v4-flash",
            "sk-abc123",
            "Test prompt",
        )
        assert "This PR looks good" in review
        assert "No issues found" in review

    @mock.patch("urllib.request.urlopen")
    def test_strips_trailing_slash_from_endpoint(self, mock_urlopen):
        """Should not produce double slashes when endpoint has trailing slash."""
        mock_response = mock.MagicMock()
        mock_response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "ok"}}]}
        ).encode()
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        fetch_remote_openai_review(
            "https://my-instance.example.com/",
            "deepseek-v4-flash",
            "sk-abc123",
            "Test prompt",
        )

        # Verify the request URL was built correctly
        call_args = mock_urlopen.call_args[0][0]
        assert call_args.full_url == (
            "https://my-instance.example.com/v1/chat/completions"
        )

    @mock.patch("urllib.request.urlopen")
    def test_auth_header_when_api_key_set(self, mock_urlopen):
        """Should include Authorization header when API key is provided."""
        mock_response = mock.MagicMock()
        mock_response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "ok"}}]}
        ).encode()
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        fetch_remote_openai_review(
            "https://my-instance.example.com",
            "deepseek-v4-flash",
            "sk-abc123",
            "Test prompt",
        )

        call_args = mock_urlopen.call_args[0][0]
        assert call_args.headers["Authorization"] == "Bearer sk-abc123"

    @mock.patch("urllib.request.urlopen")
    def test_no_auth_header_when_api_key_empty(self, mock_urlopen):
        """Should omit Authorization header when API key is empty."""
        mock_response = mock.MagicMock()
        mock_response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "ok"}}]}
        ).encode()
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        fetch_remote_openai_review(
            "https://my-instance.example.com",
            "deepseek-v4-flash",
            "",
            "Test prompt",
        )

        call_args = mock_urlopen.call_args[0][0]
        assert "Authorization" not in call_args.headers

    @mock.patch("urllib.request.urlopen")
    def test_connection_error(self, mock_urlopen):
        """Should exit with error on connection failure."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with pytest.raises(SystemExit) as exc_info:
            fetch_remote_openai_review(
                "https://my-instance.example.com",
                "deepseek-v4-flash",
                "sk-abc123",
                "Test prompt",
            )
        assert exc_info.value.code == 1

    @mock.patch("urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        """Should exit with error on HTTP error."""
        import urllib.error

        error = urllib.error.HTTPError(
            "https://my-instance.example.com/v1/chat/completions",
            404,
            "Not Found",
            {},
            None,
        )
        error.read = mock.MagicMock(return_value=b"model not found")
        mock_urlopen.side_effect = error

        with pytest.raises(SystemExit) as exc_info:
            fetch_remote_openai_review(
                "https://my-instance.example.com",
                "nonexistent",
                "sk-abc123",
                "Test prompt",
            )
        assert exc_info.value.code == 1

    @mock.patch("urllib.request.urlopen")
    def test_invalid_json_response(self, mock_urlopen):
        """Should exit with error on invalid JSON response."""
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as exc_info:
            fetch_remote_openai_review(
                "https://my-instance.example.com",
                "deepseek-v4-flash",
                "sk-abc123",
                "Test prompt",
            )
        assert exc_info.value.code == 1

    @mock.patch("urllib.request.urlopen")
    def test_read_timeout(self, mock_urlopen):
        """A stall mid-read raises a bare TimeoutError, not URLError -- must
        still exit cleanly rather than propagate as an uncaught exception."""
        mock_response = mock.MagicMock()
        mock_response.read.side_effect = TimeoutError(
            "The read operation timed out"
        )
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as exc_info:
            fetch_remote_openai_review(
                "https://my-instance.example.com",
                "deepseek-v4-flash",
                "sk-abc123",
                "Test prompt",
            )
        assert exc_info.value.code == 1
