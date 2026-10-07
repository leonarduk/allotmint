"""Tests for :mod:`backend.common.prices`."""

from __future__ import annotations

import json
import sys
import types
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.common import portfolio_utils, prices
from backend.common.portfolio_utils import DATA_BUCKET_ENV, PRICES_S3_KEY


@pytest.fixture(autouse=True)
def _reset_securities_cache():
    """Ensure each test observes a fresh ``get_security_meta`` cache.

    ``prices._SECURITIES`` is a module-level, process-lifetime cache (see
    allotmint#6908); tests that call ``get_security_meta``/
    ``_build_securities_from_portfolios`` with their own portfolio fixtures
    must not see state left over from a previous test.
    """
    prices._SECURITIES = None
    yield
    prices._SECURITIES = None


def test_close_on_falls_back_to_close_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should use the first available close column."""

    sample_date = date(2024, 5, 6)
    frame = pd.DataFrame({"Close": [99.25]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)

    captured: list[tuple[str, str, date, date]] = []

    def fake_load(sym: str, exch: str, start_date: date, end_date: date):
        captured.append((sym, exch, start_date, end_date))
        return frame

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load)

    result = prices._close_on("XYZ", "L", sample_date)

    assert result == pytest.approx(99.25)
    assert captured == [("XYZ", "L", sample_date, sample_date)]


def test_close_on_returns_none_when_no_price_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should return ``None`` if no recognised columns exist."""

    sample_date = date(2024, 5, 7)
    frame = pd.DataFrame({"open": [10.0], "high": [11.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(
        prices,
        "load_meta_timeseries_range",
        lambda sym, exch, start_date, end_date: frame,
    )

    assert prices._close_on("ABC", "N", sample_date) is None


def test_close_on_returns_none_for_nan_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should return ``None`` rather than propagate a NaN close price."""

    sample_date = date(2024, 5, 9)
    frame = pd.DataFrame({"Close": [float("nan")]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(
        prices,
        "load_meta_timeseries_range",
        lambda sym, exch, start_date, end_date: frame,
    )

    assert prices._close_on("ABC", "L", sample_date) is None


def test_close_on_converts_native_currency_to_gbp(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should convert native close prices to GBP when needed."""

    sample_date = date(2024, 5, 8)
    frame = pd.DataFrame({"Close": [100.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(prices, "load_meta_timeseries_range", lambda *args, **kwargs: frame)

    from backend.common import portfolio_utils

    monkeypatch.setattr(portfolio_utils, "_fx_to_base", lambda *_: 0.8)
    monkeypatch.setattr("backend.common.instruments.get_instrument_meta", lambda *_: {"currency": "USD"})

    assert prices._close_on("USDX", "US", sample_date) == pytest.approx(80.0)


def test_close_on_converts_gbx_pence_to_gbp(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should apply pence->GBP conversion through CurrencyNormaliser."""

    sample_date = date(2024, 5, 8)
    frame = pd.DataFrame({"Close": [250.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(prices, "load_meta_timeseries_range", lambda *args, **kwargs: frame)
    monkeypatch.setattr("backend.common.instruments.get_instrument_meta", lambda *_: {"currency": "GBX"})

    # GBX conversion is arithmetic (/100); FX resolver must not be called.
    monkeypatch.setattr(
        portfolio_utils,
        "_fx_to_base",
        lambda *_: (_ for _ in ()).throw(AssertionError("_fx_to_base should not run for GBX")),
    )

    assert prices._close_on("VOD", "L", sample_date) == pytest.approx(2.5)


def test_get_price_snapshot_handles_stale_and_missing_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_price_snapshot`` should correctly combine live and cached data."""

    tickers = ["ABC.L", "DEF.N", "GHI.L"]
    now = datetime.now(UTC)
    stale_ts = now - timedelta(minutes=30)
    last_trading_day = prices._nearest_weekday(date.today() - timedelta(days=1), forward=False)
    old_close_day = last_trading_day - timedelta(days=10)
    latest = {
        "ABC.L": (100.0, last_trading_day),
        "DEF.N": (55.0, last_trading_day),
        "GHI.L": (40.0, old_close_day),
    }

    monkeypatch.setattr(prices, "_load_latest_closes", lambda requested: latest)
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda requested: {
            "ABC.L": {"price": 101.0, "timestamp": now},
            "DEF.N": {"price": 55.0, "timestamp": stale_ts},
        },
    )

    mapping = {"ABC.L": ("ABC", "L"), "DEF.N": ("DEF", "N"), "GHI.L": ("GHI", "L")}
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: mapping.get(full))

    seven_day = last_trading_day - timedelta(days=7)
    thirty_day = last_trading_day - timedelta(days=30)
    ninety_day = last_trading_day - timedelta(days=90)
    one_year = last_trading_day - timedelta(days=365)

    close_lookup: dict[tuple[str, str, date], float | None] = {
        ("ABC", "L", seven_day): 95.0,
        ("ABC", "L", thirty_day): 90.0,
        ("ABC", "L", ninety_day): 80.0,
        ("ABC", "L", one_year): 0,
        ("DEF", "N", seven_day): None,
        ("DEF", "N", thirty_day): 50.0,
        ("GHI", "L", seven_day): 39.0,
        ("GHI", "L", thirty_day): 38.0,
    }

    requested: list[tuple[str, str, date]] = []

    def fake_close_on(sym: str, exch: str, requested_date: date):
        requested.append((sym, exch, requested_date))
        return close_lookup.get((sym, exch, requested_date))

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot(tickers)

    info_abc = snapshot["ABC.L"]
    assert info_abc["last_price"] == pytest.approx(101.0)
    assert info_abc["is_stale"] is False
    assert info_abc["last_price_time"] == now.isoformat().replace("+00:00", "Z")
    assert info_abc["last_price_date"] == last_trading_day.isoformat()
    assert info_abc["change_7d_pct"] == pytest.approx((101.0 / 95.0 - 1.0) * 100.0)
    assert info_abc["change_30d_pct"] == pytest.approx((101.0 / 90.0 - 1.0) * 100.0)
    assert info_abc["change_90d_pct"] == pytest.approx((101.0 / 80.0 - 1.0) * 100.0)
    # A zero (or missing) anchor close yields no change rather than a division error.
    assert info_abc["change_1y_pct"] is None

    info_def = snapshot["DEF.N"]
    assert info_def["last_price"] == pytest.approx(55.0)
    assert info_def["is_stale"] is True
    assert info_def["last_price_time"] == stale_ts.isoformat().replace("+00:00", "Z")
    assert info_def["change_7d_pct"] is None
    assert info_def["change_30d_pct"] == pytest.approx((55.0 / 50.0 - 1.0) * 100.0)

    info_ghi = snapshot["GHI.L"]
    assert info_ghi["last_price"] == pytest.approx(40.0)
    assert info_ghi["is_stale"] is True
    assert info_ghi["last_price_time"] is None
    assert info_ghi["last_price_date"] == old_close_day.isoformat()
    assert info_ghi["change_7d_pct"] == pytest.approx((40.0 / 39.0 - 1.0) * 100.0)
    assert info_ghi["change_30d_pct"] == pytest.approx((40.0 / 38.0 - 1.0) * 100.0)

    assert requested == [
        (sym, exch, anchor)
        for sym, exch in (("ABC", "L"), ("DEF", "N"), ("GHI", "L"))
        for anchor in (seven_day, thirty_day, ninety_day, one_year)
    ]


def test_get_price_snapshot_treats_nan_price_as_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """A NaN live/last-close price must not be written into the snapshot as ``last_price``."""

    tickers = ["NAN_LIVE.L", "NAN_CACHED.L"]

    monkeypatch.setattr(
        prices,
        "_load_latest_closes",
        lambda requested: {"NAN_LIVE.L": (12.0, None), "NAN_CACHED.L": (float("nan"), None)},
    )
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda requested: {"NAN_LIVE.L": {"price": float("nan"), "timestamp": datetime.now(UTC)}},
    )
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None)

    snapshot = prices.get_price_snapshot(tickers)

    assert snapshot["NAN_LIVE.L"]["last_price"] is None
    assert snapshot["NAN_CACHED.L"]["last_price"] is None


# ---------------------------------------------------------------------------
# refresh_prices() S3 upload behaviour
# ---------------------------------------------------------------------------


_STUB_SNAPSHOT = {"STUB.L": {"last_price": 1.0, "price_currency": "GBP", "is_stale": False}}


def _stub_refresh_prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Wire up minimal mocks so refresh_prices() can run without real data."""
    prices_file = tmp_path / "latest_prices.json"
    monkeypatch.setattr(prices.config, "prices_json", prices_file, raising=False)
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["STUB.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda tickers: _STUB_SNAPSHOT)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", lambda s: None)
    monkeypatch.setattr(prices, "check_price_alerts", lambda: None)


def test_refresh_prices_uploads_to_s3_in_aws_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog):
    """refresh_prices() must call s3.put_object with PRICES_S3_KEY when app_env==aws."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(DATA_BUCKET_ENV, "test-bucket")

    put_calls: list[dict] = []

    class FakeS3:
        def put_object(self, **kwargs):
            put_calls.append(kwargs)

    fake_boto3 = types.SimpleNamespace(client=lambda svc: FakeS3())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    import logging

    with caplog.at_level(logging.INFO):
        prices.refresh_prices()

    assert len(put_calls) == 1, f"Expected exactly one put_object call; got {put_calls}"
    assert put_calls[0]["Bucket"] == "test-bucket"
    assert put_calls[0]["Key"] == PRICES_S3_KEY
    assert "Uploaded price snapshot" in caplog.text


@pytest.mark.parametrize("source", ["last_close", "live_quote"])
@pytest.mark.parametrize("ticker", ["AV", "CLIG", "HICL", "ADM"])
def test_refresh_prices_persists_scaled_gbp_not_raw_pence(
    ticker: str, source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#8923: ``latest_prices.json`` stores scaled GBP, not the raw pence value.

    Uses the repo's real ``data/scaling_overrides.json`` for the four tickers
    #8589 corrected, so dropping one from the table fails here. Covers both
    sources :func:`get_price_snapshot` can take ``last_price`` from: the
    cached close (``holding_utils.load_latest_closes``) and the live quote
    (``holding_utils.load_live_prices``, preferred when present). Either way
    the raw pence value (3588) gets the 0.01 override before persistence, so
    the snapshot carries GBP 35.88. This is why an override-table change needs
    a snapshot refresh (done on every deploy).
    """
    from types import SimpleNamespace

    from backend.common import holding_utils
    from backend.utils import timeseries_helpers as th

    repo_root = Path(__file__).resolve().parents[3]
    assert (repo_root / "data" / "scaling_overrides.json").exists()
    # Repo table only: no DATA_ROOT overlay from the developer's machine.
    monkeypatch.setattr(th, "config", SimpleNamespace(repo_root=repo_root, data_root=None))
    full_ticker = f"{ticker}.L"

    if source == "last_close":
        cached = pd.DataFrame({"Date": [date.today() - timedelta(days=1)], "Close": [3588.0]})
        monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: cached)
        monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    else:
        monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers, **k: {})
        quote = {
            "symbol": full_ticker,
            "regularMarketPrice": 3588.0,
            "regularMarketTime": int(datetime.now(UTC).timestamp()),
        }
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"quoteResponse": {"result": [quote]}},
        )
        monkeypatch.setattr(holding_utils.requests, "get", lambda *a, **k: response)
    # Metadata wrongly says GBP (the AV/CLIG/HICL failure mode), so only the
    # override can turn 3588 into 35.88.
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda *_: {"currency": "GBP"})

    prices_file = tmp_path / "latest_prices.json"
    monkeypatch.setattr(prices.config, "prices_json", prices_file, raising=False)
    monkeypatch.setattr(prices.config, "app_env", "local", raising=False)
    monkeypatch.setattr(prices, "refresh_universe", lambda: [full_ticker])
    monkeypatch.setattr(prices, "_close_on", lambda *a, **k: None)
    monkeypatch.setattr(prices, "_refresh_reference_data", lambda tickers: None)
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", lambda s: None)
    monkeypatch.setattr(prices, "check_price_alerts", lambda: None)

    prices.refresh_prices()

    persisted = json.loads(prices_file.read_text())
    assert persisted[full_ticker]["last_price"] == pytest.approx(35.88)
    assert persisted[full_ticker]["price_currency"] == "GBP"
    # Only the live path stamps a quote time, so this pins which source ran.
    assert (persisted[full_ticker]["last_price_time"] is not None) == (source == "live_quote")


def test_snapshot_deploy_ordering_claims_hold() -> None:
    """#8923: pin the deploy-ordering chain the ``prices`` docstring relies on.

    The module docstring says an override-table change reaches the deployed
    snapshot without an extra workflow step because (1) the table is tracked
    in git and baked into the Lambda image, (2) ``PriceRefreshLambda`` is built
    from that image and a REQUEST_RESPONSE ``PriceRefreshOnDeploy`` Trigger
    runs it during the CDK deploy, and (3) the "Warm price snapshot" workflow
    step invokes it again after the deploy. If any link is removed, this fails
    and the docstring must be revisited.
    """
    import yaml

    repo_root = Path(__file__).resolve().parents[3]

    # (1) Table is part of the image build context.
    assert (repo_root / "data" / "scaling_overrides.json").exists()
    dockerfile = (repo_root / "backend" / "Dockerfile.lambda").read_text(encoding="utf-8")
    assert "COPY data/ /var/task/data/" in dockerfile
    dockerignore = (repo_root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert not any(line.strip().rstrip("/") == "data" for line in dockerignore)

    # (2) Refresh Lambda uses that image and is triggered synchronously on deploy.
    stack = (repo_root / "cdk" / "stacks" / "backend_lambda_stack.py").read_text(encoding="utf-8")
    refresh_block = stack[stack.index("refresh_code = ") : stack.index('"PriceRefreshLambda",')]
    assert 'file="backend/Dockerfile.lambda"' in refresh_block
    assert "backend.lambda_api.price_refresh.lambda_handler" in refresh_block
    trigger_block = stack[stack.index('"PriceRefreshOnDeploy",') :][:300]
    assert "handler=refresh_fn" in trigger_block
    assert "InvocationType.REQUEST_RESPONSE" in trigger_block

    # (3) Workflow warms the snapshot after the CDK deploy.
    workflow_path = repo_root / ".github" / "workflows" / "deploy-lambda.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    names = [step.get("name", "") for step in workflow["jobs"]["deploy"]["steps"]]
    assert names.index("Warm price snapshot") > names.index("Deploy BackendLambdaStack")

    # Caveat in the docstring: a bucket-root table can override the git copy,
    # both via the pre-build S3 sync into data/ and via the DATA_ROOT overlay.
    assert names.index("Sync data from S3") < names.index("Deploy BackendLambdaStack")


def test_data_root_override_table_wins_over_bundled_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#8923 caveat: a bucket-derived ``DATA_ROOT`` table beats the git table.

    The ``prices`` docstring warns that a stale bucket copy of
    ``scaling_overrides.json`` would keep the snapshot wrong after a git fix;
    this pins that precedence so the warning can't silently go stale.
    """
    from types import SimpleNamespace

    from backend.utils import timeseries_helpers as th

    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "scaling_overrides.json").write_text('{"L": {"ADM": 0.01}}')
    data_root = tmp_path / "bucket"
    data_root.mkdir()
    (data_root / "scaling_overrides.json").write_text('{"L": {"ADM": 1.0}}')
    monkeypatch.setattr(th, "config", SimpleNamespace(repo_root=repo_root, data_root=data_root))

    assert th.get_scaling_override("ADM", "L", None) == 1.0


def test_refresh_prices_s3_upload_failure_logs_warning_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
):
    """If the S3 upload fails, refresh_prices() must log WARNING and not re-raise."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(DATA_BUCKET_ENV, "test-bucket")

    class FakeS3:
        def put_object(self, **kwargs):
            raise OSError("network failure")

    fake_boto3 = types.SimpleNamespace(client=lambda svc: FakeS3())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    import logging

    with caplog.at_level(logging.WARNING):
        result = prices.refresh_prices()

    assert "Failed to upload price snapshot to S3" in caplog.text
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert (
        error_records == []
    ), f"S3 upload failure must log WARNING, not ERROR; got: {[r.message for r in error_records]}"
    assert result is not None, "refresh_prices() must still return normally after S3 upload failure"


def test_refresh_prices_skips_s3_when_data_bucket_not_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog):
    """refresh_prices() must log a WARNING and skip S3 when DATA_BUCKET env var is absent."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "aws", raising=False)
    monkeypatch.delenv(DATA_BUCKET_ENV, raising=False)

    import logging

    with caplog.at_level(logging.WARNING):
        prices.refresh_prices()

    assert "DATA_BUCKET not set" in caplog.text


def test_refresh_prices_does_not_upload_to_s3_in_local_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """refresh_prices() must not call s3.put_object when app_env != 'aws'."""
    _stub_refresh_prices(tmp_path, monkeypatch)
    monkeypatch.setattr(prices.config, "app_env", "local", raising=False)

    put_calls: list = []

    class FakeS3:
        def put_object(self, **kwargs):
            put_calls.append(kwargs)

    fake_boto3 = types.SimpleNamespace(client=lambda svc: FakeS3())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    prices.refresh_prices()

    assert put_calls == [], "S3 upload must not happen in non-AWS environments"


def test_build_securities_and_get_security_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Security metadata should be derived from current portfolios."""

    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "abc", "name": "Alpha", "instrument_type": "stock"},
                        {"ticker": "def"},
                        {"ticker": ""},
                        {},
                    ]
                }
            ]
        },
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "GHI", "name": "Gamma"},
                        {"ticker": None},
                    ]
                }
            ]
        },
    ]

    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)

    securities = prices._build_securities_from_portfolios()

    assert securities == {
        "ABC": {"ticker": "ABC", "name": "Alpha", "instrument_type": "stock"},
        "DEF": {"ticker": "DEF", "name": "DEF", "instrument_type": None},
        "GHI": {"ticker": "GHI", "name": "Gamma", "instrument_type": None},
    }

    assert prices.get_security_meta("abc") == {"ticker": "ABC", "name": "Alpha", "instrument_type": "stock"}
    assert prices.get_security_meta("DEF") == {"ticker": "DEF", "name": "DEF", "instrument_type": None}
    assert prices.get_security_meta("missing") is None


def test_build_securities_prefers_canonical_instrument_type_over_holding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical instrument metadata should win over a raw holding's field.

    Regression test for allotmint#6902: raw holding documents (CSV-import /
    transaction-rebuild paths) frequently carry a stale or absent
    ``instrument_type`` while the canonical instrument metadata file has the
    correct, current value.
    """

    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "ABC", "name": "Alpha", "instrument_type": "stale"},
                    ]
                }
            ]
        }
    ]
    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta",
        lambda t: {"instrumentType": "ETF"} if t == "ABC" else {},
    )

    securities = prices._build_securities_from_portfolios()

    assert securities["ABC"]["instrument_type"] == "ETF"


