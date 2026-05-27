import datetime
import html

import pandas as pd
from fastapi.responses import HTMLResponse
from pandas import DataFrame


def render_meta_timeseries_html(
    df: DataFrame,
    ticker: str,
    exchange: str,
    resolved_start: datetime.date,
    resolved_end: datetime.date,
    scaling: float,
) -> HTMLResponse:
    """Render the GET /timeseries/meta HTML response.

    Accepts raw (unescaped) *ticker* and *exchange* values from
    ``_resolve_ticker_exchange`` and applies ``html.escape()`` internally
    so callers never embed unsanitised user input into the template.
    DataFrame cell values are escaped by pandas via ``escape=True``.
    """
    escaped_ticker = html.escape(ticker)
    escaped_exchange = html.escape(exchange)
    html_table = df.to_html(index=False, escape=True)
    return HTMLResponse(
        content=f"""
    <html>
        <head><title>{escaped_ticker}.{escaped_exchange} Price History</title></head>
        <body>
            <h1>{escaped_ticker}.{escaped_exchange} - {resolved_start} to {resolved_end}</h1>
            <p><strong>Scaling:</strong> {scaling}x</p>
            {html_table}
        </body>
    </html>
    """
    )


def render_timeseries_html(df: DataFrame, title: str, subtitle: str = "") -> HTMLResponse:
    df = df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]].copy()

    df["Volume"] = df["Volume"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].map("{:.2f}".format)

    html_table = df.to_html(index=False, classes="table table-striped text-center", border=0)

    escaped_title = html.escape(title)
    escaped_subtitle = html.escape(subtitle)

    return HTMLResponse(
        content=f"""
    <html>
    <head>
        <title>{escaped_title}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ padding: 2rem; }}
            table {{ font-size: 0.9rem; }}
            th, td {{ vertical-align: middle; }}
            h2 small {{ font-size: 1rem; color: #666; }}
        </style>
    </head>
    <body>
        <h2>{escaped_title}<br><small>{escaped_subtitle}</small></h2>
        {html_table}
    </body>
    </html>
    """
    )
