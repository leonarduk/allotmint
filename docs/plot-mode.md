# Plot mode (the gamified skin)

Plot mode is an optional, arcade-style skin over the data the conventional
AllotMint UI already shows. It lives at `/plot` and is **additive**: every
classic screen keeps working exactly as before, and nothing in Plot mode
places a trade or writes portfolio data.

The theme is horticultural — an allotment rather than a spaceport. A holding
is a _crop_, an account is a _bed_, and the daily Trail tasks are _chores_.

## Screens

- **`/plot` — The Plot (hub).** Best and worst crop on the stage, the three
  resource meters, open chores, beds and biggest crops.
- **`/plot/crops` — Crop roster.** Every holding as a card, sortable by plot
  share / growth / vigour / name and filterable by bed.
- **`/plot/crops/:ticker` — Crop detail.** One holding's traits, portrait and
  ledger, with a link out to the classic instrument view.
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

- **Crop** — one card per `Holding` from `GET /portfolio/{owner}`.
- **Bed** — one per `Account` in the same response; the account type gives
  the bed its name and icon.
- **Growth stage** — from `gain_pct`: wilting ≤ −20%, sown ≤ 0%,
  sprouting ≤ 5%, leafing ≤ 15%, budding ≤ 30%, flowering ≤ 60%,
  fruiting ≤ 120%, bumper crop above that.
- **Stars (1–7)** — from share of total plot value: 7★ at ≥ 20%, then
  12%, 7%, 4%, 2%, 1%, and 1★ below.
- **Vigour (0–100)** — today's move (`day_change_gbp`) mapped from ±5% onto
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
- **Seed packets** — the `watchlistSymbols` localStorage key (the same list
  the classic Watchlist page reads) priced via `GET /api/quotes`.
- **Propagator** — holdings still inside their minimum holding period, from
  the backend's own `sell_eligible`, `days_until_eligible` and
  `next_eligible_sell_date` (derived from the configured `hold_days_min`).
  Progress runs `days_held` over `days_held + days_until_eligible`.
- **Streak path** — the last seven days from the Trail's `daily_totals`,
  anchored on its `today`. A day is stamped only when every daily chore was
  finished; a day the backend has no record for stays blank rather than being
  reconstructed.
- **Season** — the UK tax year from the allowances API's `tax_year`
  (`"YYYY-YYYY"`, ending 5 April of the second year). Milestone tiers are
  driven by crop count, plot value, allowance usage, streak and grower level;
  a cleared tier shows the real current figure, not the target it beat.
- **Favourite stars** — this browser's own marks, kept in `localStorage`
  under `allotmint:plot:favourites:<owner>`. They never reach the backend.

Chores write back through the same `POST /trail/{id}/complete` (or
`POST /quests/{id}/complete`) endpoints the classic Trail page uses, so XP and
streaks are shared between the two skins rather than tracked separately.

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
  renders it. Colour comes from `currentColor` and the fill from a rect
  clipped to the silhouette, so a single component reports both the crop's
  flavour and its growth stage — one path reused from an 18px legend chip up
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
