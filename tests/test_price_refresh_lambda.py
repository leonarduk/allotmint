import importlib
import sys
from types import SimpleNamespace

import backend.common.prices as prices


def _import_lambda(monkeypatch, env_value):
    sentinel = object()
    monkeypatch.setattr(prices, "refresh_prices", lambda: sentinel)
    monkeypatch.setenv("ALLOTMINT_ENABLE_TRADING_AGENT", env_value)

    sys.modules.pop("backend.lambda_api.price_refresh", None)
    mod = importlib.import_module("backend.lambda_api.price_refresh")

    agent_state = SimpleNamespace(called=False)

    def fake_run():
        agent_state.called = True

    monkeypatch.setattr(mod, "trading_agent", SimpleNamespace(run=fake_run))

    return mod, agent_state, sentinel


def test_run_called_when_enabled(monkeypatch):
    mod, agent, sentinel = _import_lambda(monkeypatch, "true")
    result = mod.lambda_handler({}, {})
    assert agent.called is True
    assert result is sentinel


def test_run_not_called_when_disabled(monkeypatch):
    mod, agent, sentinel = _import_lambda(monkeypatch, "false")
    result = mod.lambda_handler({}, {})
    assert agent.called is False
    assert result is sentinel


# ---------------------------------------------------------------------------
# lambda_handler exception path
# ---------------------------------------------------------------------------


def _import_lambda_raising(monkeypatch, trading_agent_env="false"):
    def _raise():
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(prices, "refresh_prices", _raise)
    monkeypatch.setenv("ALLOTMINT_ENABLE_TRADING_AGENT", trading_agent_env)

    sys.modules.pop("backend.lambda_api.price_refresh", None)
    return importlib.import_module("backend.lambda_api.price_refresh")


def test_lambda_handler_exception_returns_error_shape(monkeypatch):
    mod = _import_lambda_raising(monkeypatch)
    monkeypatch.setattr(mod, "_seed_empty_snapshot", lambda: None)

    result = mod.lambda_handler({}, {})

    assert result["error"] == "quota exceeded"
    assert result["tickers"] == []
    assert result["snapshot"] == {}
    assert "timestamp" in result


def test_lambda_handler_exception_calls_seed(monkeypatch):
    mod = _import_lambda_raising(monkeypatch)
    seeded = []
    monkeypatch.setattr(mod, "_seed_empty_snapshot", lambda: seeded.append(True))

    mod.lambda_handler({}, {})

    assert seeded, "_seed_empty_snapshot must be called when refresh_prices() raises"


def test_lambda_handler_returns_error_shape_even_if_seed_raises(monkeypatch):
    """lambda_handler must never propagate to CloudFormation even if _seed_empty_snapshot raises."""
    mod = _import_lambda_raising(monkeypatch)

    def _explode():
        raise RuntimeError("S3 unreachable")

    monkeypatch.setattr(mod, "_seed_empty_snapshot", _explode)

    result = mod.lambda_handler({}, {})

    assert result["error"] == "quota exceeded"
    assert result["tickers"] == []
    assert "timestamp" in result


def test_trading_agent_not_called_when_refresh_fails(monkeypatch):
    mod = _import_lambda_raising(monkeypatch, trading_agent_env="true")
    monkeypatch.setattr(mod, "_seed_empty_snapshot", lambda: None)

    agent_called = []
    monkeypatch.setattr(mod, "trading_agent", SimpleNamespace(run=lambda: agent_called.append(True)))

    mod.lambda_handler({}, {})

    assert not agent_called, "trading agent must not run when refresh_prices() raises"


# ---------------------------------------------------------------------------
# _seed_empty_snapshot
# ---------------------------------------------------------------------------


def _get_seed_fn(monkeypatch):
    sys.modules.pop("backend.lambda_api.price_refresh", None)
    monkeypatch.setattr(prices, "refresh_prices", lambda: {})
    mod = importlib.import_module("backend.lambda_api.price_refresh")
    return mod._seed_empty_snapshot, mod


def test_seed_empty_snapshot_skips_non_aws_env(monkeypatch):
    fn, mod = _get_seed_fn(monkeypatch)
    monkeypatch.setattr(mod.config, "app_env", "local")

    called = []
    fake_boto3 = SimpleNamespace(client=lambda svc: SimpleNamespace(put_object=lambda **kw: called.append(kw)))
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    fn()

    assert not called, "_seed_empty_snapshot must not call boto3 when app_env != 'aws'"


def test_seed_empty_snapshot_skips_missing_bucket(monkeypatch):
    fn, mod = _get_seed_fn(monkeypatch)
    monkeypatch.setattr(mod.config, "app_env", "aws")
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    called = []
    fake_boto3 = SimpleNamespace(client=lambda svc: SimpleNamespace(put_object=lambda **kw: called.append(kw)))
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    fn()

    assert not called, "_seed_empty_snapshot must not call boto3 when DATA_BUCKET is unset"


def test_seed_empty_snapshot_puts_object(monkeypatch):
    fn, mod = _get_seed_fn(monkeypatch)
    monkeypatch.setattr(mod.config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    put_calls = []

    class _FakeS3:
        def put_object(self, **kwargs):
            put_calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda svc: _FakeS3()))

    fn()

    assert len(put_calls) == 1
    assert put_calls[0]["Bucket"] == "test-bucket"
    assert put_calls[0]["Key"] == "prices/latest_prices.json"
    assert put_calls[0]["Body"] == b"{}"
    assert put_calls[0]["ContentType"] == "application/json"


def test_seed_empty_snapshot_swallows_boto3_error(monkeypatch):
    fn, mod = _get_seed_fn(monkeypatch)
    monkeypatch.setattr(mod.config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")

    class _BrokenS3:
        def put_object(self, **kwargs):
            raise OSError("connection refused")

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda svc: _BrokenS3()))

    # Must not raise
    fn()
