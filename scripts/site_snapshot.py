#!/usr/bin/env python3
"""
Site Snapshotper — crawl a SPA/site and generate a printable PDF manual,
with optional full-page PNG screenshots and markdown extracts.

Fixes:
- First-page discovery bug (visited check happened before canonicalization).
- Always include the start URL even if navigation returns about:blank.
- No fpdf2 deprecation warnings (uses XPos/YPos, no 'uni' arg).
- Works with deep routes (e.g., http://localhost:5173/movers).
- Embeds screenshots only if Pillow is installed; otherwise skips cleanly.

Install:
  pip install beautifulsoup4 fpdf markdownify playwright tldextract
  playwright install
Optional for images in PDF:
  pip install pillow

Example:
  python site_snapshot.py --base-url http://localhost:5173/movers --depth 1 --max-pages 30
"""

import asyncio
import argparse
import logging
import re
import base64
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Set, Tuple, List
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl
import shutil

# Optional Pillow detection (PNG embedding)
try:
    from PIL import Image  # noqa: F401

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

import tldextract
from bs4 import BeautifulSoup
from fpdf import FPDF, XPos, YPos
from markdownify import markdownify
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from openai import OpenAI

# -------- Defaults --------
OUTPUT_DIR = Path("site_manual")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
MARKDOWN_DIR = OUTPUT_DIR / "markdown"
PDF_PATH = OUTPUT_DIR / "manual.pdf"
SITEPLAN_DIR = Path("docs/siteplan")

