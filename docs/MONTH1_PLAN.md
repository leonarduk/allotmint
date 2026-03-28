# AllotMint — Month 1 Execution Plan

> Last updated: March 2026  
> Goal: have a working, presentable audit report PDF and a paying customer by end of Week 4.

---

## The single constraint

**Do not open the IDE for anything not on this list.**  
Every hour spent on code quality, infra, or features not listed below is an hour not spent getting to first revenue. The codebase is complete enough. The bottleneck is the report pipeline and sales.

---

## Code prerequisites (in order)

These are the only things that need to be built before you can sell a report. Everything else is out of scope until you have a paying customer.

### 1. Merge PR #2572 — VaR fix *(today, ~1 hour)*

The VaR calculation has known bugs for cash and scaled prices. This is already written. Review and merge it.  
**Blocked by:** nothing.  
**Blocks:** issue #2578 (VaR section in report).

### 2. Issue #2578 — Wire sector/region/VaR/concentration into report pipeline *(Days 1–2, ~1.5 days)*

The audit report sections described in the business plan do not exist yet in `SECTION_BUILDERS`. This is the core engineering gap.

New section sources needed:
- `portfolio.overview` — total value, holdings count, account summary
- `portfolio.sectors` — sector breakdown
- `portfolio.regions` — geographic breakdown
- `portfolio.concentration` — top 10 holdings, HHI concentration metric
- `portfolio.var` — VaR 95%/99%, Sharpe ratio

New built-in template: `audit-report` composing sections 1–4.  
**Blocked by:** #2572 merged (for VaR section).  
**Blocks:** #2581 (end-to-end test).

### 3. Issue #2579 — PDF formatting *(Day 3, ~0.5 days)*

Current PDF is pipe-delimited monospace. Minimum bar for a customer-facing document:
- Title page with owner name and date
- Section headers with ruled lines
- £ currency formatting and % for ratios
- Aligned table columns, alternating row shading
- Page footer with page numbers
- `watermark="SAMPLE"` parameter for demo reports

**Blocked by:** nothing (can be done in parallel with #2578).  
**Blocks:** #2581 (the test checks formatting).

### 4. Issue #2580 — Key Findings section *(Day 3–4, ~0.5 days)*

Add `portfolio.key_findings` section builder that reads `data/accounts/{owner}/key_findings.md` and renders it as numbered paragraphs in the PDF. This is the section that justifies the £39 price — it must look like it was written for the reader, not generated from a template.

**Blocked by:** #2579 (PDF formatting must be in place first).  
**Blocks:** #2581.

### 5. Issue #2581 — End-to-end manual test against real data *(Day 4–5, ~0.5 days)*

Run the full pipeline locally against your own portfolio data and verify:
- Portfolio value within 5% of broker statements
- VaR between 0.3–3% of portfolio value
- PDF opens, all sections present, numbers correct, formatting presentable
- Demo report generated with SAMPLE watermark
- Honest answer to: "Would I pay £39 for this?"

**Blocked by:** #2578, #2579, #2580.  
**Blocks:** everything in Week 2 onwards.

---

## Week-by-week plan

### Week 1 — Code sprint + market research (parallel)

**Code (Days 1–5):** Complete issues #2572, #2578, #2579, #2580, #2581 in order. Target: demo PDF exists by end of Friday.

**Market research (every day, 1–2 hours):** These do not require the code to be working.
- Read r/UKPersonalFinance, r/FIREUK, r/UKInvesting. Do not post. Make a list of 15 specific people who have publicly described multi-account portfolio tracking pain in the last 3 months.
- Write your positioning statement: "I help [specific user] achieve [specific outcome] without [specific pain]."
- Set up Stripe payment links for £39 and £79.
- Draft the DM you will send to your 15 prospects (use scripts from the business plan Section 6.2).

**Week 1 exit criteria:**
- [ ] Demo PDF exists and passes the £39 test
- [ ] 15 prospects identified
- [ ] Positioning statement written
- [ ] Stripe links live
- [ ] DM draft ready

---

### Week 2 — First outreach + free report offers

**No new code unless a bug blocks report generation.**

- Send DMs to 10 of the 15 prospects offering a free portfolio analysis.
- Generate and send 3–5 free reports to people who respond. Use `make local-up` + hit the endpoint + email the PDF manually.
- Choose your target segment (Compliance professionals vs Multi-account families) based on who responds with the strongest pain.
- Post first Reddit content piece (see business plan Section 6, Post 1).

**Week 2 exit criteria:**
- [ ] 10 DMs sent
- [ ] At least 5 meaningful replies (not just "interesting")
- [ ] At least 3 free reports delivered
- [ ] Segment chosen
- [ ] Reddit post 1 published

**If fewer than 5 meaningful replies:** rewrite your DM and try a different community. Do not build anything.

---

### Week 3 — First paid report

**No new code.**

- Collect feedback on free reports. Iterate the Key Findings writing based on what people valued.
- Offer paid reports at £39 to anyone who expressed interest.
- Ask free report recipients for a referral.
- Post Reddit content piece 2.

**Week 3 exit criteria:**
- [ ] At least 1 paid report sold (£39)
- [ ] At least 1 testimonial collected
- [ ] Reddit post 2 published

**If 0 paid reports by end of Week 3:** do not continue as-is. Choose one: rewrite positioning, switch segment, or change offer shape (e.g. cheaper single-page exposure summary). Do not add features.

---

### Week 4 — Iterate and scale

**Minimal code only if:** per-report effort is > 60 minutes and you have paying customers. If so, automate one bottleneck step.

- Deliver paid reports. Collect testimonials.
- Refine Key Findings based on feedback. Which sections did people value? Which did they skip?
- Post Reddit content piece 3.
- Friday: bottleneck diagnosis (see below).

**Week 4 exit criteria:**
- [ ] £39–200 cumulative revenue
- [ ] 3–8 reports delivered
- [ ] Clear signal on which segment converts
- [ ] Bottleneck identified and actioned

---

## Weekly bottleneck diagnosis (every Friday)

Ask one question: what is the current bottleneck?

| Bottleneck | Symptoms | Action |
|---|---|---|
| No demand | Nobody responds; posts get no engagement | Rewrite positioning. Change segment. |
| No trust | People interested but won't share data | More public proof. Get testimonials. |
| No conversion | Want free report, won't pay | Reduce free scope. Change price point. |
| No retention | One-time buyers, no referrals | The report is a one-off need. Pivot shape. |

Track only these five metrics weekly:
1. Outreach DMs sent
2. Meaningful replies received
3. Explicit willingness-to-pay expressions
4. Reports sold (£ revenue)
5. Repeat/referral customers

---

## What not to build this month

- AWS deployment
- Customer-facing UI or CSV upload form
- Multi-tenant authentication
- Any feature not directly required to generate and email a PDF
- Anything in response to "it would be better if.." without a paying customer asking for it

---

## Issue tracker

| Issue | Title | Prerequisite for |
|---|---|---|
| PR #2572 | Fix VaR inputs for cash and scaled prices | #2578 |
| #2578 | Wire sector/region/VaR/concentration into report pipeline | #2581 |
| #2579 | Improve PDF report formatting | #2581 |
| #2580 | Add Key Findings section to audit report PDF | #2581 |
| #2581 | End-to-end manual test against real portfolio data | Week 2 outreach |
| #2576 | Remove personal email from config.yaml (PR open) | Repo stays public |
