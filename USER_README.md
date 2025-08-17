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

### Authentication

The backend can validate OAuth2/JWT tokens issued by **Amazon Cognito**. The
user pool ID and app client ID are stored in **AWS Secrets Manager**:

1. Create a secret (e.g. `allotmint-cognito`) with JSON data:
   ```json
   {"user_pool_id": "<pool id>", "app_client_id": "<client id>"}
   ```
2. Grant the backend IAM role permission to read this secret.
3. Set environment variables `COGNITO_SECRET_NAME` (secret name) and
   `AWS_REGION`.

With these values configured the API will verify incoming JWTs using Cognito’s
JWKS. Local development and tests skip verification when the secret is absent.

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

