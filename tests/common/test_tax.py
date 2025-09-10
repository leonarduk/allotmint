from backend.common.tax import harvest_losses


def test_harvest_losses_filters_and_rounds():
    positions = [
        {"ticker": "GOOD", "basis": 100.0, "price": 89.123},  # valid loss
        {"ticker": "LOW", "basis": 100.0, "price": 95.0},    # below threshold
        {"ticker": "BADBASIS", "basis": "oops", "price": 50.0},  # malformed basis
        {"ticker": "BADPRICE", "basis": 100.0, "price": "oops"},  # malformed price
    ]
    result = harvest_losses(positions, threshold=0.1)
    assert result == [{"ticker": "GOOD", "loss": 10.88}]
    assert result[0]["loss"] == 10.88

