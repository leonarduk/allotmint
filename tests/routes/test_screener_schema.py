import pytest
from fastapi import FastAPI

from backend.routes.screener import RankedFundamentals, router

# Fields declared on RankedFundamentals that are route-only (not present on
# allotmint_pro.screener.Fundamentals) and are therefore allowed to exist
# only on this side of the comparison in
# test_ranked_fundamentals_matches_allotmint_pro_fundamentals below. This is
# an explicit allowlist, not a subset comparison, per allotmint#6833
# acceptance criterion 4: a field missing from RankedFundamentals must fail,
# but a RankedFundamentals-only field is tolerated only if named here.
_ROUTE_ONLY_FIELDS = {"rank", "instrument_type"}


def test_screener_openapi_schema_matches_model_fields():
    """The OpenAPI schema for RankedFundamentals reflects the model's own
    fields exactly -- a genuine schema-generation check, not a hand-typed
    duplicate of the field list (allotmint#6833)."""
    app = FastAPI()
    app.include_router(router)

    schema = app.openapi()["components"]["schemas"]["RankedFundamentals"]

    assert set(schema["properties"]) == set(RankedFundamentals.model_fields)
    assert set(schema["required"]) == {"ticker", "rank"}


def test_ranked_fundamentals_matches_allotmint_pro_fundamentals():
    """Detect drift between RankedFundamentals and allotmint_pro.screener.Fundamentals.

    RankedFundamentals (backend/routes/screener.py) is a fixed BaseModel that
    hand-lists every field of the private allotmint_pro.screener.Fundamentals
    model, because FastAPI's response_model filtering silently drops any
    field a route returns that isn't declared on the response model. If
    Fundamentals ever gains a field without RankedFundamentals being updated
    to match, paid-tier /screener API responses would silently stop
    including it -- worse than a merely cosmetic schema bug, because nothing
    would fail anywhere to reveal it.

    This test compares the two field-name sets by introspection on both
    sides (RankedFundamentals.model_fields vs Fundamentals.model_fields) --
    no new hand-typed field list. It fails loudly wherever allotmint_pro is
    importable, and skips cleanly (green build) where it is not, so fork PRs
    and free-tier public CI are unaffected (allotmint#6833).
    """
    pytest.importorskip("allotmint_pro")
    from allotmint_pro.screener import Fundamentals

    pro_fields = set(Fundamentals.model_fields)
    route_fields = set(RankedFundamentals.model_fields) - _ROUTE_ONLY_FIELDS

    # A field present in Fundamentals but missing from RankedFundamentals is
    # the silent-data-loss case and must fail.
    missing_from_route = pro_fields - route_fields
    assert not missing_from_route, (
        "allotmint_pro.screener.Fundamentals has fields not declared on "
        f"RankedFundamentals: {sorted(missing_from_route)}. FastAPI's "
        "response_model filtering will silently drop them from every "
        "/screener API response -- add them to RankedFundamentals in "
        "backend/routes/screener.py."
    )

    # A field present only on RankedFundamentals is tolerated only if it is
    # an explicit, named exception (route-only fields like `rank`), never an
    # accident of using a one-directional subset comparison.
    route_only_extras = route_fields - pro_fields
    assert not route_only_extras, (
        "RankedFundamentals has fields not present on "
        f"allotmint_pro.screener.Fundamentals and not in _ROUTE_ONLY_FIELDS: "
        f"{sorted(route_only_extras)}. Either remove them or add them to "
        "_ROUTE_ONLY_FIELDS in this test if intentional."
    )
