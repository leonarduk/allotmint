# AllotMint User Guide

## Overview
AllotMint helps families track and manage investments like tending an allotment. The app enforces compliance rules (30‑day minimum holding period and monthly trade limits) and presents portfolios and research tools through a web UI backed by a FastAPI backend and React frontend.

## Installation
1. **Clone the repository** and move into the project directory.
2. **Backend dependencies**: `pip install -r requirements.txt` (includes
   `moviepy` and `gTTS` for video generation)
3. **Frontend dependencies**: change into the `frontend/` folder and run `npm install`

## Configuration
Copy `config.example.yaml` to `config.yaml` for local defaults and
`.env.example` to `.env` to define secrets via environment variables.
=
Runtime options live in `config.yaml`:

- `app_env`: `local` for local development or `aws` for Lambda.
- `uvicorn_port`: port for the local FastAPI server.
- `reload`: enables auto-reload for development.
- `tabs`: enable or disable optional frontend tabs.
- `offline_mode`: load FX data from local parquet files.

Additional runtime settings (place these in your `.env` file or export them):

- `ALPHA_VANTAGE_KEY`: Alpha Vantage API key.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`: forward alerts to Telegram.
- `SNS_TOPIC_ARN`: publish alerts to an AWS SNS topic.
- `DATA_BUCKET`: S3 bucket containing account data when running in AWS.

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

If `API_TOKEN` is unset, the API remains open which is convenient for local development and tests.

## Common workflows
- **Start the backend**: `uvicorn app:app --reload --port 8000`
- **Start the frontend**: `cd frontend && npm run dev`
- **Run tests**:
  - Backend: `pytest`
  - Frontend: `cd frontend && npm test`
- **Run the trading agent**: `python scripts/run_trading_agent.py --tickers AAPL MSFT`
- **Deploy to AWS**:
  1. `cd frontend && npm run build`
  2. `cd cdk && cdk deploy StaticSiteStack`

