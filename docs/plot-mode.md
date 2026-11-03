# Plot mode (the gamified skin)

Plot mode is an optional, arcade-style skin over the data the conventional
AllotMint UI already shows. It lives at `/plot` and is **additive**: every
classic screen keeps working exactly as before, and nothing in Plot mode
places a trade or writes portfolio data.

The theme is horticultural — an allotment rather than a spaceport. A holding
is a _crop_, an account is a _bed_, and the daily Trail tasks are _chores_.

## Screens

- **`/plot` — The Plot (hub).** Best and worst crop on the stage, one
  "next job on the plot", the three resource meters, open chores, beds and
  biggest crops. "Biggest crops"
  shows one card per instrument: a ticker held in several beds is summed
  and labelled "in N beds".
- **`/plot/crops` — Crop roster.** Every holding as a card, sortable by plot
  share / growth / today's move / name and filterable by bed.
- **`/plot/crops/:cropId` — Crop detail.** `:cropId` is the per-holding id
  (`<bedIndex>-<holdingIndex>-<ticker>`, e.g. `0-3-HFEL.L`); a bare ticker still resolves, to the first
  holding of it. One holding's traits, portrait and
  ledger, a plain-English "What is this?" note on its instrument type,
  sector and region, and a link out to the classic instrument view.
- **`/plot/chores` — Chores.** Daily and one-off tasks, the completion ring,
  season XP and streak.
- **`/plot/season` — Season track.** A tiered milestone ladder over the UK
  tax year, with the countdown to 5 April.
- **`/plot/seeds` — Seed shed.** The watchlist as seed packets, priced from
  live quotes.

## Where the numbers come from

Nothing in Plot mode is invented; every figure traces back to an existing
endpoint. The mapping lives in `frontend/src/gamified/plotModel.ts` and is
unit tested in `frontend/tests/unit/gamified/plotModel.test.ts`.

- **Crop** — one card per non-cash `Holding` from `GET /portfolio/{owner}`.
- **Seed store** — cash holdings (`instrument_type` "Cash", the same
  `isCashInstrument` rule the classic summary uses) are not crops: they are
  summed into a "ready to sow" tile on the hub, still count toward plot
  value, and stay out of crop counts, shares and the Sunlight meter.
