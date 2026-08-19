from fastapi import FastAPI

from backend.routes.screener import router


def test_screener_openapi_schema_includes_fundamental_fields_without_pro_package():
    app = FastAPI()
    app.include_router(router)

    schema = app.openapi()["components"]["schemas"]["RankedFundamentals"]

    assert set(schema["properties"]) == {
        "ticker",
        "name",
        "peg_ratio",
        "pe_ratio",
        "de_ratio",
        "lt_de_ratio",
        "interest_coverage",
        "current_ratio",
        "quick_ratio",
        "fcf",
        "eps",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "ebitda_margin",
        "roa",
        "roe",
        "roi",
        "dividend_yield",
        "dividend_payout_ratio",
        "beta",
        "shares_outstanding",
        "float_shares",
        "market_cap",
        "high_52w",
        "low_52w",
        "avg_volume",
        "rank",
    }
    assert set(schema["required"]) == {"ticker", "rank"}