def test_get_security_meta_resolves_watchlist_only_symbol_from_canonical_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A symbol with no holding at all (e.g. a Screener watchlist entry) must
    still resolve ``instrument_type`` via canonical instrument metadata.
    """

    monkeypatch.setattr(prices, "list_portfolios", lambda: [])
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta",
        lambda t: {"assetClass": "Commodity"} if t == "GOLD.L" else {},
    )

    meta = prices.get_security_meta("GOLD.L")

    assert meta is not None
    # Legacy capitalised asset class resolves to the canonical value (#9196).
    assert meta["instrument_type"] == "commodity"


@pytest.mark.parametrize(
    "meta,expected",
    [
        # Persisted before #9196 (or a stale S3/live-data-root copy).
        ({"asset_class": "Equity"}, "equity"),
        ({"asset_class": "Bond"}, "bond"),
        ({"assetClass": "Commodity"}, "commodity"),
        # Reclassified by #9196.
        ({"asset_class": "equity"}, "equity"),
        # An explicit type always wins and is returned verbatim.
        ({"instrumentType": "ETF", "asset_class": "Equity"}, "ETF"),
    ],
)
def test_resolve_instrument_type_accepts_legacy_asset_class_casing(
    monkeypatch: pytest.MonkeyPatch, meta: dict, expected: str
) -> None:
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta",
        lambda t: {"name": "Legacy", **meta} if t == "LEG.L" else {},
    )

    assert prices._resolve_instrument_type("LEG.L") == expected


def test_resolve_instrument_type_resolves_bare_watchlist_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare watchlist symbol (e.g. "PFE") must resolve via the persisted
    exchange-qualified instrument record (e.g. ``data/instruments/N/PFE.json``
    -> ``PFE.N``) rather than falling into a nonexistent ``Unknown/`` folder.

    Regression test for allotmint#6908 review comment: ``get_instrument_meta``
    requires an exchange-qualified ticker, so passing a bare ticker straight
    through always returned ``{}``/``None`` for exactly the watchlist-only
    symbols this fallback was meant to cover.
    """

    assert prices._resolve_instrument_type("PFE") == "equity"


