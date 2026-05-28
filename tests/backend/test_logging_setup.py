import pytest

from backend.logging_setup import sanitise_log_value


@pytest.mark.parametrize(
    "value, expected",
    [
        ("hello", "hello"),
        ("ticker\nnewline", "tickernewline"),
        ("ticker\rreturn", "tickerreturn"),
        ("multi\r\nline", "multiline"),
        (123, "123"),
        (None, "None"),
        ("safe value", "safe value"),
    ],
)
def test_sanitise_log_value(value, expected):
    assert sanitise_log_value(value) == expected
