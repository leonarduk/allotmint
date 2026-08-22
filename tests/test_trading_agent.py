import json
import shutil

import pytest

from backend.agent import trading_agent
from backend.agent.trading_agent import generate_signals as ta_generate_signals
from backend.agent.trading_agent import run, send_trade_alert
from backend.common import portfolio_utils
from backend.common.core_optional import CoreFeatureUnavailableError

# Alias to match the terminology of "generate_signals"
generate_signals = portfolio_utils.check_price_alerts


def test_generate_signals_buy_sell_actions(monkeypatch):
    snapshot = {
        "AAA.L": {"last_price": 110.0},
        "BBB.L": {"last_price": 90.0},
    }
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "AAA", "units": 1, "cost_gbp": 100},
                    {"ticker": "BBB", "units": 1, "cost_gbp": 100},
                ]
            }
        ]
    }

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot)
    monkeypatch.setattr(portfolio_utils, "list_portfolios", lambda: [portfolio])
    monkeypatch.setattr("backend.common.alerts.publish_alert", lambda alert: None)

    alerts = generate_signals(threshold_pct=0.05)
    assert len(alerts) == 2
    actions = {a["ticker"]: ("sell" if a["change_pct"] > 0 else "buy") for a in alerts}
    assert actions == {"AAA.L": "sell", "BBB.L": "buy"}


def test_generate_signals_emits_alerts(monkeypatch):
    snapshot = {"AAA.L": {"last_price": 110.0}}
    portfolio = {"accounts": [{"holdings": [{"ticker": "AAA", "units": 1, "cost_gbp": 100}]}]}
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot)
    monkeypatch.setattr(portfolio_utils, "list_portfolios", lambda: [portfolio])

    published = []

    def fake_publish(alert):
        published.append(alert)

    monkeypatch.setattr("backend.common.alerts.publish_alert", fake_publish)

    alerts = generate_signals(threshold_pct=0.05)
    assert alerts == published
    assert published and published[0]["ticker"] == "AAA.L"


def test_agent_generate_signals_indicators():
    snapshot = {
        "AAA": {"rsi": 25},
        "BBB": {"rsi": 75},
        "CCC": {"sma_50": 120, "sma_200": 100},
        "DDD": {"sma_50": 80, "sma_200": 100},
    }
    signals = ta_generate_signals(snapshot)
    actions = {s["ticker"]: s["action"] for s in signals}
    assert actions == {"AAA": "BUY", "BBB": "SELL", "CCC": "BUY", "DDD": "SELL"}


def test_agent_generate_signals_risk_filters(monkeypatch):
    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "min_sharpe", 1.0)
    monkeypatch.setattr(cfg, "max_volatility", 0.1)
    snapshot = {"AAA": {"rsi": 20, "sharpe": 0.5, "volatility": 0.2}}
    signals = ta_generate_signals(snapshot)
    assert signals == []


def test_load_strategy_config_ignores_unknown_keys(tmp_path, monkeypatch):
    prefs = {"rsi_buy": 25, "unknown": 1}
    prefs_path = tmp_path / "strategy_prefs.json"
    prefs_path.write_text(json.dumps(prefs))
    monkeypatch.setattr(trading_agent.config, "repo_root", tmp_path)
    cfg = trading_agent.load_strategy_config()
    assert cfg.rsi_buy == 25
    assert cfg.rsi_sell == 70.0


def test_send_trade_alert_sns_only(monkeypatch):
    calls = {"publish": None, "telegram": False}

    def fake_publish(alert):
        calls["publish"] = alert

    def fake_send(msg):
        calls["telegram"] = True

    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", fake_publish)
    monkeypatch.setattr("backend.agent.trading_agent.send_message", fake_send)
    monkeypatch.setattr(trading_agent.config, "telegram_bot_token", None)
    monkeypatch.setattr(trading_agent.config, "telegram_chat_id", None)

    send_trade_alert("hello")

    assert calls["publish"] == {"message": "hello"}
    assert calls["telegram"] is False


def test_send_trade_alert_with_telegram(monkeypatch):
    published = {}
    telegram_msgs = []

    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", lambda alert: published.update(alert))
    monkeypatch.setattr("backend.agent.trading_agent.send_message", lambda msg: telegram_msgs.append(msg))
    monkeypatch.setattr(trading_agent.config, "telegram_bot_token", "T")
    monkeypatch.setattr(trading_agent.config, "telegram_chat_id", "C")

    send_trade_alert("hi")

    assert published["message"] == "hi"
    assert telegram_msgs == ["hi"]


