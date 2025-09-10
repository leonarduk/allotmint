# Scripts

## frontend-backend-smoke.ts

Run a quick smoke test against key backend endpoints. After running any `deploy:local:*` command to start the stack, execute:

```
npm run smoke:test
```

Set `API_BASE` to target a different backend URL and `TEST_ID_TOKEN` if needed.

## smoke-test.ps1

Check a single endpoint for an HTTP 200 response.

```powershell
# Pass URL as a parameter
./scripts/smoke-test.ps1 https://example.com

# or rely on the environment variable
$env:SMOKE_TEST_URL = "https://example.com"
./scripts/smoke-test.ps1
```

## site_snapshot.py

Crawl a website, capture screenshots, run AI analysis on each page and build PDF/Markdown docs.

### Setup

1. Install dependencies:
   ```bash
   pip install beautifulsoup4 fpdf Pillow markdownify playwright tldextract openai python-dotenv
   playwright install
   ```
2. Provide your `OPENAI_API_KEY` for per-page analysis. The script will read it
   from the environment and automatically load a `.env` file if `python-dotenv`
   is installed. For example:
   ```bash
   export OPENAI_API_KEY=your_api_key
   # or place the key in a .env file:
   echo "OPENAI_API_KEY=your_api_key" > .env
   ```
3. Download the [DejaVuSans.ttf](https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf) font.
   If you download the ZIP release, extract `DejaVuSans.ttf` from the archive.
4. Save the font and set `FONT_PATH` in `site_snapshot.py` to its location.
5. Run:
   ```bash
   python scripts/site_snapshot.py --base-url http://localhost:5173 \
       --ai-model gpt-4o-mini \
       --ai-prompt "Describe this page."
   ```
6. Output appears in `site_manual/` with screenshots, per-page Markdown files (including AI analysis) and a combined PDF manual
embedding the analysis text under each screenshot.

The script uses Playwright to render pages so that JavaScript-generated links are discovered correctly. Pillow enables image support in FPDF; without it, PDFs are generated without screenshots. If OpenAI analysis fails for a page, the rest of the snapshot continues with an empty analysis.

## import_transactions.py

Upload a local transaction export to the running backend for parsing:

```
python scripts/import_transactions.py degiro path/to/transactions.csv
```

Use `--api` to point at a different backend URL. Parsed transactions are printed as JSON.

## reconcile_drawdown.py

Inspect max drawdowns and dump holding price data when the portfolio suffers a
large daily drop:

```
python scripts/reconcile_drawdown.py alice --days 180
python scripts/reconcile_drawdown.py --group family --ticker VUSA.L --ticker MSFT
```

Price series for each holding is written to `TICKER.EXCHANGE.csv` and `.json`
in the current directory for manual inspection.
