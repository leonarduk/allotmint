import pandas as pd


def rsi(series: pd.Series, window: int) -> pd.Series:
    """Return the Relative Strength Index for ``series``."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average for ``series`` over ``window`` periods."""
    return series.rolling(window=window).mean()
