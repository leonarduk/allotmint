#!/usr/bin/env python3
"""Crawl a site, capture page screenshots, and optionally analyze them.

This script performs a breadth‑first crawl starting from one or more URLs and
captures a screenshot of each page discovered within the same domain. The
screenshots can then be sent to a GPT model for analysis.
"""

import argparse
import asyncio
import base64
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import Error, async_playwright
from openai import OpenAI


async def take_screenshots(urls, out_dir: Path) -> list[Path]:
    """Visit each URL and save a full-page screenshot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        for idx, url in enumerate(urls, start=1):
            try:
                await page.goto(url, wait_until="networkidle")
            except Error as exc:
                print(f"Failed to navigate to {url}: {exc}")
                continue
            file_path = out_dir / f"menu_{idx}.png"
            print(f"Saving screenshot {url} to: {file_path}")
            await page.screenshot(path=file_path, full_page=True)
            saved_paths.append(file_path)
        await browser.close()
    return saved_paths


async def crawl_urls(start_urls: list[str], max_pages: int) -> list[str]:
    """Breadth-first crawl limited to pages within the starting domains."""
    visited: set[str] = set()
    queue = deque(start_urls)
    found: list[str] = []
    base_domains = {urlparse(u).netloc for u in start_urls}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        while queue and len(found) < max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle")
            except Error as exc:
                print(f"Failed to navigate to {url}: {exc}")
                await page.close()
                continue

            found.append(url)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            for link in soup.select("a[href]"):
                full = urljoin(url, link["href"])
                if (
                    full.startswith("http")
                    and urlparse(full).netloc in base_domains
                    and full not in visited
                ):
                    queue.append(full)
            await page.close()
        await browser.close()

    return found


def analyze_images(image_paths: list[Path], model: str) -> None:
    """Send screenshots to the GPT model and print its analysis."""
    client = OpenAI()
    for img_path in image_paths:
        with open(img_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Describe this menu page.",
                        },
                        {"type": "input_image", "image_base64": b64_img},
                    ],
                }
            ],
        )
        print(f"Analysis for {img_path.name}:\n{response.choices[0].message.content}\n")


async def main(start_urls: list[str], out_dir: Path, model: str, max_pages: int) -> None:
    to_visit = await crawl_urls(start_urls, max_pages)
    _images = await take_screenshots(to_visit, out_dir)
    # analyze_images(_images, model)


def _parse_urls(raw_urls: list[str]) -> list[str]:
    """Convert a list of raw URL or port inputs to full URLs."""
    parsed: list[str] = []
    for item in raw_urls:
        if item.isdigit():
            parsed.append(f"http://localhost:{item}")
        else:
            parsed.append(item)
    return parsed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Capture screenshots of one or more URLs and analyze them."
    )
    parser.add_argument(
        "urls",
        nargs="+",
        help="Full URLs or port numbers to capture. Port numbers imply http://localhost:<port>.",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        default="screenshots",
        help="Directory to save screenshots",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="openai",
        help="Model to use for analysis",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Maximum number of pages to crawl",
    )
    args = parser.parse_args()
    parsed_urls = _parse_urls(args.urls)
    asyncio.run(main(parsed_urls, Path(args.out_dir), args.model, args.max_pages))
