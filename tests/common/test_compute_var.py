import pandas as pd
import numpy as np
import pytest

from backend.common import portfolio_utils as pu


def test_compute_var_valid_series():
    df = pd.DataFrame({"Close": [100, 102, 101, 105]})
    expected = -np.quantile(df["Close"].pct_change().dropna(), 0.05) * df["Close"].iloc[-1]
    result = pu.compute_var(df)
    assert result == pytest.approx(expected)


def test_compute_var_insufficient_data_returns_none():
    df = pd.DataFrame({"Close": [100]})
    assert pu.compute_var(df) is None


def test_compute_var_empty_dataframe_returns_none():
    df = pd.DataFrame()
    assert pu.compute_var(df) is None