def test_send_trade_alert_no_publish_with_telegram(monkeypatch):
    published = {"called": False}
    telegram_msgs: list[str] = []

    def fake_publish(alert):
        published["called"] = True

    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", fake_publish)
    monkeypatch.setattr("backend.agent.trading_agent.send_message", lambda msg: telegram_msgs.append(msg))
    monkeypatch.setattr(trading_agent.config, "telegram_bot_token", "T")
    monkeypatch.setattr(trading_agent.config, "telegram_chat_id", "C")

    send_trade_alert("hi", publish=False)

    assert published["called"] is False
    assert telegram_msgs == ["hi"]


def test_run_defaults_to_all_known_tickers(monkeypatch):
    pytest.importorskip("allotmint_pro")
    captured: dict = {}

    # ensure the agent discovers our tickers when none are supplied
    monkeypatch.setattr(
        "backend.agent.trading_agent.list_all_unique_tickers",
        lambda: ["AAA", "BBB"],
    )

    def fake_load_prices(tickers, days=60):
        captured["tickers"] = list(tickers)
        import pandas as pd

        data = {
            "Ticker": ["AAA"] * 7 + ["BBB"] * 7,
            "close": [1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2],
        }
        return pd.DataFrame(data)

    monkeypatch.setattr(
        "backend.agent.trading_agent.prices.load_prices_for_tickers",
        fake_load_prices,
    )
    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", lambda alert: None)
    monkeypatch.setattr("backend.agent.trading_agent.list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(
        "backend.agent.trading_agent.compliance.check_trade",
        lambda trade: {"owner": trade.get("owner"), "warnings": []},
    )

    run()

    assert captured["tickers"] == ["AAA", "BBB"]


