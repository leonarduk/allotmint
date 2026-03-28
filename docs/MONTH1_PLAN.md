# AllotMint — Month 1 Execution Plan

> Last updated: March 2026  
> Goal: have a working, presentable audit report PDF and a paying customer by end of Week 4.

> **Note:** This is an internal engineering execution plan, not a product roadmap or investor document.
> Business strategy details (pricing, sales scripts, revenue targets) are kept out of this file
> as the repository is public.

---

## The single constraint

**Do not open the IDE for anything not on this list.**  
Every hour spent on code quality, infra, or features not listed below is an hour not spent getting to first revenue. The codebase is complete enough. The bottleneck is the report pipeline and sales.

---

## Code prerequisites (in order)

These are the only things that need to be built before you can deliver a report to a customer.
Everything else is out of scope until there is a paying customer.

### 1. Merge PR #2572 — VaR fix *(today, ~1 hour)*

The VaR calculation has known bugs for cash and scaled prices. This is already written. Review and merge it.  
**Blocked by:** nothing.  
**Blocks:** issue #2578 (VaR section in report).

### 2. Issue #2578 — Wire sector/region/VaR/concentration into report pipeline *(Days 1–2, ~1.5 days)*

The audit report sections do not exist yet in `SECTION_BUILDERS`. This is the core engineering gap.

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

Add `portfolio.key_findings` section builder that reads `data/accounts/{owner}/key_findings.md`
and renders it as numbered paragraphs in the PDF. This is the section that differentiates the
product — it must look like it was written for the reader, not generated from a template.

**Blocked by:** #2579 (PDF formatting must be in place first).  
**Blocks:** #2581.

### 5. Issue #2581 — End-to-end manual test against real data *(Day 4–5, ~0.5 days)*

Run the full pipeline locally against your own portfolio data and verify:
- Portfolio value is within a reasonable tolerance of broker statements
- VaR output is plausible for the actual portfolio composition (not NaN, not zero, not obviously wrong for the asset mix)
- PDF opens, all sections present, numbers match individual endpoint responses, formatting is presentable
- Demo report generated with SAMPLE watermark
- Honest answer to: "Would someone pay for this?"

**Blocked by:** #2578, #2579, #2580.  
**Blocks:** everything in Week 2 onwards.

---

## Week-by-week plan

### Week 1 — Code sprint + market research (parallel)

**Code (Days 1–5):** Complete issues #2572, #2578, #2579, #2580, #2581 in order.
Target: demo PDF exists by end of Friday.

**Market research (every day, 1–2 hours):** Does not require the code to be working.
- Read relevant investing and personal finance communities. Do not post yet. Identify people
  who have publicly described multi-account portfolio tracking pain.
- Write a positioning statement: who is helped, what outcome, what pain avoided.
- Set up a payment mechanism before Week 2.
- Draft outreach messages.

**Week 1 exit criteria:**
- [ ] Demo PDF exists and passes the quality test
- [ ] 15 prospects identified
- [ ] Positioning statement written
- [ ] Payment mechanism live
- [ ] Outreach draft ready

---

### Week 2 — First outreach + free report offers

**No new code unless a bug blocks report generation.**

- Send outreach messages to prospects offering a free portfolio analysis.
- Generate and send free reports to people who respond. Use `make local-up` + hit the endpoint + email the PDF manually.
- Choose your target segment based on who responds with the strongest expressed pain.
- Post first public content piece (data-driven, no product mention).

**Week 2 exit criteria:**
- [ ] At least 10 outreach messages sent
- [ ] At least 5 meaningful replies (not just "interesting")
- [ ] At least 3 free reports delivered
- [ ] Segment chosen
- [ ] Content piece 1 published

**If fewer than 5 meaningful replies:** rewrite your message and try a different channel. Do not build anything.

---

### Week 3 — First paid report

**No new code.**

- Collect feedback on free reports. Iterate the Key Findings writing based on what people valued.
- Offer paid reports to anyone who expressed interest.
- Ask free report recipients for a referral.
- Post content piece 2.

**Week 3 exit criteria:**
- [ ] At least 1 paid report sold
- [ ] At least 1 testimonial collected
- [ ] Content piece 2 published

**If 0 paid reports by end of Week 3:** do not continue as-is. Choose one: rewrite positioning,
switch segment, or change offer shape. Do not add features.

---

### Week 4 — Iterate and scale

**Minimal code only if:** per-report effort is > 60 minutes and there are paying customers.
If so, automate one specific bottleneck step.

- Deliver paid reports. Collect testimonials.
- Refine Key Findings based on feedback.
- Post content piece 3.
- Friday: bottleneck diagnosis (see below).

**Week 4 exit criteria:**
- [ ] Multiple reports delivered
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
1. Outreach messages sent
2. Meaningful replies received
3. Explicit willingness-to-pay expressions
4. Reports sold (revenue)
5. Repeat/referral customers

---

## What not to build this month

- AWS deployment
- Customer-facing UI or CSV upload form
- Multi-tenant authentication
- Any feature not directly required to generate and email a PDF
- Anything in response to "it would be better if.." without a paying customer asking for it

---

## Issue and PR tracker

| Ref | Type | Title | Prerequisite for |
|---|---|---|---|
| #2572 | PR | Fix VaR inputs for cash and scaled prices | #2578 |
| #2578 | Issue | Wire sector/region/VaR/concentration into report pipeline | #2581 |
| #2579 | Issue | Improve PDF report formatting | #2581 |
| #2580 | Issue | Add Key Findings section to audit report PDF | #2581 |
| #2581 | Issue | End-to-end manual test against real portfolio data | Week 2 outreach |
| #2576 | PR | Remove personal email from config.yaml | Repo stays public |
