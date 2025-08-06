# backend/utils/currency_utils.py

ISIN_TO_CURRENCY = {
    "GB": "GBP",
    "US": "USD",
    "IE": "GBP",
    "DE": "EUR",
    "FR": "EUR",
    "CH": "CHF",
    "JP": "JPY",
    "CA": "CAD",
    "AU": "AUD",
    "SG": "SGD",
    # Add more as needed
}

def currency_from_isin(isin: str) -> str:
    """
    Extracts currency from ISIN prefix using ISO 3166 mapping.
    Defaults to GBP if prefix not recognised.
    """
    prefix = isin[:2].upper()
    return ISIN_TO_CURRENCY.get(prefix, "GBP")
