import pytest

from backend.utils.growth_stage import get_growth_stage


@pytest.mark.parametrize(
    "days_held,current_price,target_price,expected_stage,expected_message",
    [
        (None, 90.0, 100.0, "seed", None),
        (45, None, None, "growing", None),
        (200, None, None, "harvest", "Long-term hold – review position."),
        (10, 105.0, 100.0, "harvest", "Target met – consider selling."),
    ],
)
def test_get_growth_stage(days_held, current_price, target_price, expected_stage, expected_message):
    info = get_growth_stage(days_held=days_held, current_price=current_price, target_price=target_price)
    assert info["stage"] == expected_stage
    if expected_message is not None:
        assert info["message"] == expected_message

