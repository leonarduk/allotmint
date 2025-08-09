"""Lambda entry point to refresh prices on a schedule."""
from backend.common.prices import refresh_prices

def lambda_handler(event, context):
    return refresh_prices()
