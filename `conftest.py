# This file should be in the root of the tests directory
import pytest

@pytest.fixture(scope="session")
def jwt_secret():
    return "your_jwt_secret_here"
