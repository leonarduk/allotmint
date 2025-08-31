import pytest
import shutil
from backend.common import portfolio_utils
from backend.agent.trading_agent import send_trade_alert, run
from backend.agent import trading_agent

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
    portfolio = {
        "accounts": [
            {"holdings": [{"ticker": "AAA", "units": 1, "cost_gbp": 100}]}
        ]
    }
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot)
    monkeypatch.setattr(portfolio_utils, "list_portfolios", lambda: [portfolio])

    published = []

    def fake_publish(alert):
        published.append(alert)

    monkeypatch.setattr("backend.common.alerts.publish_alert", fake_publish)

    alerts = generate_signals(threshold_pct=0.05)
    assert alerts == published
    assert published and published[0]["ticker"] == "AAA.L"


def test_send_trade_alert_sns_only(monkeypatch):
    calls = {"publish": None, "telegram": False}

    def fake_publish(alert):
        calls["publish"] = alert

    def fake_send(msg):
        calls["telegram"] = True

    monkeypatch.setattr("backend.agent.trading_agent.publish_alert", fake_publish)
    monkeypatch.setattr("backend.agent.trading_agent.send_message", fake_send)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    send_trade_alert("hello")

    assert calls["publish"] == {"message": "hello"}
    assert calls["telegram"] is False


def test_send_trade_alert_with_telegram(monkeypatch):
    published = {}
    telegram_msgs = []

    monkeypatch.setattr(
        "backend.agent.trading_agent.publish_alert", lambda alert: published.update(alert)
    )
    monkeypatch.setattr(
        "backend.agent.trading_agent.send_message", lambda msg: telegram_msgs.append(msg)
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")

    send_trade_alert("hi")

    assert published["message"] == "hi"
    assert telegram_msgs == ["hi"]


def test_send_trade_alert_no_publish_with_telegram(monkeypatch):
    published = {"called": False}
    telegram_msgs: list[str] = []

    def fake_publish(alert):
        published["called"] = True

    monkeypatch.setattr(
        "backend.agent.trading_agent.publish_alert", fake_publish
    )
    monkeypatch.setattr(
        "backend.agent.trading_agent.send_message", lambda msg: telegram_msgs.append(msg)
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")

    send_trade_alert("hi", publish=False)

    assert published["called"] is False
    assert telegram_msgs == ["hi"]


def test_run_defaults_to_all_known_tickers(monkeypatch):
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
    monkeypatch.setattr(
        "backend.agent.trading_agent.publish_alert", lambda alert: None
    )

    run()

    assert captured["tickers"] == ["AAA", "BBB"]


def test_run_sends_telegram_when_not_aws(monkeypatch):
    # Trigger a BUY signal for ticker AAA
    monkeypatch.setattr(
        "backend.agent.trading_agent.list_all_unique_tickers", lambda: ["AAA"]
    )

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["AAA"] * 7, "close": [1, 1, 1, 1, 1, 1, 2]}
        return pd.DataFrame(data)

    monkeypatch.setattr(
        "backend.agent.trading_agent.prices.load_prices_for_tickers", fake_load_prices
    )
    monkeypatch.setattr(
        "backend.agent.trading_agent.publish_alert", lambda alert: None
    )

    sent: list[str] = []
    monkeypatch.setattr(
        "backend.agent.trading_agent.send_message", lambda msg: sent.append(msg)
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    from backend.agent import trading_agent

    monkeypatch.setattr(trading_agent.config, "app_env", "local")

    run()

    assert sent and "AAA" in sent[0]


def test_log_trade_recreates_directory(tmp_path, monkeypatch):
    trade_path = tmp_path / "trades" / "trade_log.csv"
    trade_path.parent.mkdir(parents=True)
    shutil.rmtree(trade_path.parent)
    monkeypatch.setattr(trading_agent, "TRADE_LOG_PATH", trade_path)

    assert not trade_path.parent.exists()

    trading_agent._log_trade("AAA", "BUY", 1.0)

    assert trade_path.exists()


def test_run_uses_rsi_and_fundamentals(monkeypatch):
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["AAA", "BBB"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {
            "Ticker": ["AAA"] * 15 + ["BBB"] * 5,
            "close": [15, 14, 13, 12, 11, 10, 9, 8, 5, 5, 5, 5, 5, 5, 5]
            + [10, 11, 12, 13, 14],
        }
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)

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


def test_run_generates_ma_signal(monkeypatch):
    monkeypatch.setattr(trading_agent, "list_all_unique_tickers", lambda: ["BBB"])

    def fake_load_prices(tickers, days=60):
        import pandas as pd

        data = {"Ticker": ["BBB"] * 5, "close": [10, 11, 12, 13, 14]}
        return pd.DataFrame(data)

    monkeypatch.setattr(trading_agent.prices, "load_prices_for_tickers", fake_load_prices)
    monkeypatch.setattr(trading_agent, "publish_alert", lambda alert: None)
    monkeypatch.setattr(trading_agent, "send_message", lambda msg: None)
    monkeypatch.setattr(trading_agent, "_log_trade", lambda *a, **k: None)

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


