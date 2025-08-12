import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_var():
    """Dummy fixture to satisfy tests expecting a mock var function."""
    return MagicMock()

@pytest.fixture
def mock_sharpe():
    return MagicMock()
