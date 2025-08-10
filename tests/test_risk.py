from unittest.mock import patch

from backend.common import risk


@patch("backend.common.portfolio_utils.compute_owner_performance", return_value=[])
def test_compute_portfolio_var_accepts_percentage(mock_perf):
    """compute_portfolio_var should accept confidence as a percentage."""

    result = risk.compute_portfolio_var("alex", confidence=95)

    # Confidence should be converted to the fractional form internally
    assert result["confidence"] == 0.95
