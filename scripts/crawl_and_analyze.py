#!/usr/bin/env python3
"""Capture menu page screenshots and analyze them with a GPT model."""

import argparse
import asyncio
import base64
from pathlib import Path

from playwright.async_api import async_playwright
from openai import OpenAI


async def take_screenshots(urls, out_dir: Path) -> list[Path]:
    """Visit each URL and save a full-page screenshot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        for idx, url in enumerate(urls, start=1):
            await page.goto(url, wait_until="networkidle")
            file_path = out_dir / f"menu_{idx}.png"
            print(f"Saving screenshot {url} to: {file_path}")
            await page.screenshot(path=file_path, full_page=True)
            saved_paths.append(file_path)
        await browser.close()
    return saved_paths


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


async def main(urls: list[str], out_dir: Path, model: str) -> None:
    images = await take_screenshots(urls, out_dir)
    # analyze_images(images, model)




if __name__ == "__main__":
    urls = ["http://localhost:5174"]
    out_dir = Path("screenshots")
    model = "openai"
    asyncio.run(main(urls, out_dir, model))
