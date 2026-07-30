from .conftest import jwt_secret

def test_example(jwt_secret):
    assert jwt_secret == "your_jwt_secret_here"
