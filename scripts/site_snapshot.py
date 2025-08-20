#!/usr/bin/env python3
"""Crawl a website, snapshot pages, and generate PDF/Markdown docs.

How to use:
1. Install dependencies:
   pip install requests beautifulsoup4 fpdf Pillow markdownify playwright
   playwright install  # downloads headless browsers
2. Edit BASE_URL to point to your server.
3. Run: python scripts/site_snapshot.py
4. Output appears in the "site_manual" directory with screenshots,
   per-page Markdown files, and a combined PDF manual.

Pillow provides image support for FPDF; without it, PDFs are generated without screenshots.
"""

import asyncio
import logging
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from markdownify import markdownify
from playwright.async_api import async_playwright

BASE_URL = "https://example.com"  # Change to your server
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
            full = urljoin(url, link["href"])
            if full.startswith("http") and is_same_domain(full):
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
            await page.goto(url)
            screenshot = SCREENSHOT_DIR / f"{idx:03}.png"
            await page.screenshot(path=str(screenshot), full_page=True)
            await page.close()
            results.append((idx, url, soup, screenshot))
        await browser.close()

    return results


def build_docs(entries):
    """Create PDF and Markdown files describing each page."""
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()

    for idx, url, soup, img_path in entries:
        title = soup.title.string.strip() if soup.title else url
        text = markdownify(str(soup.body)) if soup.body else ""
        md_content = f"# {title}\n\nURL: {url}\n\n{text}"

        # Markdown manual
        md_file = MARKDOWN_DIR / f"{idx:03}_{title.replace(' ', '_')}.md"
        md_file.write_text(md_content, encoding="utf-8")

        # PDF section
        pdf.add_page()
        pdf.set_font("Arial", size=14)
        pdf.multi_cell(0, 8, md_content)
        pdf.ln(5)
        try:
            pdf.image(str(img_path), w=180)
        except OSError as exc:
            logging.warning(
                "Skipping image %s because Pillow is not installed or failed to read it: %s",
                img_path,
                exc,
            )

    pdf.output(str(OUTPUT_DIR / "manual.pdf"))


def main():
    pages = crawl_site()
    entries = asyncio.run(take_snapshots(pages))
    build_docs(entries)


if __name__ == "__main__":
    main()
