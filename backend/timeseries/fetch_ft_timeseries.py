import logging
import re
import time
from datetime import date, timedelta
from io import StringIO
from typing import Optional

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from backend.utils.currency_utils import currency_from_isin
from backend.utils.timeseries_helpers import _is_isin, STANDARD_COLUMNS

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("ft_timeseries")

FT_URL_TEMPLATE = "https://markets.ft.com/data/funds/tearsheet/historical?s={ticker}"

def init_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)

def _build_ft_ticker(ticker: str) -> Optional[str]:
    """Return an FT-compatible symbol like 'IE00B4L5Y983:GBP', or None."""
    if _is_isin(ticker):
        isin = re.split(r"[.:]", ticker)[0].upper()
        return f"{isin}:{currency_from_isin(ticker)}"
    return None

def fetch_ft_timeseries_range(ticker: str, start_date: date, end_date: Optional[date] = None) -> pd.DataFrame:
    url = FT_URL_TEMPLATE.format(ticker=ticker)
    logger.info(f"🔗 Navigating to {url}")
    driver = init_driver(headless=True)
    try:
        driver.get(url)
        logger.debug("⏳ Waiting for historical price table...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.mod-ui-table"))
        )

        try:
            consent_btn = driver.find_element(By.CSS_SELECTOR, "button.js-accept-all-cookies")
            consent_btn.click()
            logger.info("🍪 Dismissed cookie banner.")
            time.sleep(1)
        except Exception:
            logger.info("ℹ️ No cookie banner found or already dismissed.")

        table_elem = driver.find_element(By.CSS_SELECTOR, "table.mod-ui-table")
        html = table_elem.get_attribute("outerHTML")
        df = pd.read_html(StringIO(html))[0]
        df.columns = [col.strip() for col in df.columns]

        # Parse dates from spans manually
        soup = BeautifulSoup(html, "html.parser")
        cleaned_dates = []
        for row in soup.select("table.mod-ui-table tbody tr"):
            spans = row.select("td span")
            cleaned_dates.append(spans[0].text.strip() if spans else row.select_one("td").text.strip())
        df["Date"] = pd.to_datetime(cleaned_dates, format="%A, %B %d, %Y")

        df = df[df["Date"].notna()]
        df = df.sort_values("Date")
        df["Ticker"] = ticker
        df["Source"] = "FT"

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"] if "Volume" in df.columns else ["Date", "Close", "Ticker", "Source"]]

    finally:
        logger.debug("🩹 Closing Selenium driver")
        driver.quit()

def fetch_ft_timeseries(ticker: str, days: int = 365) -> pd.DataFrame:
    today = date.today()
    start = today - timedelta(days=days)
    if _is_isin(ticker=ticker):
        ft_ticker = _build_ft_ticker(ticker)
        return fetch_ft_timeseries_range(ft_ticker, start, today)

    return pd.DataFrame(columns=STANDARD_COLUMNS)


if __name__ == "__main__":
    df = fetch_ft_timeseries("1", days=365)
    print(df.head())
