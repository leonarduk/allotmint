import logging
import time
from datetime import date, timedelta

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Setup logger
logger = logging.getLogger("ft_timeseries")
logging.basicConfig(level=logging.DEBUG)


CHROMEDRIVER_PATH = r"C:\workspaces\chromedriver-win64\chromedriver.exe"  # update path if needed


def set_date_range_and_submit(driver, from_date: str, to_date: str):
    """
    Set the date range on the FT time series page and click 'Update'.
    """
    logger.debug(f"Setting date range: {from_date} → {to_date}")
    try:
        from_input = driver.find_element(By.ID, "startDate")
        to_input = driver.find_element(By.ID, "endDate")

        driver.execute_script(f"arguments[0].value = '{from_date}'", from_input)
        driver.execute_script(f"arguments[0].value = '{to_date}'", to_input)

        update_btn = driver.find_element(By.ID, "submitBtn")
        update_btn.click()

        logger.debug("Clicked 'Update' button to reload table")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.mod-ui-table"))
        )

    except Exception as e:
        logger.warning(f"Could not set date range: {e}")


def fetch_ft_timeseries(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Fetch FT.com time series for a given ticker over the past `days` days.
    """
    url = f"https://markets.ft.com/data/funds/tearsheet/historical?s={ticker}"
    logger.debug(f"Setting up headless Chrome for ticker {ticker}")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)

    try:
        logger.debug(f"Navigating to {url}")
        driver.get(url)

        # Calculate date range
        today = date.today()
        from_date = (today - timedelta(days=days)).strftime("%d/%m/%Y")
        to_date = today.strftime("%d/%m/%Y")
        set_date_range_and_submit(driver, from_date, to_date)

        logger.debug("Waiting for FT table to load...")
        table = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.mod-ui-table"))
        )

        rows = table.find_elements(By.TAG_NAME, "tr")
        logger.debug(f"Found {len(rows) - 1} data rows in table")

        data = []
        for i, row in enumerate(rows[1:], start=1):
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) < 5:
                logger.warning(f"Row {i} skipped: not enough columns ({len(cols)})")
                continue

            try:
                date_str = cols[0].text.strip()
                close = float(cols[1].text.replace(',', ''))
                open_ = float(cols[2].text.replace(',', ''))
                high = float(cols[3].text.replace(',', ''))
                low = float(cols[4].text.replace(',', ''))

                data.append([date_str, open_, high, low, close])
                logger.debug(f"Row {i} parsed: {date_str} O:{open_} H:{high} L:{low} C:{close}")
            except Exception as e:
                logger.warning(f"Error parsing row {i}: {e}")

        if not data:
            raise RuntimeError("No valid time series data parsed from FT")

        df = pd.DataFrame(data, columns=["Date", "Open", "High", "Low", "Close"])
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
        df = df.sort_values("Date").tail(days)
        df["Volume"] = None
        df["Ticker"] = ticker
        logger.info(f"Successfully fetched {len(df)} rows for {ticker}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")
        raise

    finally:
        driver.quit()
        logger.debug("Closed Selenium driver")


if __name__ == "__main__":
    # Example: Legal & General Sterling Corporate Bond Index Fund I Acc
    df = fetch_ft_timeseries("GB00B45Q9038:GBP", days=365)
    print(df.head())