def test_run_sends_telegram_when_not_aws(monkeypatch):
    pytest.importorskip("allotmint_pro")
    # Trigger a BUY signal for ticker AAA
    monkeypatch.setattr("backend.agent.trading_agent.list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr("backend.agent.trading_agent.prices.load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", lambda alert: None)
    monkeypatch.setattr("backend.agent.trading_agent.list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(
        "backend.agent.trading_agent.compliance.check_trade",
        lambda trade: {"owner": trade.get("owner"), "warnings": []},
    )

    sent: list[str] = []
    monkeypatch.setattr("backend.agent.trading_agent.send_message", lambda msg: sent.append(msg))
    monkeypatch.setattr(trading_agent.config, "telegram_bot_token", "T")
    monkeypatch.setattr(trading_agent.config, "telegram_chat_id", "C")
    monkeypatch.setattr(trading_agent.config, "app_env", "local")

    run()

    assert sent and "AAA" in sent[0]


def test_run_compliance_gates_actions(monkeypatch):
    pytest.importorskip("allotmint_pro")
    monkeypatch.setattr("backend.agent.trading_agent.list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr("backend.agent.trading_agent.prices.load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr("backend.agent.trading_agent.list_portfolios", lambda: [{"owner": "alice"}])

    def fake_check(trade):
        return {"owner": trade["owner"], "warnings": ["blocked"]}

    monkeypatch.setattr("backend.agent.trading_agent.compliance.check_trade", fake_check)

    published: list = []
    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", lambda alert: published.append(alert))

    signals = run()

    assert signals == []
    assert published == []


def test_run_skips_signal_when_compliance_blocks(monkeypatch):
    pytest.importorskip("allotmint_pro")
    monkeypatch.setattr("backend.agent.trading_agent.list_all_unique_tickers", lambda: ["AAA", "BBB"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {
            "Ticker": ["AAA"] * 7 + ["BBB"] * 7,
            "close": [1, 1, 1, 1, 1, 1, 2] + [1, 1, 1, 1, 1, 1, 2],
        }
        return pd.DataFrame(data)

    monkeypatch.setattr("backend.agent.trading_agent.prices.load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr("backend.agent.trading_agent.list_portfolios", lambda: [{"owner": "alice"}])

    calls: list[str] = []

    def fake_check(trade):
        owner = trade["owner"]
        calls.append(owner)
        if len(calls) == 1:
            return {"owner": owner, "warnings": []}
        return {"owner": owner, "warnings": ["limit"]}

    monkeypatch.setattr("backend.agent.trading_agent.compliance.check_trade", fake_check)

    published: list = []
    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", lambda alert: published.append(alert))
    monkeypatch.setattr("backend.agent.trading_agent.send_message", lambda msg: None)
    monkeypatch.setattr("backend.agent.trading_agent._log_trade", lambda *a, **k: None)

    signals = run()

    assert len(signals) == 1
    assert signals[0]["ticker"] == "AAA"
    # compliance checked for each signal
    assert len(calls) == 2
    # second signal blocked, so only one alert published
    assert len(published) == 1


def test_log_trade_recreates_directory(tmp_path, monkeypatch):
    trade_path = tmp_path / "trades" / "trade_log.csv"
    trade_path.parent.mkdir(parents=True)
    shutil.rmtree(trade_path.parent)
    monkeypatch.setattr(trading_agent, "TRADE_LOG_PATH", trade_path)

    assert not trade_path.parent.exists()

    trading_agent._log_trade("AAA", "BUY", 1.0)

    assert trade_path.exists()


def test_run_uses_rsi_and_fundamentals(monkeypatch):
    pytest.importorskip("allotmint_pro")
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA", "BBB"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {
            "Ticker": ["AAA"] * 15 + ["BBB"] * 5,
            "close": [15, 14, 13, 12, 11, 10, 9, 8, 5, 5, 5, 5, 5, 5, 5] + [10, 11, 12, 13, 14],
        }
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(trading_agent.compliance, "check_trade", lambda trade: {"warnings": []})
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(trading_agent.compliance, "check_trade", lambda trade: {"warnings": []})

    class F:
        def __init__(self, ticker: str):
            self.ticker = ticker

    monkeypatch.setattr(trading_agent, "screen", lambda tickers, **kw: [F("AAA")])

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "rsi_buy", 50.0)
    monkeypatch.setattr(cfg, "pe_max", 20.0)
    monkeypatch.setattr(cfg, "ma_short_window", 3)
    monkeypatch.setattr(cfg, "ma_long_window", 5)

    signals = run()
    assert len(signals) == 1
    assert signals[0]["ticker"] == "AAA"
    assert "RSI" in signals[0]["reason"]


def test_run_does_not_filter_sell_signal(monkeypatch):
    pytest.importorskip("allotmint_pro")
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [10, 10, 10, 10, 10, 10, 4]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(trading_agent.compliance, "check_trade", lambda trade: {"warnings": []})

    def fake_screen(tickers, **kw):
        raise AssertionError("screen should not be called for SELL signals")

    monkeypatch.setattr(trading_agent, "screen", fake_screen)

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "pe_max", 20.0)

    signals = run()
    assert signals and signals[0]["action"] == "SELL"


def test_run_generates_ma_signal(monkeypatch):
    pytest.importorskip("allotmint_pro")
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["BBB"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["BBB"] * 5, "close": [10, 11, 12, 13, 14]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(trading_agent.compliance, "check_trade", lambda trade: {"warnings": []})
    monkeypatch.setattr(
        trading_agent,
        "compute_owner_performance",
        lambda owner, **kwargs: {"max_drawdown": None},
    )

    class F:
        def __init__(self, ticker: str):
            self.ticker = ticker

    monkeypatch.setattr(trading_agent, "screen", lambda tickers, **kw: [F("BBB")])

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "rsi_buy", 0.0)
    monkeypatch.setattr(cfg, "rsi_sell", 100.0)
    monkeypatch.setattr(cfg, "pe_max", 20.0)
    monkeypatch.setattr(cfg, "ma_short_window", 3)
    monkeypatch.setattr(cfg, "ma_long_window", 5)

    signals = run()
    assert signals and signals[0]["ticker"] == "BBB"
    assert "MA" in signals[0]["reason"]


def test_run_applies_risk_filters(monkeypatch):
    pytest.importorskip("allotmint_pro")
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 10, "close": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent.compliance, "check_trade", lambda trade: {"warnings": []})
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "min_sharpe", 1.0)
    monkeypatch.setattr(cfg, "max_volatility", 0.1)

    signals = trading_agent.run()
    assert signals == []


