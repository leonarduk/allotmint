"""Unit tests for ollama_common helpers."""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest

# Import the module under test
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))
from ollama_common import (
    extract_ollama_review,
    fetch_ollama_review,
    get_ollama_endpoint,
    get_ollama_model,
    list_available_models,
    validate_ollama_connection,
)


class TestGetOllamaEndpoint:
    def test_default_endpoint(self):
        """Should return default localhost:11434 when env var not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert get_ollama_endpoint() == "http://localhost:11434"

    def test_custom_endpoint(self):
        """Should return custom endpoint from env var."""
        with mock.patch.dict(os.environ, {"OLLAMA_ENDPOINT": "http://192.168.1.100:11434"}):
            assert get_ollama_endpoint() == "http://192.168.1.100:11434"


class TestGetOllamaModel:
    def test_default_model(self):
        """Should return default neural-chat when env var not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert get_ollama_model() == "neural-chat"

    def test_custom_model(self):
        """Should return custom model from env var."""
        with mock.patch.dict(os.environ, {"OLLAMA_MODEL": "mistral"}):
            assert get_ollama_model() == "mistral"


class TestListAvailableModels:
    @mock.patch("urllib.request.urlopen")
    def test_successful_model_list(self, mock_urlopen):
        """Should return list of models from Ollama API."""
        response_data = {"models": [{"name": "neural-chat"}, {"name": "mistral"}, {"name": "codellama"}]}
        mock_response = mock.MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        models = list_available_models("http://localhost:11434")
        assert models == ["neural-chat", "mistral", "codellama"]

    @mock.patch("urllib.request.urlopen")
    def test_ollama_unreachable(self, mock_urlopen):
        """Should return empty list when Ollama is unreachable."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        models = list_available_models("http://localhost:11434")
        assert models == []

    @mock.patch("urllib.request.urlopen")
    def test_invalid_json_response(self, mock_urlopen):
        """Should return empty list on invalid JSON response."""
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b"invalid json"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        models = list_available_models("http://localhost:11434")
        assert models == []


class TestValidateOllamaConnection:
    @mock.patch("ollama_common.list_available_models")
    def test_valid_connection(self, mock_list_models):
        """Should return True when models are available."""
        mock_list_models.return_value = ["neural-chat", "mistral"]
        assert validate_ollama_connection("http://localhost:11434") is True

    @mock.patch("ollama_common.list_available_models")
    def test_no_connection(self, mock_list_models):
        """Should return False when no models available."""
        mock_list_models.return_value = []
        assert validate_ollama_connection("http://localhost:11434") is False


class TestExtractOllamaReview:
    def test_extract_response_field(self):
        """Should extract review from response field."""
        data = {"response": "  This code looks good.  \n"}
        assert extract_ollama_review(data) == "This code looks good."

    def test_empty_response(self):
        """Should handle empty response."""
        data = {"response": ""}
        assert extract_ollama_review(data) == ""

    def test_missing_response_field(self):
        """Should return empty string when response field missing."""
        data = {}
        assert extract_ollama_review(data) == ""


class TestFetchOllamaReview:
    @mock.patch("urllib.request.urlopen")
    def test_successful_review(self, mock_urlopen):
        """Should fetch and return review from Ollama."""
        response_data = {"response": "This PR looks good.\n\nNo issues found."}
        mock_response = mock.MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        review = fetch_ollama_review("http://localhost:11434", "neural-chat", "Test prompt")
        assert "This PR looks good" in review
        assert "No issues found" in review

    @mock.patch("urllib.request.urlopen")
    def test_connection_error(self, mock_urlopen):
        """Should exit with error on connection failure."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with pytest.raises(SystemExit) as exc_info:
            fetch_ollama_review("http://localhost:11434", "neural-chat", "Test prompt")
        assert exc_info.value.code == 1

    @mock.patch("urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        """Should exit with error on HTTP error."""
        import urllib.error

        error = urllib.error.HTTPError(
            "http://localhost:11434/api/generate", 404, "Not Found", {}, None
        )
        error.read = mock.MagicMock(return_value=b"model not found")
        mock_urlopen.side_effect = error

        with pytest.raises(SystemExit) as exc_info:
            fetch_ollama_review("http://localhost:11434", "nonexistent", "Test prompt")
        assert exc_info.value.code == 1

    @mock.patch("urllib.request.urlopen")
    def test_invalid_json_response(self, mock_urlopen):
        """Should exit with error on invalid JSON response."""
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as exc_info:
            fetch_ollama_review("http://localhost:11434", "neural-chat", "Test prompt")
        assert exc_info.value.code == 1