def test_get_security_meta_resolves_bare_watchlist_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_security_meta`` should resolve a bare, unheld watchlist symbol
    to its canonical instrument type via the persisted exchange alias.
    """

    monkeypatch.setattr(prices, "list_portfolios", lambda: [])

    meta = prices.get_security_meta("PFE")

    assert meta is not None
    assert meta["instrument_type"] == "equity"


def test_get_security_meta_caches_securities_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_security_meta`` must not rebuild the securities map on every
    call -- the full portfolios/accounts/holdings scan (with a potential S3
    GetObject per distinct ticker) should run at most once per cache
    lifetime, not once per screener result row.

    Regression test for allotmint#6908 review comment: the screener's
    ``_apply_instrument_type`` calls ``get_security_meta()`` once per result
    row (~500 rows for the default S&P 500 screener), so an unmemoized
    rebuild ran up to 500x per request.
    """

    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "ABC", "name": "Alpha", "instrument_type": "stock"},
                    ]
                }
            ]
        }
    ]

    call_count = 0
    real_build = prices._build_securities_from_portfolios

    def counting_build():
        nonlocal call_count
        call_count += 1
        return real_build()

    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(prices, "_build_securities_from_portfolios", counting_build)

    first = prices.get_security_meta("ABC")
    second = prices.get_security_meta("DEF")

    assert first == {"ticker": "ABC", "name": "Alpha", "instrument_type": "stock"}
    assert second is None
    assert call_count == 1, f"Expected the securities map to be built once; built {call_count} times"


