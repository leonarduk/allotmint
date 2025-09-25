from backend.agent import trading_agent
from backend.config import TradingAgentConfig


def _base_config() -> TradingAgentConfig:
    cfg = TradingAgentConfig()
    cfg.min_sharpe = None
    cfg.max_volatility = None
    return cfg


def test_generate_signals_combines_multiple_indicators(monkeypatch):
    monkeypatch.setattr(
        trading_agent,
        "load_strategy_config",
        lambda: _base_config(),
    )

    snapshot = {
        "AAA": {
            "change_7d_pct": 6.0,
            "rsi": 28.0,
            "ma_short": None,
            "ma_long": None,
            "sma_50": None,
            "sma_200": None,
            "volatility": None,
            "sharpe": None,
        }
    }

    signals = trading_agent.generate_signals(snapshot)

    assert len(signals) == 1
    signal = signals[0]
    assert signal["action"] == "BUY"
    assert "2 indicators" in signal["reason"]
    assert signal["confidence"] is not None
    assert signal["factors"] and len(signal["factors"]) == 2
    # ensure both RSI and price momentum contribute to the rationale
    assert any("RSI" in factor for factor in signal["factors"])
    assert any("price" in factor.lower() for factor in signal["factors"])


def test_generate_signals_requires_multiple_factors(monkeypatch):
    monkeypatch.setattr(
        trading_agent,
        "load_strategy_config",
        lambda: _base_config(),
    )

    snapshot = {
        "BBB": {
            "change_7d_pct": 6.0,
            "rsi": None,
            "ma_short": None,
            "ma_long": None,
            "sma_50": None,
            "sma_200": None,
            "volatility": None,
            "sharpe": None,
        }
    }

    signals = trading_agent.generate_signals(snapshot)

    assert signals == []