# Best-effort font discovery (Unicode if available)
CANDIDATE_FONTS = [
    Path(__file__).with_name("DejaVuSans.ttf"),
    Path("DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),  # Latin-1 fallback
]
FONT_PATH: Optional[Path] = next((p for p in CANDIDATE_FONTS if p.exists()), None)

DEFAULT_HIDE = [".toast", ".alerts", ".notification", "script", "style"]
DEFAULT_CONTENT_SELECTORS = ["main", "[role='main']", "#root", "#app", "body"]
DEFAULT_VIEWPORT = (1400, 900)
USER_AGENT = "SiteSnapshotper/1.2 (+https://example.invalid)"


@dataclass(frozen=True)
class PageDoc:
    idx: int
    url: str
    title: str
    screenshot: Path
    markdown: Path
    analysis: str


# -------- Helpers --------
def _same_reg_domain(a: str, b: str) -> bool:
    ea, eb = tldextract.extract(a), tldextract.extract(b)
    return (ea.domain, ea.suffix) == (eb.domain, eb.suffix)


def _canonicalize(
    url: str, drop_query: bool, keep_params: Optional[Iterable[str]]
) -> str:
    u = urlparse(url)
    path = re.sub(r"/{2,}", "/", u.path or "/")
    if drop_query:
        query = ""
    else:
        q = dict(parse_qsl(u.query, keep_blank_values=False))
        if keep_params:
            k = set(keep_params)
            q = {kk: vv for kk, vv in q.items() if kk in k}
        query = "&".join(f"{kk}={vv}" for kk, vv in sorted(q.items()))
    return urlunparse((u.scheme, u.netloc, path.rstrip("/") or "/", "", query, ""))


def _matches_any(patterns: Iterable[re.Pattern], path: str) -> bool:
    return any(p.search(path) for p in patterns)


def _compile_patterns(exprs: Iterable[str]) -> List[re.Pattern]:
    return [re.compile(e) for e in exprs]


def _slug(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_")[:120] or "page"


def _safe_text(s: str, unicode_ok: bool) -> str:
    if unicode_ok:
        return s
    s = (
        s.replace("—", "-")
        .replace("–", "-")
        .replace("•", "*")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    return s.encode("latin-1", "replace").decode("latin-1")


def _wrap_url_for_pdf(url: str) -> str:
    return (
        url.replace("/", "/\u200b")
        .replace("-", "-\u200b")
        .replace("?", "?\u200b")
        .replace("&", "&\u200b")
        .replace("=", "=\u200b")
    )


async def _hide_selectors(page, selectors: Iterable[str]):
    if not selectors:
        return
    js = """
    (sels) => {
      for (const sel of sels) {
        for (const el of document.querySelectorAll(sel)) {
          el.style.visibility = 'hidden';
          el.style.opacity = '0';
          el.style.maxHeight = '0';
          el.style.pointerEvents = 'none';
        }
      }
    }"""
    await page.evaluate(js, list(selectors))


async def _extract_markdown(html: str, selectors: List[str]) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            return markdownify(str(node))
    return markdownify(str(soup.body)) if soup.body else ""


# -------- Crawl + Snapshot --------
async def crawl(
    base_url: str,
    include: List[re.Pattern],
    exclude: List[re.Pattern],
    depth: int,
    max_pages: int,
    drop_query: bool,
    keep_params: Optional[List[str]],
    network_idle_ms: int,
) -> List[str]:
    """
    Returns a list of canonical URLs to snapshot.
    Fix: do NOT mark as visited before canonicalization; keep separate sets for:
      - seen (BFS dedupe)
      - added (already scheduled for snapshot)
    Always add the (canonical) start page even if it loads as about:blank.
    """
    parsed_start = urlparse(base_url)
    if not parsed_start.scheme:
        raise ValueError("--base-url must include scheme, e.g., http://localhost:5173/")

    queue: deque[Tuple[str, int]] = deque([(base_url, 0)])
    seen: Set[str] = set()  # dedupe crawl frontier by canonical URL
    added: Set[str] = set()  # URLs included in output list
    out: List[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)

        while queue and len(out) < max_pages:
            raw_url, d = queue.popleft()
            if d > depth:
                continue

            page = await context.new_page()
            html = ""
            cur_url = raw_url
            try:
                await page.goto(
                    raw_url, wait_until="networkidle", timeout=network_idle_ms
                )
                html = await page.content()
                cur_url = page.url or raw_url
            except PWTimeout:
                logging.warning("Timeout loading %s", raw_url)
            except Exception as e:
                logging.warning("Error loading %s: %s", raw_url, e)
            finally:
                await page.close()

            canon = _canonicalize(cur_url, drop_query, keep_params)
            # If Playwright gave us about:blank, keep the requested URL canon
            if urlparse(canon).scheme == "about":
                canon = _canonicalize(raw_url, drop_query, keep_params)

            if canon in seen:
                continue
            seen.add(canon)

            path = urlparse(canon).path or "/"
            if include and not _matches_any(include, path):
                pass  # not included → don't add to out
            elif exclude and _matches_any(exclude, path):
                pass  # excluded
            else:
                if canon not in added:
                    out.append(canon)
                    added.add(canon)

            # BFS: extract links for next depth, but only from successful HTML
            if d < depth and html:
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.select("a[href]"):
                    href = (a.get("href") or "").strip()
                    if not href:
                        continue
                    full = urljoin(cur_url, href)
                    if not full.startswith("http"):
                        continue
                    if not _same_reg_domain(full, base_url):
                        continue
                    nxt = _canonicalize(full, drop_query, keep_params)
                    if nxt not in seen:
                        queue.append((nxt, d + 1))

        await context.close()
        await browser.close()

    return out[:max_pages]


async def snapshot_pages(
    urls: List[str],
    hide_selectors: List[str],
    content_selectors: List[str],
    out_dir: Path,
    viewport: Tuple[int, int],
    concurrency: int,
    page_timeout_ms: int,
) -> List[PageDoc]:
    out_dir.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    results: List[PageDoc] = []
    client = OpenAI()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            user_agent=USER_AGENT,
        )

        async def _work(idx: int, url: str):
            async with sem:
                page = await context.new_page()
                try:
                    await page.goto(
                        url, wait_until="networkidle", timeout=page_timeout_ms
                    )
                    await _hide_selectors(page, hide_selectors)
                    await page.wait_for_timeout(300)
                    title = (await page.title()) or url
                    png_path = SCREENSHOT_DIR / f"{idx:03}_{_slug(title)}.png"
                    try:
                        await page.screenshot(path=str(png_path), full_page=True)
                    except Exception as e_img:
                        logging.warning("Screenshot failed for %s: %s", url, e_img)
                    html = await page.content()
                    md = await _extract_markdown(html, content_selectors)
                    analysis = ""
                    if png_path.exists():
                        try:
                            b64_img = base64.b64encode(png_path.read_bytes()).decode("utf-8")
                            resp = await asyncio.to_thread(
                                client.chat.completions.create,
                                model="gpt-4o-mini",
                                messages=[
                                    {
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Describe this page.",
                                            },
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:image/png;base64,{b64_img}",
                                                },
                                            },
                                        ],
                                    }
                                ],
                            )
                            analysis = resp.choices[0].message.content.strip()
                        except Exception as e_ai:
                            logging.warning("Analysis failed for %s: %s", url, e_ai)
                    md_path = MARKDOWN_DIR / f"{idx:03}_{_slug(title)}.md"
                    md_text = f"# {title}\n\nURL: {url}\n\n{md}"
                    if analysis:
                        md_text += f"\n\n## Analysis\n\n{analysis}"
                    md_path.write_text(md_text, encoding="utf-8")
                    results.append(
                        PageDoc(
                            idx=idx,
                            url=url,
                            title=title,
                            screenshot=png_path,
                            markdown=md_path,
                            analysis=analysis,
                        )
                    )
                finally:
                    await page.close()

        await asyncio.gather(*(_work(i + 1, u) for i, u in enumerate(urls)))
        await context.close()
        await browser.close()

    results.sort(key=lambda d: d.idx)
    return results


