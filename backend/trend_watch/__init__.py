"""Holding trend watch (#10476): a weekly review list of held positions whose trend has turned.

See :mod:`backend.trend_watch.service` for the run, :mod:`.detect` for the
change-of-direction rule, :mod:`.data_gate` for the data check, :mod:`.agent`
for the read-only investigation and :mod:`.backtest` for the detector's track
record. It is a review list, not trade instructions, and it never trades.
"""
