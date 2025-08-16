# AllotMint User Guide

## Overview
AllotMint helps families track and manage investments like tending an allotment. The app enforces compliance rules (30‑day minimum holding period and monthly trade limits) and presents portfolios and research tools through a web UI backed by a FastAPI backend and React frontend.

## Installation
1. **Clone the repository** and move into the project directory.
2. **Backend dependencies**: `pip install -r requirements.txt` (includes
   `moviepy` and `gTTS` for video generation)
3. **Frontend dependencies**: change into the `frontend/` folder and run `npm install`

## Configuration
Runtime options live in `config.yaml`:

- `app_env`: `local` for local development or `aws` for Lambda.
- `uvicorn_port`: port for the local FastAPI server.
- `reload`: enables auto-reload for development.
- `tabs`: enable or disable optional frontend tabs.
- `offline_mode`: load FX data from local parquet files.

Additional runtime settings:

- `SNS_TOPIC_ARN`: publish alerts to an AWS SNS topic.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`: forward alerts to Telegram.
- `DATA_BUCKET` (environment variable): S3 bucket containing account data when running in AWS.

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