def build_pdf(
    pages: List[PageDoc],
    pdf_path: Path,
    font_path: Optional[Path] = None,
    summary: Optional[str] = None,
):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    unicode_font = False
    if font_path and font_path.exists() and font_path.suffix.lower() == ".ttf":
        pdf.add_font("AppFont", fname=str(font_path))
        pdf.set_font("AppFont", size=12)
        unicode_font = True
    else:
        pdf.set_font("Helvetica", size=12)

    def cell(text: str, size: int = 12, bold: bool = False):
        t = _safe_text(text, unicode_font)
        if bold and unicode_font:
            pdf.set_font("AppFont", size=size)
        elif bold:
            pdf.set_font("Helvetica", style="B", size=size)
        else:
            pdf.set_font("AppFont" if unicode_font else "Helvetica", size=size)
        pdf.cell(0, 8 if size >= 12 else 6, t, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def multicell(text: str, size: int = 11):
        t = _safe_text(text, unicode_font)
        pdf.set_font("AppFont" if unicode_font else "Helvetica", size=size)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w=0, h=5, text=t, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.add_page()
    cell("Site Manual", size=18, bold=True)
    cell(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    pdf.ln(2)
    cell("Contents", size=14, bold=True)
    pdf.ln(1)
    for d in pages:
        title = d.title.strip() or d.url
        url_wrapped = _wrap_url_for_pdf(d.url)
        multicell(f"{d.idx:03}  {title}  -  {url_wrapped}")

    if summary:
        pdf.add_page()
        cell("Site-wide Summary", size=16, bold=True)
        pdf.ln(2)
        multicell(summary, size=11)

    for d in pages:
        pdf.add_page()
        title = d.title.strip() or d.url
        url_wrapped = _wrap_url_for_pdf(d.url)
        multicell(f"{d.idx:03}  {title}\n{url_wrapped}")
        pdf.ln(2)

        if PIL_AVAILABLE and d.screenshot.exists():
            try:
                max_w = pdf.w - pdf.l_margin - pdf.r_margin
                pdf.image(str(d.screenshot), w=max_w)
                pdf.ln(2)
            except Exception as e:
                logging.warning("Could not embed image for %s: %s", d.url, e)
        if d.analysis:
            multicell(d.analysis, size=11)
            pdf.ln(2)

        try:
            text = d.markdown.read_text(encoding="utf-8")
            lines = text.splitlines()[2:]
            if "## Analysis" in lines:
                idx = lines.index("## Analysis")
                lines = lines[:idx]
            body = "\n".join(lines).strip()
            if body:
                multicell(body, size=11)
        except Exception as e:
            logging.warning("Could not embed markdown for %s: %s", d.url, e)

    pdf.output(str(pdf_path))


# -------- CLI --------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Snapshot a site into screenshots, markdown, and a combined PDF."
    )
    ap.add_argument(
        "--base-url",
        required=True,
        help="Start URL (can be a deep route, e.g., http://localhost:5173/movers)",
    )
    ap.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Output directory (default: site_manual)",
    )
    ap.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Max crawl depth from start URL (default: 2)",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="Max number of pages to snapshot (default: 200)",
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel page snapshots (default: 4)",
    )
    ap.add_argument(
        "--viewport",
        default=f"{DEFAULT_VIEWPORT[0]}x{DEFAULT_VIEWPORT[1]}",
        help="Viewport WxH, e.g., 1440x900",
    )
    ap.add_argument(
        "--include",
        action="append",
        default=[],
        help="Regex for allowed paths (repeatable). If none, allow all.",
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Regex for excluded paths (repeatable).",
    )
    ap.add_argument(
        "--drop-query",
        action="store_true",
        help="Drop query strings when canonicalizing URLs.",
    )
    ap.add_argument(
        "--keep-param",
        action="append",
        default=[],
        help="If keeping query, whitelist these params (repeatable).",
    )
    ap.add_argument(
        "--hide",
        action="append",
        default=[],
        help="CSS selectors to hide before screenshot (repeatable).",
    )
    ap.add_argument(
        "--content-selector",
        action="append",
        default=[],
        help="Selectors to extract markdown from (repeatable).",
    )
    ap.add_argument(
        "--network-idle-ms",
        type=int,
        default=15000,
        help="Timeout for page loads (ms).",
    )
    ap.add_argument(
        "--page-timeout-ms",
        type=int,
        default=20000,
        help="Timeout per snapshot page (ms).",
    )
    ap.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    return ap.parse_args()