def test_run_pro_absent_tags_checks_skipped_and_warns_once(monkeypatch, caplog):
    """When allotmint-pro is absent, run() should still return signals but
    tag them with `checks_skipped`, and the "unavailable" warnings should be
    logged once per run, not once per signal/owner pair."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA", "BBB"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {
            "Ticker": ["AAA"] * 7 + ["BBB"] * 7,
            "close": [1, 1, 1, 1, 1, 1, 2] + [1, 1, 1, 1, 1, 1, 2],
        }
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    # Two owners so the old per-owner-loop warning placement would have
    # logged the compliance warning twice for a single BUY signal.
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}, {"owner": "bob"}])
    monkeypatch.setattr(trading_agent, "compliance", None)
    monkeypatch.setattr(trading_agent, "screen", None)

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "pe_max", 20.0)
    monkeypatch.setattr(cfg, "require_pro_checks", False)

    with caplog.at_level("WARNING"):
        signals = trading_agent.run()

    assert signals, "expected at least one signal to be returned"
    for sig in signals:
        assert "compliance" in sig["checks_skipped"]

    compliance_warnings = [r for r in caplog.records if "Compliance check skipped" in r.message]
    screening_warnings = [r for r in caplog.records if "Fundamental screening skipped" in r.message]
    assert len(compliance_warnings) == 1
    assert len(screening_warnings) == 1


def test_run_require_pro_checks_raises_when_pro_absent(monkeypatch):
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(trading_agent, "compliance", None)
    monkeypatch.setattr(trading_agent, "screen", None)

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "require_pro_checks", True)

    with pytest.raises(CoreFeatureUnavailableError) as exc_info:
        trading_agent.run()

    message = str(exc_info.value)
    assert "fundamental_screen" in message
    assert "compliance" in message


def test_run_require_pro_checks_raises_with_partial_degradation(monkeypatch):
    """Only one pro check missing (screen) should still raise and name just
    that check, not the one that is actually available."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    class FakeCompliance:
        @staticmethod
        def check_trade(trade):
            return {"owner": trade.get("owner"), "warnings": []}

    monkeypatch.setattr(trading_agent, "compliance", FakeCompliance)
    monkeypatch.setattr(trading_agent, "screen", None)

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "require_pro_checks", True)

    with pytest.raises(CoreFeatureUnavailableError) as exc_info:
        trading_agent.run()

    message = str(exc_info.value)
    assert "fundamental_screen" in message
    assert "compliance" not in message


def test_run_pro_present_checks_skipped_empty(monkeypatch):
    """When allotmint-pro's compliance/screen modules are available, signals
    should carry an empty `checks_skipped` list and existing blocking
    behaviour must be unchanged."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    class FakeCompliance:
        @staticmethod
        def check_trade(trade):
            return {"owner": trade.get("owner"), "warnings": []}

    class F:
        def __init__(self, ticker: str):
            self.ticker = ticker

    monkeypatch.setattr(trading_agent, "compliance", FakeCompliance)
    monkeypatch.setattr(trading_agent, "screen", lambda tickers, **kw: [F("AAA")])

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "pe_max", 20.0)
    monkeypatch.setattr(cfg, "require_pro_checks", False)

    signals = trading_agent.run()

    assert signals
    for sig in signals:
        assert sig["checks_skipped"] == []


def test_run_pro_absent_partial_degradation_only_compliance(monkeypatch):
    """Only compliance is missing (screen is available): signals should be
    tagged with `compliance` only, and fundamental screening should still
    run normally."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])
    monkeypatch.setattr(trading_agent, "compliance", None)

    class F:
        def __init__(self, ticker: str):
            self.ticker = ticker

    monkeypatch.setattr(trading_agent, "screen", lambda tickers, **kw: [F("AAA")])

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "pe_max", 20.0)
    monkeypatch.setattr(cfg, "require_pro_checks", False)

    signals = trading_agent.run()

    assert signals
    for sig in signals:
        assert sig["checks_skipped"] == ["compliance"]


