import pandas as pd
from pandas import DataFrame
from fastapi.responses import HTMLResponse

def render_timeseries_html(df: DataFrame, title: str, subtitle: str = "") -> HTMLResponse:
    df = df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]].copy()

    df["Volume"] = df["Volume"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].map("{:.2f}".format)

    html_table = df.to_html(index=False, classes="table table-striped text-center", border=0)

    return HTMLResponse(content=f"""
    <html>
    <head>
        <title>{title}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ padding: 2rem; }}
            table {{ font-size: 0.9rem; }}
            th, td {{ vertical-align: middle; }}
            h2 small {{ font-size: 1rem; color: #666; }}
        </style>
    </head>
    <body>
        <h2>{title}<br><small>{subtitle}</small></h2>
        {html_table}
    </body>
    </html>
    """)
