# AllotMint User Guide

## Overview
AllotMint helps families track and manage investments like tending an allotment. The app enforces compliance rules (30‑day minimum holding period and monthly trade limits) and presents portfolios and research tools through a web UI backed by a FastAPI backend and React frontend.

## Installation
1. **Clone the repository** and move into the project directory.
2. **Backend dependencies**: `pip install -r requirements.txt -r requirements-dev.txt` (installs
   `moviepy`, `gTTS`, and other development tools)
3. **Frontend dependencies**: change into the `frontend/` folder and run `npm install`

## Configuration
Runtime options live in `config.yaml`:

- `app_env`: `local` for local development or `aws` for Lambda.
- `uvicorn_host`: host interface for the local FastAPI server.
- `uvicorn_port`: port for the local FastAPI server.
- `reload`: enables auto-reload for development.
- `tabs`: enable or disable optional frontend tabs.
- `offline_mode`: load FX data from local parquet files.
- `alpha_vantage_enabled`: set to `false` to skip Alpha Vantage API calls.

Additional runtime settings are supplied via environment variables. Copy
`.env.example` to `.env` and fill in values such as:

- `ALPHA_VANTAGE_KEY`: API key for Alpha Vantage data (example: `demo`).
- `SNS_TOPIC_ARN`: publish alerts to an AWS SNS topic (e.g.
  `arn:aws:sns:us-east-1:123456789012:allotmint`).
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`: forward alerts to Telegram
  (e.g. `123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ` and `123456789`).
- `DATA_BUCKET`: S3 bucket containing account data when running in AWS.
- `METADATA_BUCKET` and `METADATA_PREFIX`: S3 bucket and key prefix for instrument metadata.


## Authentication
Sensitive endpoints such as portfolio or transaction data can be secured with a simple API token.

1. Generate a token:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Export the token before starting the backend:

   ```bash
   export API_TOKEN="<token-from-step-1>"
   ```

3. Include the token in requests using the `X-API-Token` header:

   ```bash
   curl -H "X-API-Token: $API_TOKEN" http://localhost:8000/portfolio/alex
   ```

   Another example fetching the list of owners:

   ```bash
   curl -H "X-API-Token: $API_TOKEN" http://localhost:8000/owners
   ```

   Omitting the header when `API_TOKEN` is set will result in `401 Unauthorized`.

If `API_TOKEN` is unset, the API remains open which is convenient for local development and tests.

## Using a remote backend
If the backend API is not running on `http://localhost:8000`, configure the
frontend to use the correct base URL.

1. Set `VITE_ALLOTMINT_API_BASE` before starting the frontend:

   ```bash
   export VITE_ALLOTMINT_API_BASE="https://api.example.com"
   cd frontend && npm run dev
   ```

2. Or create a `.env` file inside `frontend/` with:

   ```
   VITE_ALLOTMINT_API_BASE=https://api.example.com
   ```

If the variable is unset the UI defaults to `http://localhost:8000` (or
`VITE_API_URL` if defined).

## Common workflows
- **Start the backend**: `uvicorn app:app --reload --port 8000 --host 0.0.0.0`
- **Start the frontend**: `cd frontend && npm run dev`
- **Run tests**:
  - Backend: `pytest`
  - Frontend: `cd frontend && npm test`
  - Sample account data under `data/accounts/` (e.g.,
    `data/accounts/alice/savings.json`) allows tests to run without extra
    setup.
- **Get trading agent signals**: `curl http://localhost:8000/trading-agent/signals` or invoke the `price_refresh` Lambda
- **Deploy to AWS**:
  1. `cd frontend && npm run build`
  2. `cd cdk && DEPLOY_BACKEND=false cdk deploy StaticSiteStack`
  3. To include the backend: `DEPLOY_BACKEND=true cdk deploy BackendLambdaStack StaticSiteStack`

