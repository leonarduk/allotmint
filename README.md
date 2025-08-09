# AllotMint 🌱💷
*Tend your family’s investments like an allotment. Harvest smarter wealth.*

AllotMint is a private, server-less web app that turns real-world family
investing into a visually engaging “allotment” you tend over time. It enforces
strict compliance rules (30‑day minimum holding, 20 trades/person/month), runs
entirely on AWS S3 + Lambda, and keeps your AWS and Python skills sharp.

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

---

## Backend dependencies

All backend Python dependencies live in the top-level `requirements.txt` file.
Workflows and helper scripts install from this list, so update it when new packages are needed.

## Local Quick-start

The project is split into a Python FastAPI backend and a React/TypeScript
frontend. The two communicate over HTTP which makes it easy to work on either
side in isolation.

```bash
# clone & enter
git clone git@github.com:leonarduk/allotmint.git
cd allotmint

# set up Python venv for CDK & backend (optional)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the API locally on :8000
./run-local-api.sh

# in another shell install React deps and start Vite on :5173
cd frontend
npm install
npm run dev

# visit the app
open http://localhost:5173/
```

## Tests

Run Python and frontend test suites with:

```bash
pytest
cd frontend && npm test
```

## Error summary helper

Use the `run_with_error_summary.py` script to capture error lines when running
commands. A log file `error_summary.log` will be created with a summary of
errors which you can attach when reporting bugs.

```bash
# example
python run_with_error_summary.py pytest
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

# deploy the static site stack
cd cdk
cdk bootstrap   # only required once per AWS account/region
cdk deploy StaticSiteStack
```

The bucket remains private and CloudFront uses an origin access identity
with Price Class 100 to minimise cost while serving the content over HTTPS.

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

