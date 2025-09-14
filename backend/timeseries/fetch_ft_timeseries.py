import argparse
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

from backend.config import config
from backend.utils.currency_utils import currency_from_isin
from backend.utils.timeseries_helpers import STANDARD_COLUMNS, _is_isin

logger = logging.getLogger("ft_timeseries")


def init_driver(headless: Optional[bool] = None, user_agent: Optional[str] = None) -> webdriver.Chrome:
    """Initialise a Selenium Chrome driver using shared configuration.

    Parameters may override values from the configuration. If *headless* or
    *user_agent* are ``None`` the corresponding values are looked up in
    ``config.yaml`` (with environment overrides).
    """
    cfg = config
    if headless is None:
        headless = cfg.selenium_headless if cfg.selenium_headless is not None else True
    if user_agent is None:
        user_agent = cfg.selenium_user_agent

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    if user_agent:
        options.add_argument(f"user-agent={user_agent}")
    return webdriver.Chrome(options=options)


def _build_ft_ticker(ticker: str) -> Optional[str]:
    """Return an FT-compatible symbol like 'IE00B4L5Y983:GBP', or None."""
    if _is_isin(ticker):
        isin = re.split(r"[.:]", ticker)[0].upper()
        return f"{isin}:{currency_from_isin(ticker)}"
    return None


def fetch_ft_timeseries_range(
    ticker: str,
    start_date: date,
    end_date: Optional[date] = None,
    *,
    url_template: Optional[str] = None,
    headless: Optional[bool] = None,
    user_agent: Optional[str] = None,
) -> pd.DataFrame:
    cfg = config
    template = (
        url_template
        or cfg.ft_url_template
        or "https://markets.ft.com/data/funds/tearsheet/historical?s={ticker}"
    )
    url = template.format(ticker=ticker)
    logger.info(f"Navigating to {url}")
    driver = init_driver(headless=headless, user_agent=user_agent)

    try:
        driver.get(url)
        logger.debug("Waiting for historical price table...")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.mod-ui-table")))

        # Handle cookie banner
        try:
            consent_btn = driver.find_element(By.CSS_SELECTOR, "button.js-accept-all-cookies")
            consent_btn.click()
            logger.info("Dismissed cookie banner.")
            time.sleep(1)
        except Exception:
            logger.info("No cookie banner found or already dismissed.")

        table_elem = driver.find_element(By.CSS_SELECTOR, "table.mod-ui-table")
        html = table_elem.get_attribute("outerHTML")
        df = pd.read_html(StringIO(html))[0]
        df.columns = [col.strip() for col in df.columns]

        # Extract and clean Date column manually
        soup = BeautifulSoup(html, "html.parser")
        cleaned_dates = []
        for row in soup.select("table.mod-ui-table tbody tr"):
            spans = row.select("td span")
            cleaned_dates.append(spans[0].text.strip() if spans else row.select_one("td").text.strip())
        df["Date"] = pd.to_datetime(cleaned_dates, format="%A, %B %d, %Y", errors="coerce")

        df = df[df["Date"].notna()]
        df = df.sort_values("Date")
        df["Ticker"] = ticker
        df["Source"] = "FT"

        # Normalise to STANDARD_COLUMNS
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = None

        return df[STANDARD_COLUMNS]

    except Exception as e:
        logger.warning("FT fetch failed for %s: %s", ticker, e)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    finally:
        logger.debug("Closing Selenium driver")
        driver.quit()


def fetch_ft_timeseries(
    ticker: str,
    days: int = 365,
    *,
    url_template: Optional[str] = None,
    headless: Optional[bool] = None,
    user_agent: Optional[str] = None,
) -> pd.DataFrame:
    today = date.today()
    start = today - timedelta(days=days)
    if _is_isin(ticker=ticker):
        ft_ticker = _build_ft_ticker(ticker)
        return fetch_ft_timeseries_range(
            ft_ticker,
            start,
            today,
            url_template=url_template,
            headless=headless,
            user_agent=user_agent,
        )

    return pd.DataFrame(columns=STANDARD_COLUMNS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description="Fetch FT timeseries data")
    parser.add_argument("ticker", help="Ticker or ISIN to fetch")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--ft-url-template")
    parser.add_argument("--selenium-user-agent")
    parser.add_argument("--selenium-headless", dest="selenium_headless", action="store_true")
    parser.add_argument(
        "--selenium-non-headless",
        dest="selenium_headless",
        action="store_false",
        help="Run Selenium with a visible browser",
    )
    parser.set_defaults(selenium_headless=None)
    args = parser.parse_args()

    cfg = config
    df = fetch_ft_timeseries(
        args.ticker,
        days=args.days,
        url_template=args.ft_url_template or cfg.ft_url_template,
        headless=(
            args.selenium_headless
            if args.selenium_headless is not None
            else (cfg.selenium_headless if cfg.selenium_headless is not None else True)
        ),
        user_agent=args.selenium_user_agent or cfg.selenium_user_agent,
    )
    print(df.head())
