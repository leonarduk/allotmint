# Scripts

## lint.ps1

Run all configured linters (Python Ruff/Black and frontend ESLint) and emit a
Codex-friendly summary of any issues. The output can be pasted directly into
the Codex fix workflow.

```powershell
./scripts/lint.ps1
```

## frontend-backend-smoke.ts

Run a quick smoke test against key backend endpoints. After running any `deploy:local:*` command to start the stack, execute:

```
npm run smoke:test
```

Set `SMOKE_URL` to point at a different deployment and include `TEST_ID_TOKEN`
when the target requires authentication (the smoke runner forwards it as a
bearer token).

## smoke-test.ps1

Check one or more endpoints for an HTTP 200 response.

```powershell
# Pass URLs as parameters
./scripts/smoke-test.ps1 https://example.com https://example.com/health

# or rely on the environment variable
$env:SMOKE_TEST_URLS = "https://example.com,https://example.com/health"
./scripts/smoke-test.ps1
```

```bash
SMOKE_TEST_URLS=http://localhost:8000/health,http://localhost:5173 npm run smoke:test
```


## run-smoke-tests-all.ps1

Run the combined backend and frontend smoke suites defined in `npm run smoke:test:all`.

```powershell
./scripts/run-smoke-tests-all.ps1
```


## site_healthcheck.py

Parse the sitemap and verify that each URL responds with HTTP 200.

```bash
python scripts/site_healthcheck.py
# or on Windows PowerShell
./scripts/site-healthcheck.ps1
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

## generate_sitemap.py

Crawl a running frontend and build `frontend/public/sitemap.xml` with all internal links.

```bash
python scripts/generate_sitemap.py --base-url https://app.allotmint.io
```

Use the PowerShell wrapper for convenience:

```powershell
# Deployed site
./scripts/generate-sitemap.ps1

# Local dev server
./scripts/generate-sitemap.ps1 -Local

# Explicit URL
./scripts/generate-sitemap.ps1 -BaseUrl http://localhost:5173
```

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
