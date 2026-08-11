# Decision: portfolio consolidation architecture (#6365)

Status: **Accepted** — resolves the design spike in
[#6376](https://github.com/leonarduk/allotmint/issues/6376).
Scope: binding on every child task of
[#6365](https://github.com/leonarduk/allotmint/issues/6365)
("Consolidate group overview (`/`) and per-owner portfolio (`/portfolio/:owner`)
into one scoped view").

Child tasks must cite this document by section number rather than re-deciding
any of it. If a child task believes a decision here is wrong, it should say so
in a comment on #6365 and get this document amended — not diverge silently.

Resolved follow-up clarifications:

- [#6385](https://github.com/leonarduk/allotmint/issues/6385): §3 defines the
  strict tri-state rendering contract for `sell_eligible`, including the
  distinct `null`, `true`, and `false` outputs.
- [#6386](https://github.com/leonarduk/allotmint/issues/6386): §1 defines the
  permanent redirect that removes an `account` query parameter when `owner`
  is absent.

---

## 0. Findings that changed the framing

Two premises in #6365/#6376 turned out to be inaccurate once the backend was
read. Both matter, because the decisions below depend on them.

**Finding A — group-level holdings are *not* impoverished per-owner holdings.**
`build_group_portfolio` enriches every merged holding with the *same*
`enrich_holding(...)` call the single-owner builder uses, passing that owner's
own approvals and user config
(`backend/common/group_portfolio.py:167` vs `backend/common/portfolio.py:169`).
Each merged account is also stamped with its `owner`
(`backend/common/group_portfolio.py:162`). So a `Holding` obtained via
`getGroupPortfolio` already carries `acquired_date`, `days_held`,
`sell_eligible`, `days_until_eligible` and `next_eligible_sell_date`, correctly
computed per owner.

The consequence: the incompatibility is **rollup-vs-lot**, not
**group-vs-owner**. For the table-row data used by this decision,
`getGroupPortfolio` contains the enriched holdings returned by
`getPortfolio(owner)` for every owner in the group. The endpoint envelopes are
not literal supersets: the owner endpoint returns `trades_this_month` and
`trades_remaining` at its top level, while the group endpoint carries those
values per owner in `members_summary`
(`backend/common/group_portfolio.py:201-245`).

**Code verification (2026-08-11; follow-up #6384).** This claim was traced
through both builders before the consolidation child tasks started. The group
builder loads approvals and user config into owner-keyed maps
(`backend/common/group_portfolio.py:139-151`) and passes the entries for the
account's owner to the same `enrich_holding` function used by the owner builder
(`backend/common/group_portfolio.py:157-176` vs
`backend/common/portfolio.py:160-176`). `enrich_holding` preserves the input
`acquired_date` (and supplies a default for a positive non-cash holding that
lacks one), then derives `days_held` and `sell_eligible`
(`backend/common/holding_utils.py:505-555`), so those values remain attached to
each holding inside its owner-stamped account. As in the owner response, an
acquisition date and `days_held` can be null for cash, zero-unit, or
unparseable-date holdings. The group builder obtains each
member's trade counts from `build_owner_portfolio` and copies them into that
member's `members_summary` entry, with a per-owner fallback when owner details
cannot be loaded (`backend/common/group_portfolio.py:201-245`). No discrepancy
was found in the per-owner fields on which §§2-3 depend; the wording above is
limited to table-row data to avoid implying that the two endpoint envelopes
are identical.

**Finding B — `InstrumentSummary` cannot be produced on the client.**
`/portfolio-group/{slug}/instruments` is literally
`aggregate_by_ticker(filtered_group_portfolio)`
(`backend/routes/portfolio.py:722`), and that function resolves full tickers
against the price snapshot, joins instrument metadata to derive `grouping`, and
fills `change_7d_pct`/`change_30d_pct` from the snapshot
(`backend/common/portfolio_utils.py:596-825`). None of those inputs exist in
the browser. A client-side `reduce` over `Holding[]` can reproduce the *sums*
but not `grouping`, `exchange`, `change_7d_pct` or `change_30d_pct`.

That endpoint **already accepts `owner` and `account_type` filters
server-side** (`backend/routes/portfolio.py:676-722`), and the frontend already
passes them (`frontend/src/components/GroupPortfolioView.tsx:366-368`).

---

## 1. Scope-selector UX — two-tier tabs, driven by URL query params

**Decision.** Keep the two-tier tab strip that `GroupPortfolioView` already
renders, and make it URL-driven.

- Row 1: `All family` | one tab per owner. (`GroupPortfolioView.tsx:1178-1211`)
- Row 2: appears only when an owner is selected — `All accounts` | one tab per
  account type for that owner. (`GroupPortfolioView.tsx:1213-1265`)
- Position: directly above the table, below the family-level charts/aggregates,
  so the charts stay the page header and the tabs read as "what the table below
  is showing".

**URL contract.**

| URL | Scope |
| --- | --- |
| `/` | All family |
| `/?account=isa` (no `owner`) | All family; permanently redirect (301) to `/` |
| `/?owner=steve` | Single owner, all accounts |
| `/?owner=steve&account=isa` | Single owner + single account type |

`owner` absent ⇒ family scope. When `account` is present without `owner`, it
is ignored for scope selection **and removed from the URL with a 301 permanent
redirect** (`/?account=isa` → `/`). This cleanup prevents stale, ineffective
parameters from remaining in browser history, bookmarks, or shared links.
An `owner`/`account` value that does not exist in the loaded group falls back to
the next-widest valid scope and rewrites the URL (`GroupPortfolioView.tsx:348-364`
already implements this reconciliation against local state; it moves to the
query param).

**Why tabs, not a dropdown.** The tab strip already exists, already carries
`role="tab"`/`aria-selected`, and the option count is bounded and small
(4 owners × ~4 account types). A dropdown would hide the current scope behind a
click and make owner-to-owner comparison a two-interaction operation. Tabs also
degrade cleanly: the second row simply does not render at family scope.

**Consequence for #6365 step 5.** `/portfolio/:owner` redirects to
`/?owner=:owner` (301-equivalent client redirect in `frontend/src/routes/registry.ts:96-102`).
The old route keeps working; no bookmark breaks.

---

## 2. Data-fetch consolidation — `getGroupPortfolio` is the canonical row source

**Decision.** `getGroupPortfolio(slug, { asOf })` is the single source of truth
for table rows at every scope. Owner and account scoping are **client-side
filters** over its `accounts[]`. `getPortfolio` is removed from this page.

`getGroupInstruments` is **retained but demoted**: it is no longer a competing
row source, it is a per-ticker *enrichment/aggregate* source, fetched only when
the rollup display mode (§3) is active, using the same `owner`/`account_type`
params as the current scope.

Concretely:

```
getGroupPortfolio(slug, {asOf})          -> fetched ONCE per (slug, asOf)
                                            cached; NOT refetched on scope change
  └─ accounts[].holdings[]  ............... every row the table ever renders
     filtered client-side by account.owner / account.account_type

getGroupInstruments(slug, {owner, account_type}, {asOf})
                                          -> fetched per scope, ONLY in rollup mode
  └─ joined onto rolled-up rows by ticker for grouping / exchange /
     change_7d_pct / change_30d_pct
```

**Why this direction.** Finding A means the family payload already contains
every field the per-owner page renders, so per-owner `getPortfolio` calls are
redundant network work. Finding B means the reverse consolidation — make
`getGroupInstruments` canonical and derive lots from it — is impossible, since
per-lot rows cannot be recovered from a ticker rollup.

**Why `getGroupInstruments` is not simply deleted.** Its four exclusive fields
require server-side data (price snapshot, instrument metadata, group
definitions). Reimplementing that client-side is out of scope and would be a
second aggregation layer — exactly what #6365 sets out to eliminate.

**Not in scope.** `getPortfolio` stays as-is for `pages/Rebalance.tsx`,
`pages/TaxTools.tsx`, `pages/ScenarioTester.tsx` and `pages/Portfolio.tsx`.
This decision is about the consolidated view only.

---

## 3. Row-shape reconciliation — two row types, mapping goes lot → rollup

**Decision.** The shared table renders **two distinct row types**, chosen by a
display-mode toggle, not one coerced type. The mapping direction is
`Holding[] → RollupRow`. Do **not** map `InstrumentSummary → Holding`.

```ts
// Flat mode — one row per lot. Default at every scope.
type ScopedHoldingRow = Holding & {
  owner: string;           // from account.owner
  source_account: string;  // from account.account_type
  row_key: string;         // `${owner}:${account_type}:${ticker}:${index}`
};

// Rollup mode — one row per ticker across the current scope.
type RollupRow = {
  ticker: string;
  name: string;
  // summed across the lots in scope:
  units: number;
  cost_basis_gbp: number;
  market_value_gbp: number;
  gain_gbp: number;
  gain_pct: number;        // RECOMPUTED as gain_gbp / cost_basis_gbp — never averaged
  weight_pct: number;      // recomputed against the scoped total, not the family total
  // provenance, replaces the per-lot owner/account columns:
  lot_count: number;
  owners: string[];
  accounts: string[];
  // joined from InstrumentSummary by ticker; null when unmatched:
  grouping: string | null;
  exchange: string | null;
  change_7d_pct: number | null;
  change_30d_pct: number | null;
  // structurally absent at rollup level — ALWAYS null, never fabricated:
  acquired_date: null;
  days_held: null;
  sell_eligible: null;
  days_until_eligible: null;
  next_eligible_sell_date: null;
};
```

**Rules for the always-null fields.**

1. Render as `—`, never as `No`, `0`, or an empty cell. In particular,
   `sell_eligible` is tri-state across the two row types, so its cell renderer
   must test `value === null` **before** rendering the existing enabled or
   disabled state. Do not use a truthiness check that collapses `null` into
   `false`. This preserves the existing flat-mode rendering while making the
   rollup-only, not-applicable state explicit:

   | `sell_eligible` value | Meaning | Cell output |
   | --- | --- | --- |
   | `null` | Not applicable to a rollup row | `—` |
   | `true` | The lot is sell eligible | Existing `Yes`/enabled state |
   | `false` | The lot is not sell eligible | Existing `No`/disabled state |
2. The **sell-eligible quick filter is disabled** in rollup mode
   (`HoldingsTable.tsx:286-292`) rather than filtering on a fabricated value.
   Sorting by any of these columns is likewise disabled in rollup mode.
3. If a future task needs "is any lot of this ticker sellable", that is a *new*
   derived field (`any_lot_sell_eligible`), not a reinterpretation of
   `sell_eligible`. Do not overload the existing field.

**Do not conflate these two similarly-named fields.** `Holding.forward_7d_change_pct`
is a per-lot forward-looking value from `holding_utils`
(`backend/common/holding_utils.py:560-604`); `InstrumentSummary.change_7d_pct`
is a trailing snapshot value. They are different measurements — keep distinct
column headers and do not map one onto the other.

**Consistency with §2.** The rollup is computed from the canonical `Holding[]`
(so the sums always agree with the flat view at the same scope) and only the
four unreachable fields come from `getGroupInstruments`. If the join misses a
ticker, those four render `—`; the row still shows correct money.

---

## 4. Group-assignment feature — stays on `/instrument/:group`, presentation ported

**Decision.** Split `InstrumentTable`'s two responsibilities and route them
differently:

- **Grouped presentation is ported** into the merged table: `createGroups`,
  expandable group rows, `calculateGroupTotals`, the flat/group/category mode
  switch — all from `frontend/src/components/instrumentTable/utils.ts` and
  `useInstrumentTableState`. This is what makes rollup mode (§3) equal to
  today's family view; #6365's "must not regress the family view" constraint
  depends on it.
- **Group *mutation* UI is not ported.** `assignInstrumentGroup`,
  `createInstrumentGroup`, `clearInstrumentGroup` and their
  `pendingGroupTicker`/`groupOverrides` state
  (`InstrumentTable.tsx:12-18, 44-66`) stay on the existing
  `/instrument/:group` route, which keeps rendering `InstrumentTable` unchanged.

**Why.** §1 chose a scope selector plus a display-mode toggle rather than
retaining a separate grouped page as the family view — so the merged page needs
grouping as a *view*, not as an *editor*. Assigning a ticker to a group is data
administration affecting every user of the instrument, not a portfolio-viewing
action, and `/` is the default landing page; putting a write path there is a
regression in blast radius, not an improvement.

**Follow-up (not part of #6365).** The natural long-term home for group
assignment is the `InstrumentDetail` drawer, where exactly one ticker is in
focus and the write is unambiguous. File that as a separate issue after #6365
lands; do not fold it into a consolidation child task.

---

## 5. `familyMvpEnabled` — gates the controls, never the scope selector

**Decision.** `familyMvpEnabled` keeps its current meaning ("hide advanced
controls") and gains no new responsibilities. Specifically:

| Element | `familyMvpEnabled = true` | `= false` |
| --- | --- | --- |
| Scope selector (§1, both tab rows) | **visible** | visible |
| Display-mode toggle (flat / rollup, §3) | **hidden, forced to flat** | visible |
| `FilterBar`, quick filters, column toggles, spark-range | hidden (unchanged, `HoldingsTable.tsx:252`) | visible |
| Family-level charts/aggregates | unchanged from today's `GroupPortfolioView` | unchanged |

**Why the scope selector is never gated.** "Show me just Steve's ISA" is the
core family-MVP interaction — it is the thing family mode exists to make easy.
Gating it would leave family-mode users with a single undifferentiated family
total and no drill-down, which is worse than today.

**Why the display-mode toggle is gated.** Flat-vs-rollup is a power-user
distinction of the same kind as column visibility, and rollup mode is where the
`—` placeholder columns of §3 appear. Family mode should not surface columns
that are structurally blank.

**Implementation constraint.** Do not introduce a new gating primitive or
per-scope gating. Reuse the existing single `!familyMvpEnabled && (...)` block
in `HoldingsTable.tsx:252` and add exactly one more around the display-mode
toggle in the merged view. No child task should add a third gating mechanism.

---

## Mapping to #6376 success criteria

| # | Criterion | Section |
| --- | --- | --- |
| 1 | Scope-selector form decided | §1 — two-tier tabs, URL query params |
| 2 | Data-fetch direction decided | §2 — `getGroupPortfolio` canonical; `getGroupInstruments` demoted to rollup enrichment |
| 3 | Row-shape reconciliation rule | §3 — two row types, `Holding[] → RollupRow`, five always-null fields with render/filter rules |
| 4 | Group-assignment fate | §4 — presentation ported, mutation UI stays on `/instrument/:group`, drawer as follow-up |
| 5 | `familyMvpEnabled` interaction | §5 — gates the display-mode toggle, never the scope selector |

Internal consistency: §3's mapping direction follows from §2's choice of
canonical fetch path; §4 and §5 both follow from §1's choice of tabs plus a
display-mode toggle rather than a separate grouped page.