def test_last_close_fallback_snapshot_does_not_double_convert_fx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USD last-close fallback should remain single-converted when aggregated."""

    ticker = "USDX.US"
    monkeypatch.setattr(prices, "_load_latest_closes", lambda _: {ticker: (80.0, None)})
    monkeypatch.setattr(prices, "load_live_prices", lambda _: {})
    monkeypatch.setattr(prices, "_close_on", lambda *_: 80.0)
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("USDX", "US"))

    snapshot = prices.get_price_snapshot([ticker])
    assert snapshot[ticker]["price_currency"] == "GBP"
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot, raising=False)
    monkeypatch.setattr("backend.common.instrument_api._resolve_full_ticker", lambda t, _: ("USDX", "US"))
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda _: {"currency": "USD", "name": "USD X"})
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda _: {})
    monkeypatch.setattr("backend.common.instrument_api.price_change_pct", lambda *_: None)
    monkeypatch.setattr(portfolio_utils, "_fx_to_base", lambda c, b, cache: 0.8 if c == "USD" else 1.0)

    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": ticker,
                        "exchange": "US",
                        "units": 2,
                        "cost_basis_gbp": 100.0,
                        "currency": "USD",
                    }
                ]
            }
        ]
    }

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert rows[0]["last_price_gbp"] == pytest.approx(80.0)
    assert rows[0]["market_value_gbp"] == pytest.approx(160.0)


def test_last_close_fallback_snapshot_marks_gbx_prices_as_gbp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GBX instruments should not be divided twice when snapshot uses last-close fallback."""

    ticker = "VOD.L"
    monkeypatch.setattr(prices, "_load_latest_closes", lambda _: {ticker: (1.103, None)})
    monkeypatch.setattr(prices, "load_live_prices", lambda _: {})
    monkeypatch.setattr(prices, "_close_on", lambda *_: 1.103)
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("VOD", "L"))

    snapshot = prices.get_price_snapshot([ticker])
    assert snapshot[ticker]["price_currency"] == "GBP"

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot, raising=False)
    monkeypatch.setattr("backend.common.instrument_api._resolve_full_ticker", lambda t, _: ("VOD", "L"))
    monkeypatch.setattr(
        portfolio_utils,
        "get_instrument_meta",
        lambda _: {"currency": "GBX", "name": "Vodafone"},
    )
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda _: {"currency": "GBX"})
    monkeypatch.setattr("backend.common.instrument_api.price_change_pct", lambda *_: None)

    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": ticker,
                        "exchange": "L",
                        "units": 290,
                        "cost_basis_gbp": 200.46,
                        "currency": "GBX",
                    }
                ]
            }
        ]
    }

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert rows[0]["last_price_gbp"] == pytest.approx(1.103)
    assert rows[0]["market_value_gbp"] == pytest.approx(319.87)
    assert rows[0]["gain_gbp"] == pytest.approx(119.41)


def test_close_on_returns_none_when_fx_lookup_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should return ``None`` when FX conversion cannot be resolved."""

    sample_date = date(2024, 5, 9)
    frame = pd.DataFrame({"Close": [100.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(prices, "load_meta_timeseries_range", lambda *args, **kwargs: frame)

    from backend.common import portfolio_utils

    monkeypatch.setattr(portfolio_utils, "_fx_to_base", lambda *_: None)
    monkeypatch.setattr("backend.common.instruments.get_instrument_meta", lambda *_: {"currency": "USD"})

    assert prices._close_on("USDX", "US", sample_date) is None
