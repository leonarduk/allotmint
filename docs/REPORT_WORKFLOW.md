# Report Workflow

This workflow documents the exact end-to-end path for producing a customer-facing `audit-report` PDF from a clean checkout.

## 1) Start from a clean checkout

Install dependencies (first run or after dependency changes):

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
```

Bring up the local stack:

```bash
make local-up
```

The API is available at `http://localhost:8000` once containers are healthy.

## 2) Confirm the customer scope

Collect:
- owner identifier (for example, `demo-owner`)
- ticker/portfolio context to review

## 3) Create or update key findings

`audit-report` expects manually written findings at:

```text
data/accounts/{owner}/key_findings.md
```

Example setup for demo generation from a clean checkout:

```bash
mkdir -p data/accounts/demo-owner
cat > data/accounts/demo-owner/key_findings.md << 'EOF2'
- Global equity exposure is 71.4% of portfolio value, above the 65.0% policy target.
- Largest position concentration is 12.1% in a single issuer versus a 10.0% guardrail.
- 1-day 95% VaR is £1,240 on a £42,800 portfolio, implying a 2.9% downside move.
- Cash drag is 9.8% of assets while short-duration bonds yield 4.2%.
EOF2
```

Writing guidance:
- Findings are **not auto-generated**.
- Use one bullet per finding with concrete numbers.
- Keep each finding short and specific (recommended 20-240 chars).
- Invalid lines are skipped with warnings instead of failing report generation.

## 4) Generate and download the PDF

Use the report route directly:

```bash
curl -sS "http://localhost:8000/reports/demo-owner/audit-report?format=pdf&watermark=SAMPLE" -o demo-owner-audit-report.pdf
```

Optional JSON preview of section payloads:

```bash
curl -sS "http://localhost:8000/reports/demo-owner/audit-report?format=json" | jq '.sections[].title'
```

Expected section order for a complete demo report:
1. Portfolio Summary
2. Holdings Breakdown
3. Sector Allocation
4. Risk Analysis
5. Key Findings

## 5) Validate report quality before sending

Minimum checks:
- PDF opens and all five sections render (including Key Findings).
- Currency and percentages are formatted for end users (no raw floats/internal IDs).
- Narrative answers: total value, top risk, and recommended action are clear.
- Product gate: "Would I confidently send this to a prospect?" must be **yes**.

## 6) Operational handoff

If needed, attach the generated PDF to your normal reporting channel/email flow.

When done with local containers:

```bash
make local-down
```
