import pytest

from backend.chat import mcp_tools_client


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:8001/mcp", True),
        ("http://127.0.0.1:8001/mcp", True),
        ("http://[::1]:8001/mcp", True),
        ("https://abc123.lambda-url.eu-west-1.on.aws/mcp", False),
        ("https://localhost.example.com/mcp", False),
    ],
)
def test_is_local_url(url, expected):
    assert mcp_tools_client._is_local_url(url) is expected
