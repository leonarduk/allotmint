#!/usr/bin/env python3
"""Crawl a website, snapshot pages, and generate PDF/Markdown docs.

How to use:
1. Install dependencies:
   pip install requests beautifulsoup4 fpdf markdownify playwright
   playwright install  # downloads headless browsers
2. Edit BASE_URL to point to your server.
3. Run: python scripts/site_snapshot.py
4. Output appears in the "site_manual" directory with screenshots,
   per-page Markdown files, and a combined PDF manual.
"""

import argparse
import asyncio
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from markdownify import markdownify
from playwright.async_api import async_playwright

# Default base URL can be overridden via CLI
BASE_URL = "https://example.com"
OUTPUT_DIR = Path("site_manual")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
MARKDOWN_DIR = OUTPUT_DIR / "markdown"


def is_same_domain(url: str) -> bool:
    return urlparse(url).netloc == urlparse(BASE_URL).netloc


def crawl_site():
    """Breadth-first crawl of pages within BASE_URL."""
    visited, pages = set(), []
    queue = deque([BASE_URL])

    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        resp = requests.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        pages.append((url, soup))

        for link in soup.select("a[href]"):
            full = urljoin(url, link["href"]).split("#")[0].rstrip("/")
            if full.startswith("http") and is_same_domain(full) and full not in visited:
                queue.append(full)

    return pages


async def take_snapshots(pages):
    """Headless browser to capture full-page screenshots."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for idx, (url, soup) in enumerate(pages, 1):
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_load_state("networkidle")
            screenshot = SCREENSHOT_DIR / f"{idx:03}.png"
            await page.screenshot(path=str(screenshot), full_page=True)
            await page.close()
            results.append((idx, url, soup, screenshot))
        await browser.close()

    return results


def extract_summary(soup: BeautifulSoup) -> str:
    """Return first non-empty paragraph text as a summary."""
    for p in soup.select("p"):
        text = p.get_text(strip=True)
        if text:
            return text
    return ""


def build_docs(entries):
    """Create PDF and Markdown files describing each page."""
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()

    for idx, url, soup, img_path in entries:
        title = soup.title.string.strip() if soup.title else url
        text = markdownify(str(soup.body)) if soup.body else ""
        summary = extract_summary(soup)
        md_content = f"# {title}\n\nURL: {url}\n\n**Summary:** {summary}\n\n{text}"

        # Markdown manual
        md_file = MARKDOWN_DIR / f"{idx:03}_{title.replace(' ', '_')}.md"
        md_file.write_text(md_content, encoding="utf-8")

        # PDF section
        pdf.add_page()
        pdf.set_font("Arial", size=14)
        pdf.multi_cell(0, 8, md_content)
        pdf.ln(5)
        pdf.image(str(img_path), w=180)

    pdf.output(str(OUTPUT_DIR / "manual.pdf"))


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl website and create manual")
    parser.add_argument("base_url", nargs="?", default=BASE_URL, help="Base URL to crawl")
    return parser.parse_args()


def main():
    args = parse_args()
    global BASE_URL
    BASE_URL = args.base_url.rstrip("/")

    pages = crawl_site()
    entries = asyncio.run(take_snapshots(pages))
    build_docs(entries)


if __name__ == "__main__":
    main()
