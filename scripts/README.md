# Scripts

## site_snapshot.py

Crawl a website, capture screenshots, run AI analysis on each page and build PDF/Markdown docs.

### Setup

1. Install dependencies:
   ```bash
   pip install beautifulsoup4 fpdf Pillow markdownify playwright tldextract openai
   playwright install
   ```
2. Set your `OPENAI_API_KEY` environment variable to enable per-page analysis.
3. Download the [DejaVuSans.ttf](https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf) font.
   If you download the ZIP release, extract `DejaVuSans.ttf` from the archive.
4. Save the font and set `FONT_PATH` in `site_snapshot.py` to its location.
5. Run:
   ```bash
   python scripts/site_snapshot.py --base-url http://localhost:5173 \
       --ai-model gpt-4o-mini \
       --ai-prompt "Describe this page."
   ```
6. Output appears in `site_manual/` with screenshots, per-page Markdown files (including AI analysis) and a combined PDF manual embedding the analysis text under each screenshot.

The script uses Playwright to render pages so that JavaScript-generated links are discovered correctly. Pillow enables image support in FPDF; without it, PDFs are generated without screenshots. If OpenAI analysis fails for a page, the rest of the snapshot continues with an empty analysis.
