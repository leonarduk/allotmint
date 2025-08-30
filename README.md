# AllotMint 🌱💷
[![codecov](https://codecov.io/gh/leonarduk/allotmint/branch/main/graph/badge.svg)](https://codecov.io/gh/leonarduk/allotmint)
*Tend your family’s investments like an allotment. Harvest smarter wealth.*

AllotMint is a private, server-less web app that turns real-world family
investing into a visually engaging “allotment” you tend over time. It enforces
strict compliance rules (30‑day minimum holding, 20 trades/person/month), runs
entirely on AWS S3 + Lambda, and keeps your AWS and Python skills sharp.

For setup and usage instructions, see the [USER_README](USER_README.md).

---

## MVP Scope
1. **Portfolio Viewer** – individual / adults / whole family.
2. **Compliance Engine** – 30‑day sell lock & monthly trade counter.
3. **Stock Screener v1** – PEG < 1, P/E < 20, low D/E, positive FCF.
4. **Scenario Tester (Lite)** – single‑asset price shocks.
5. **Lucy DB Pension Forecast** – inflation‑linked income overlay.

---

## Tech Stack

| Layer    | Choice                                       |
|----------|----------------------------------------------|
| Frontend | React + TypeScript → S3 + CloudFront         |
| Backend  | AWS Lambda (Python 3.12) behind API Gateway  |
| Storage  | S3 JSON / CSV (no RDBMS)                     |
| IaC      | AWS CDK (Py)                                 |

The backend, CI/CD workflows, and tests all target Python 3.12.

## Watchlist

The repo includes a lightweight Yahoo Finance watchlist. Run it locally with:

```
# backend
uvicorn app:app --reload --port 8000 --host 0.0.0.0

# frontend
npm i && npm run dev
```

---

## Backend dependencies

Runtime Python dependencies live in `requirements.txt`. Development tooling
(CDK, Playwright, moviepy, etc.) is listed in `requirements-dev.txt`. Install
both when working locally:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Workflows and helper scripts install from these files, so update them when new
packages are needed.

### Environment variables

Sensitive settings are loaded from environment variables rather than
`config.yaml`. Create a `.env` file (copy from `.env.example`) to keep them in
one place:

```
cp .env.example .env
# then edit .env with values such as
ALPHA_VANTAGE_KEY=your-alpha-vantage-api-key
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:allotmint   # optional
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ      # optional
TELEGRAM_CHAT_ID=123456789                                  # optional
```

Alternatively export variables in your shell. Unset variables simply disable
their corresponding integrations.

## Page cache

Expensive API routes cache their JSON responses under `data/cache/<page>.json`.
Each request serves the cached payload when it is fresh; on a miss or stale
entry the response is rebuilt, returned to the client and saved in the
background. A lightweight scheduler keeps caches warm by rebuilding them at a
fixed interval.

| Page           | TTL (seconds) |
|----------------|---------------|
| Portfolio views | 300 |
| Screener queries | 900 |

Adjust the `PORTFOLIO_TTL` and `SCREENER_TTL` constants in
`backend/routes/portfolio.py` and `backend/routes/screener.py` to change these
intervals. The cache helpers live in `backend/utils/page_cache.py`.

## FX rate cache & offline mode

FX conversions use daily GBP rates. When `offline_mode: true` in
`config.yaml`, rates are loaded from parquet files under
`data/timeseries/fx/<CCY>.parquet`. Each file must contain `Date` and `Rate`
columns. Populate the cache before going offline:

```bash
python - <<'PY'
from datetime import date
import pandas as pd
from backend.utils.fx_rates import fetch_fx_rate_range

df = fetch_fx_rate_range("USD", date(2024,1,1), date.today())
df.to_parquet("data/timeseries/fx/USD.parquet", index=False)
PY
```

If a currency file is missing, `_convert_to_gbp` falls back to requesting
rates from `fx_proxy_url` configured in `config.yaml`.

## Risk reporting

The backend exposes Value at Risk (VaR) metrics for each portfolio.

* **Defaults** – 95 % confidence over a 1‑day horizon and 99 % over 10 days.
* **Query** – `GET /var/{owner}?days=30&confidence=0.99` fetches a 30‑day, 99 % VaR.
* **UI** – VaR surfaces alongside portfolio charts on the performance dashboard.

**Assumptions**

* Historical simulation using daily returns from cached price series.
* Results reported in GBP.
* Calculations default to a 365‑day window (`days` parameter).

See [backend/common/portfolio_utils.py](backend/common/portfolio_utils.py) for the return series that feed the calculation
and [backend/common/constants.py](backend/common/constants.py) for currency labels.

## Portfolio reports

`GET /reports/{owner}` compiles realized gains, income and performance metrics
for a portfolio. Pass `format=csv` or `format=pdf` to download the report in
your preferred format.

## Local Quick-start

The project is split into a Python FastAPI backend and a React/TypeScript
frontend. The two communicate over HTTP which makes it easy to work on either
side in isolation. Backend runtime options are stored in `config.yaml`:

```yaml
app_env: local
uvicorn_host: 0.0.0.0
uvicorn_port: 8000
reload: true
log_config: backend/logging.ini
```

Adjust these values to change the environment or server behaviour.

Environment-specific CORS whitelists are defined in the same file:

```yaml
cors:
  local:
    - http://localhost:3000
  production:
    - https://app.allotmint.io
```

The list matching `app_env` is applied to the backend's CORS middleware.

Optional frontend tabs can be toggled in `config.yaml`:

```yaml
tabs:
  instrument: true
  performance: true
  transactions: true
  screener: true
  trading: true
  timeseries: true
  watchlist: true
  virtual: true
  reports: true
  support: true
```

Setting a tab to `false` removes its menu entry and related links from the UI.

```bash
# clone & enter
git clone git@github.com:leonarduk/allotmint.git
cd allotmint

# set up Python venv for CDK & backend (optional)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# configure API settings
# (see config.yaml for app_env, uvicorn_host, uvicorn_port, reload and log_config)
./run-local-api.sh    # or use run-backend.ps1 on Windows

# in another shell install React deps and start Vite on :5173
cd frontend
npm install
npm run dev

# visit the app
open http://localhost:5173/
```

- **Authentication**:
  - Set `API_TOKEN` and include it as an `X-API-Token` header in requests, or
  - Leave `API_TOKEN` unset to disable authentication during local development.
  See the [Authentication](USER_README.md#authentication) section for details.

## Alerts

Trading alerts support multiple transports that are enabled via environment
variables:

* **AWS SNS** – set ``SNS_TOPIC_ARN`` to publish alerts to an SNS topic using
  ``backend.common.alerts.publish_alert``.
* **Telegram** – provide ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` to
  forward alerts to a Telegram chat via ``backend.utils.telegram_utils``.

When several transports are configured, alerts are sent to each of them.

## AWS data bucket

When running the backend in AWS (``config.app_env: aws``), account and
metadata JSON files are loaded from an S3 bucket.

Set the ``DATA_BUCKET`` environment variable to the name of the bucket
containing the ``accounts/OWNER/ACCOUNT.json`` objects. The Lambda execution
role requires the following minimal IAM permissions on that bucket:

* ``s3:ListBucket`` (with a prefix of ``accounts/``) – discover available
  accounts.
* ``s3:GetObject`` on ``accounts/*`` – read account and ``person.json`` files.

## Tests

Run Python and frontend test suites with:

```bash
pytest
cd frontend && npm test
```

The `PY_COV_MIN` environment variable lets you enforce a minimum coverage
percentage during `pytest` runs. Use it together with `PYTEST_ADDOPTS` to pass
the desired threshold to `pytest`:

```bash
PY_COV_MIN=80 PYTEST_ADDOPTS="--cov-fail-under=$PY_COV_MIN" pytest
```

## Error summary helper

An optional `error_summary` section in `config.yaml` stores settings for the
`run_with_error_summary.py` utility. When the field is missing the backend falls
back to an empty mapping so the script can still be used with explicit
arguments. You can capture error lines by running the helper which writes them
to `error_summary.log`. Optionally set a default command in
`config.yaml` under `error_summary.default_command` so the script can run
without CLI arguments:

```yaml
error_summary:
  default_command: ["pytest"]
```

Running `python run_with_error_summary.py` with no arguments will then use the
configured default.

```bash
# example
python run_with_error_summary.py pytest
```

## Trading Agent

Use the helper script to run the trading agent locally. All arguments are
optional:

```bash
python scripts/run_trading_agent.py --tickers AAPL MSFT --thresholds 0.1 0.2 --indicator RSI
```

## API endpoint tester

Execute a set of HTTP calls listed in `api_test_cases.yaml` and summarise the results with GPT:

```bash
python scripts/ai_api_tester.py
```

## Deploy to AWS

The project includes an AWS CDK stack that provisions an S3 bucket and
CloudFront distribution for the frontend. To deploy the site:

```bash
# build the frontend assets first
cd frontend
npm install
npm run build
cd ..

# deploy the static site stack only
cd cdk
cdk bootstrap   # only required once per AWS account/region
DEPLOY_BACKEND=false cdk deploy StaticSiteStack

# or include the backend Lambda stack
DEPLOY_BACKEND=true cdk deploy BackendLambdaStack StaticSiteStack
# equivalently: cdk deploy BackendLambdaStack StaticSiteStack -c deploy_backend=true
```

The bucket remains private and CloudFront uses an origin access identity
with Price Class 100 to minimise cost while serving the content over HTTPS.

### Backend data bucket

Runtime portfolio data lives in a separate S3 bucket referenced by the
`DATA_BUCKET` environment variable. Files are stored under the `accounts/`
prefix:

- `accounts/<owner>/trades.csv`
- `accounts/<owner>/<account>.json`
- `accounts/<owner>/person.json`

Lambdas that read portfolio information require `s3:GetObject` permission for
these paths. A minimal IAM policy statement is:

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject"],
  "Resource": "arn:aws:s3:::YOUR_DATA_BUCKET/accounts/*"
}
```

### GitHub Actions Deployment

The CI workflow in `.github/workflows/deploy-lambda.yml` uses GitHub's
OpenID Connect (OIDC) provider to assume an IAM role at deploy time. To
enable this:

1. Create an IAM role with permissions to deploy the CDK stack.
2. Add a trust policy that allows the GitHub OIDC provider to assume the
   role. A minimal example is:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {"Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"},
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:ref:refs/heads/main"
           }
         }
       }
     ]
   }
   ```
3. Store the role ARN in the repository as the `AWS_ROLE_TO_ASSUME` secret
   and set `AWS_REGION` as needed.

Remove any long-term `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
secrets, as they are no longer required.


## 🎬 Generating the Overview Video

Install the video dependencies first. The `requirements-dev.txt` file includes
`moviepy` and `gTTS`:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Save an image named `presenter.png` in the `scripts` directory, then run:

```bash
python scripts/make_allotmint_video.py
```

The script will produce `allotmint_video.mp4` in the repository root.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
