# AllotMint 🌱💷
*Tend your family’s investments like an allotment. Harvest smarter wealth.*

AllotMint is a private, server-less web app that turns real-world family investing into a visually engaging “allotment” you tend over time.  
It enforces strict compliance rules (30-day minimum holding, 20 trades / person / month), runs entirely on AWS S3 + Lambda, and keeps your AWS and Python skills sharp.

---

## MVP Scope
1. **Portfolio Viewer** – individual / adults / whole family.
2. **Compliance Engine** – 30-day sell lock & monthly trade counter.
3. **Stock Screener v1** – PEG < 1, P/E < 20, low D/E, positive FCF.
4. **Scenario Tester (Lite)** – single-asset price shocks.
5. **Lucy DB Pension Forecast** – inflation-linked income overlay.

---

## Tech Stack
| Layer      | Choice                      |
|------------|----------------------------|
| Frontend   | React + TypeScript → S3 + CloudFront |
| Backend    | AWS Lambda (Python 3.12) behind API Gateway |
| Storage    | S3 JSON / CSV (no RDBMS)   |
| IaC        | AWS CDK (Py)               |

---

## Local Quick-start
```bash
# clone & enter
git clone git@github.com:leonarduk/allotmint.git
cd allotmint

# set up Python venv for CDK & backend (optional)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # requirements file TBD

# install React deps later:
# cd frontend && npm install