- **Bed** — one per `Account` in the same response; the account type gives
  the bed its name and icon, and a one-sentence explanation of its tax
  wrapper (ISA, SIPP, GIA…). The bed card's gain is the sum of its crops'
  `gain_gbp` over their summed cost, and "unknown" if any crop's cost basis
  is (#8471).
- **Next job on the plot** — `plotGuidance.ts` (#7209) checks, in order:
  stale portfolio prices (same rule as the stage, links to
  `/data-quality`), holdings waiting on sale approval (`/trade-compliance`),
  open chores, unused ISA allowance from `/tax/allowances`
  (`/tax-tools`), cash of 5%+ of plot value (`/allocation`), and an
  instrument held in more than one bed (its crop). The hub shows the first
  that applies, or "nothing needs doing". Every line is a fact with a link;
  none is a buy or sell suggestion.
- **Growth stage (maturity)** — from `days_held`, so it only ever moves
  forward while a holding is kept (#7200): sown < 30 days, sprouting < 90,
  leafing < 180, budding < 365, flowering < 730, fruiting < 1825,
  established from 1825 days (5 years). `days_held: null` is "Age unknown",
  never "Sown". The detail screen's Time held level reads the same ladder.
- **Condition (performance)** — from `gain_pct`, and allowed to go both
  ways: wilting ≤ −20%, struggling < 0%, healthy < 20%, thriving from 20%.
  An unknown cost basis is "Condition unknown". Condition sets the crop's
  colour; stage sets how full the glyph is.
- **Share of plot** — each crop's share of total plot value, shown as a
  "N% of plot" chip over a proportional bar (and as the Share of plot bar on
  the crop detail screen). It is position size, not a quality rating, so it
  is deliberately not drawn as stars; ★ only ever marks a favourite.
- **Today's move (0–100, `vigour` in code)** — today's move (`day_change_gbp`) mapped from ±5% onto
  the bar, minus 30 when `is_stale` is set.
- **Water meter** — `trades_remaining` out of `trades_this_month` plus
  `trades_remaining`: trades left this month.
- **Feed meter** — unused tax-allowance headroom from `GET /tax/allowances`.
- **Sunlight meter** — share of crops not flagged `is_stale`, i.e. priced
  from fresh data.
- **Grower level and XP** — `GET /trail`, falling back to
  `GET /quests/today`. Cumulative XP to reach level _L_ is
  `25 × L × (L − 1)`, so L2 is 50 XP, L3 is 150 and L4 is 300.
- **Streak** — from the same endpoint: consecutive days with every daily
  chore finished.
- **Seed packets** — the active watchlist (the same list the classic
  Watchlist page shows, from `frontend/src/lib/watchlistStore.ts`, cached in
  localStorage and saved per user via `GET`/`PUT /watchlists`) priced via
  `GET /api/quotes`.
- **Holding period (the hub panel; `Propagator` in code)** — holdings still inside their minimum holding period, from
  the backend's own `sell_eligible`, `days_until_eligible` and
  `next_eligible_sell_date` (derived from the configured `hold_days_min`).
  Progress runs `days_held` over `days_held + days_until_eligible`.
- **Streak path** — the last seven days from the Trail's `daily_totals`,
  anchored on its `today`. A day is stamped only when every daily chore was
  finished; a day the backend has no record for stays blank rather than being
  reconstructed.
- **Season** — the UK tax year from the allowances API's `tax_year`
  (`"YYYY-YYYY"`, ending 5 April of the second year). Milestone tiers are
  driven by crop count (distinct instruments, not holding rows), plot value, allowance usage, streak and grower level;
  a cleared tier shows the real current figure, not the target it beat.
- **Favourite stars** — this browser's own marks, kept in `localStorage`
  under `allotmint:plot:favourites:<owner>`. They never reach the backend.

Chores write back through the same `POST /trail/{id}/complete` (or
`POST /quests/{id}/complete`) endpoints the classic Trail page uses, so XP and
streaks are shared between the two skins rather than tracked separately.

## User guide, glossary and first-run walkthrough

Users read about Plot mode in the app, not here (#7210):

- **Glossary** — the "Plot garden terms" section of `/metrics-explained`
  (anchor `#plot-guide`), linked from the **Guide** entry on the Plot rail.
  Every term has its own anchor and names the real figure behind it. The
  hand-written entries there cover beds, growth stages, condition, the
  holding period and the meters; everything else comes from
  `frontend/src/lib/plotGlossary.ts`, which also feeds the in-app InfoTips
  (`components/GlossaryTip.tsx`), so a tip and its glossary entry can't
  disagree.
- **First-run walkthrough** — `components/PlotWelcome.tsx`, an inline,
  dismissible panel at the top of the hub. Dismissal is remembered per
  browser in `localStorage` (`allotmint:plotWelcomeDismissed`); it never
  blocks the hub.
- **Vocabulary rule** — a garden word is kept only where it carries
  structure (plot = portfolio, bed = account, crop = holding, chores, the
  water/feed/sunlight meters, growth stage and condition, the streak crate,
  season, grower rank). Words that only renamed a finance term were
  replaced with the real one: Propagator → Holding period, lift → sell,
  Root depth → Share of plot, Vigour → Today's move, Hardiness → Time held,
  Groundwork → One-off tasks. Code identifiers and i18n key names keep
  their old names to avoid churn; only the user-facing text changed.

## Switching between the skins

- Classic → Plot: the **Plot Mode** entry in the Dashboard menu category.
- Plot → classic: the **Classic view** button in the Plot HUD, which carries
  the currently selected grower across as `/?owner=<owner>`.

There is no automatic redirect: opening AllotMint always lands on the
conventional UI, and Plot mode is entered deliberately.

## Turning it off

`plot` is a normal config tab. Setting `tabs.plot: false` in `config.yaml`
(or adding `plot` to `disabled_tabs`) removes the menu entry and unmounts the
route, exactly like any other page.

## Implementation notes

- Everything lives under `frontend/src/gamified/`, and the styling is a single
  CSS module (`plot.module.css`) scoped to `.plotRoot`. No global styles are
  touched, so the classic light/dark themes are unaffected.
- `PlotApp` is lazy-loaded through the route registry, so users who never open
  Plot mode do not download it.
- `PlotDataProvider` fetches the portfolio, allowances and progress once and
  shares them across all five screens.
- Each crop is drawn, not emoji: `glyphShapes.ts` holds twelve species as
  SVG paths, `cropGlyph.ts` picks one deterministically from ticker + sector
  (same idea as the old emoji pools, same FNV-1a hash), and `<CropGlyph>`
  renders it. Colour comes from `currentColor` (the crop's condition) and
  the fill from a rect clipped to the silhouette (its growth stage), so a
  single component reports the crop's flavour, age and condition — one path reused from an 18px legend chip up
  to a 104px detail portrait. Twelve shapes are not enough to make the
  species an identifier (a real portfolio collides most of the time past a
  handful of holdings), so it is deliberately treated as flavour only; the
  ticker printed on every card is what identifies the crop.
- The skin is keyboard- and screen-reader navigable: meters are real
  `progressbar` elements with accessible names, crop glyphs and other
  decorative marks are `aria-hidden`, and ambient animation is disabled under
  `prefers-reduced-motion`. `tests/unit/gamified/PlotAccessibility.test.tsx`
  runs axe over the hub, chores, season and roster screens.
- Grid tracks use `minmax(0, 1fr)` and card grids `minmax(min(Npx, 100%),
1fr)`. A bare `1fr` carries `min-width: auto`, which let the widest card row
  push the whole layout past a phone viewport.

## Validation

```bash
npm --prefix frontend run test -- --run tests/unit/gamified
npm --prefix frontend run lint
python -m pytest tests/backend/test_tabs_config.py
```
