    if risk is None:
        return []
    # Guard: only attempt VaR computation when the owner portfolio is available.
    # This prevents repeated expensive I/O retries after a known portfolio-load
    # failure and aligns with the caching contract in ReportContext.
    portfolio = context.owner_portfolio()
    if not portfolio:
        return []
    rows: List[Dict[str, Any]] = []
    for confidence, metric in ((0.95, "VaR (95%)"), (0.99, "VaR (99%)")):
        try:
            payload = risk.compute_portfolio_var(
                context.owner, confidence=confidence, include_cash=False
            )
        except (FileNotFoundError, ValueError):
            continue
        rows.append(
            {
                "metric": metric,
                "value": _round_if_number(_extract_var_value(payload), 6),
                "units": "GBP",
            }
        )
    if not rows:
        return []
    try:
        sharpe_ratio = risk.compute_sharpe_ratio(context.owner)
    except (FileNotFoundError, ValueError):
        sharpe_ratio = None
    if sharpe_ratio is not None:
        rows.append(
            {
                "metric": "Sharpe ratio",
                "value": _round_if_number(sharpe_ratio, 6),
                "units": "ratio",
            }
        )
    return rows
