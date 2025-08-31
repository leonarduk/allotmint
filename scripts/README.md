# Scripts

## site_snapshot.py

Crawl a website, capture screenshots and build PDF/Markdown docs.

### Setup

1. Install dependencies:
   ```bash
   pip install beautifulsoup4 fpdf Pillow markdownify playwright
   playwright install
   ```
2. Download the [DejaVuSans.ttf](https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf) font.
   If you download the ZIP release, extract `DejaVuSans.ttf` from the archive.
3. Save the font and set `FONT_PATH` in `site_snapshot.py` to its location.
4. Edit `BASE_URL` in the script to point to your server.
5. Run:
   ```bash
   python scripts/site_snapshot.py
   ```
6. Output appears in `site_manual/` with screenshots, per-page Markdown files and a combined PDF manual.

The script uses Playwright to render pages so that JavaScript-generated links are discovered correctly. Pillow enables image support in FPDF; without it, PDFs are generated without screenshots.