async def main_async(ns: argparse.Namespace):
    logging.basicConfig(level=getattr(logging, ns.log_level))
    base = ns.base_url

    include = _compile_patterns(ns.include) if ns.include else []
    exclude = _compile_patterns(ns.exclude) if ns.exclude else []
    keep_params = ns.keep_param or None

    m = re.match(r"^(\d+)x(\d+)$", ns.viewport)
    viewport = (int(m.group(1)), int(m.group(2))) if m else DEFAULT_VIEWPORT

    out_dir = Path(ns.output_dir)
    global OUTPUT_DIR, SCREENSHOT_DIR, MARKDOWN_DIR, PDF_PATH
    OUTPUT_DIR = out_dir
    SCREENSHOT_DIR = out_dir / "screenshots"
    MARKDOWN_DIR = out_dir / "markdown"
    PDF_PATH = out_dir / "manual.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    hide = ns.hide or DEFAULT_HIDE
    content_selectors = ns.content_selector or DEFAULT_CONTENT_SELECTORS

    urls = await crawl(
        base_url=base,
        include=include,
        exclude=exclude,
        depth=ns.depth,
        max_pages=ns.max_pages,
        drop_query=ns.drop_query and not ns.keep_param,
        keep_params=keep_params,
        network_idle_ms=ns.network_idle_ms,
    )
    if not urls:
        logging.error(
            "No pages discovered. Check --base-url and include/exclude patterns."
        )
        return

    pages = await snapshot_pages(
        urls=urls,
        hide_selectors=hide,
        content_selectors=content_selectors,
        out_dir=out_dir,
        viewport=viewport,
        concurrency=max(1, ns.concurrency),
        page_timeout_ms=ns.page_timeout_ms,
    )
    analyses = [d.analysis for d in pages if d.analysis]
    summary_text = ""
    if analyses:
        try:
            client = OpenAI()
            combined = "\n\n".join(analyses)
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Given the following per-page analyses, provide an overall summary of the site's strengths and weaknesses.",
                            },
                            {"type": "text", "text": combined},
                        ],
                    }
                ],
            )
            summary_text = resp.choices[0].message.content.strip()
        except Exception as e:
            logging.warning("Site-wide summary failed: %s", e)

    if summary_text:
        summary_path = OUTPUT_DIR / "summary.md"
        summary_path.write_text(f"# Site Summary\n\n{summary_text}\n", encoding="utf-8")

    build_pdf(pages, PDF_PATH, FONT_PATH if FONT_PATH else None, summary=summary_text or None)
    print(f"OK • {len(pages)} pages → {out_dir}")
    print(f"- PDF: {PDF_PATH}")
    if summary_text:
        print(f"- Summary: {summary_path}")
    print(f"- Screenshots: {SCREENSHOT_DIR}")
    print(f"- Markdown: {MARKDOWN_DIR}")

    # Copy markdown to docs/siteplan and build README index
    SITEPLAN_DIR.mkdir(parents=True, exist_ok=True)
    # Remove existing markdown files in siteplan (keep README)
    for md_file in SITEPLAN_DIR.glob("*.md"):
        if md_file.name.lower() != "readme.md":
            md_file.unlink()
    links = []
    for d in pages:
        dest = SITEPLAN_DIR / d.markdown.name
        shutil.copy(d.markdown, dest)
        links.append((d.title.strip().replace("\n", " "), dest.name))

    index = ["# Site Plan", ""]
    for title, name in links:
        index.append(f"- [{title}](./{name})")
    index.append("")
    index.append("<!-- Generated by scripts/site_snapshot.py -->")
    (SITEPLAN_DIR / "README.md").write_text("\n".join(index), encoding="utf-8")
    print(f"- Site plan markdown copied to {SITEPLAN_DIR}")


def main():
    ns = parse_args()
    try:
        asyncio.run(main_async(ns))
    except KeyboardInterrupt:
        print("Interrupted.")


if __name__ == "__main__":
    main()
