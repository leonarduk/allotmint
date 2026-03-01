# Onboarding Improvements TODO

Recommendations to make the codebase easier for new developers to pick up.

---

## High Priority

- [ ] **Add an architecture diagram** showing the portfolio data flow
  - `trades CSV → portfolio loader → group aggregator → API response → frontend cache`
  - A single diagram would replace hours of reading across 3–4 files
  - Add to `docs/README.md` or a new `docs/ARCHITECTURE.md`

- [ ] **Add a module docstring to `backend/common/portfolio_utils.py`**
  - Explain what the module does and what it doesn't do
  - Document key assumptions (e.g. how FX is handled, what "snapshot" means)
  - File is 1,740 lines with no high-level orientation

- [ ] **Split `frontend/src/App.tsx`** (715 lines)
  - Extract routing config from state management logic
  - Each concern becomes easier to reason about independently

---

## Medium Priority

- [ ] **Add a `CLAUDE.md`** at the repo root
  - Useful for AI-assisted workflows
  - Can mirror/extend `AGENTS.md` with project context

- [ ] **Document the compliance engine** (`backend/common/compliance.py`)
  - Explain the 30-day hold rule, monthly trade limits, and approval workflow
  - Non-obvious stateful logic that is risky to modify without context

- [ ] **Add a data flow comment block to `backend/auth.py`** (342 lines)
  - Clarify when each auth strategy applies: token vs Google OAuth vs demo fallback
  - Local vs production differences are easy to miss

---

## Low Priority

- [ ] **Break up `portfolio_utils.py`** into smaller focused modules
  - Candidates: VaR calculations, FX conversions, aggregation logic
  - Would improve testability and discoverability

- [ ] **Add architecture decision records (ADRs)** for key choices
  - Why S3 + JSON instead of a relational DB
  - Why Mangum/Lambda over a persistent server
  - Why React Context over Redux/Zustand

- [ ] **Add a route map comment to `backend/app.py`**
  - 25+ routers registered — a quick index would help navigation