def test_run_pro_absent_partial_degradation_only_screen(monkeypatch):
    """Only fundamental screening is missing (compliance is available):
    signals should be tagged with `fundamental_screen` only."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    class FakeCompliance:
        @staticmethod
        def check_trade(trade):
            return {"owner": trade.get("owner"), "warnings": []}

    monkeypatch.setattr(trading_agent, "compliance", FakeCompliance)
    monkeypatch.setattr(trading_agent, "screen", None)

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "pe_max", 20.0)
    monkeypatch.setattr(cfg, "require_pro_checks", False)

    signals = trading_agent.run()

    assert signals
    for sig in signals:
        assert sig["checks_skipped"] == ["fundamental_screen"]


def test_run_pro_absent_does_not_tag_fundamental_screen_when_pe_max_none(monkeypatch):
    """`fundamental_screen` must NOT be tagged as skipped for a BUY signal
    when no `pe_max`/`de_max` is configured (fundamental_params is empty) --
    no screen would have run even with allotmint-pro installed, so tagging it
    as "skipped" would be a false positive (misleading "checks skipped"
    badge/notification suffix)."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    class FakeCompliance:
        @staticmethod
        def check_trade(trade):
            return {"owner": trade.get("owner"), "warnings": []}

    monkeypatch.setattr(trading_agent, "compliance", FakeCompliance)
    monkeypatch.setattr(trading_agent, "screen", None)

    cfg = trading_agent.config.trading_agent
    # No pe_max/de_max configured, so fundamental_params is empty and the
    # `if fundamental_params and signals:` filtering block is skipped
    # entirely -- but the BUY signal should still be tagged.
    monkeypatch.setattr(cfg, "pe_max", None)
    monkeypatch.setattr(cfg, "de_max", None)
    monkeypatch.setattr(cfg, "require_pro_checks", False)

    signals = trading_agent.run()

    assert signals
    for sig in signals:
        assert sig["action"] == "BUY"
        assert "fundamental_screen" not in sig["checks_skipped"]


def test_run_pro_absent_no_screening_warning_when_no_fundamental_params(monkeypatch, caplog):
    """The "screening unavailable" warning should not fire when no
    fundamental threshold (`pe_max`/`de_max`) is configured -- fundamental
    screening was never going to apply, so warning about it is misleading
    noise (#6798 Codex follow-up)."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    class FakeCompliance:
        @staticmethod
        def check_trade(trade):
            return {"owner": trade.get("owner"), "warnings": []}

    monkeypatch.setattr(trading_agent, "compliance", FakeCompliance)
    monkeypatch.setattr(trading_agent, "screen", None)

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "pe_max", None)
    monkeypatch.setattr(cfg, "de_max", None)
    monkeypatch.setattr(cfg, "require_pro_checks", False)

    with caplog.at_level("WARNING"):
        signals = trading_agent.run()

    assert signals and signals[0]["action"] == "BUY"
    screening_warnings = [r for r in caplog.records if "Fundamental screening skipped" in r.message]
    assert screening_warnings == []


def test_run_pro_absent_no_screening_warning_when_only_sell_signals(monkeypatch, caplog):
    """The "screening unavailable" warning should not fire when fundamental
    thresholds are configured but the only generated signals are SELL --
    fundamental screening only ever applies to BUY signals."""
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        # Price falling from 2 to 1 over the last 7 days -> SELL momentum signal.
        data = {"Ticker": ["AAA"] * 7, "close": [2, 2, 2, 2, 2, 2, 1]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    class FakeCompliance:
        @staticmethod
        def check_trade(trade):
            return {"owner": trade.get("owner"), "warnings": []}

    monkeypatch.setattr(trading_agent, "compliance", FakeCompliance)
    monkeypatch.setattr(trading_agent, "screen", None)

    cfg = trading_agent.config.trading_agent
    monkeypatch.setattr(cfg, "pe_max", 20.0)
    monkeypatch.setattr(cfg, "require_pro_checks", False)

    with caplog.at_level("WARNING"):
        signals = trading_agent.run()

    assert signals and signals[0]["action"] == "SELL"
    screening_warnings = [r for r in caplog.records if "Fundamental screening skipped" in r.message]
    assert screening_warnings == []


def test_alert_on_drawdown_handles_value_error(monkeypatch):
    """Ensure ValueError in performance computation doesn't leak."""
    monkeypatch.setattr(trading_agent, "list_portfolios", lambda: [{"owner": "alice"}])

    def fake_perf(owner: str, **kwargs):
        raise ValueError("cache gap")

    monkeypatch.setattr(trading_agent, "compute_owner_performance", fake_perf)
    alerts: list[str] = []
    monkeypatch.setattr(trading_agent, "send_trade_alert", lambda msg: alerts.append(msg))

    trading_agent._alert_on_drawdown()

    assert alerts == []
