# Decision: retain Watchlist, Movers, and Screener as separate workflows (#6517)

Status: **Accepted**.

This records the product decision requested by
[#6517](https://github.com/leonarduk/allotmint/issues/6517). Watchlist, Movers,
and Screener remain separate top-level destinations. They all render ticker
rows, but the similarity is presentational rather than a shared product
workflow. No consolidation follow-up issue is required.

## 1. Decision

Keep the existing routes and navigation entries:

| Route        | User intent                                                                           | Membership                                                          | Refresh/query model                                                         |
| ------------ | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `/watchlist` | Passively monitor a small, explicitly chosen set of instruments                       | A comma-separated list saved in browser storage                     | Live quotes fetched on entry and refreshed automatically or manually        |
| `/movers`    | Rank the strongest and weakest moves over a selected period                           | A named market list or the authenticated user's portfolio           | A bounded opportunities query, including signals and portfolio-aware values |
| `/screener`  | Discover instruments matching fundamental constraints, or run a saved reporting query | A named/custom universe for screening; owners/tickers for reporting | User-submitted filters; results remain stable until the next run            |

Do **not** represent Movers as a saved Screener filter or Watchlist as a pinned
Screener result. Retain each page's current API path and state model.

## 2. Rationale

The three pages answer different questions:

- **Watchlist:** “What is happening now to instruments I already chose?” Its
  defining behavior is a persistent, editable symbol set plus quote refresh.
- **Movers:** “What changed most in this universe during this period?” Its
  defining behavior is ranking, not filtering. The Portfolio option also
  calculates position-sensitive values, including percentage of portfolio and
  value change, that a market screener cannot infer.
- **Screener:** “Which instruments satisfy these constraints?” Its defining
  behavior is an explicit, repeatable query. The custom-query section is a
  reporting workflow over owners, dates, tickers, and metrics rather than a
  live-price list.

Moving all three behind Screener would make navigation superficially smaller,
but it would couple three different data contracts and lifecycles. A “saved
filter” cannot express Watchlist's refresh semantics or Movers' ranked,
period-relative and portfolio-aware results without becoming a second routing
and execution system inside Screener.

## 3. Product boundaries

Future work should preserve these boundaries:

1. **Watchlist owns monitoring state.** Its editable symbols and refresh
   preference remain browser-local. Adding a symbol from instrument research
   continues to update this list.
2. **Movers owns ranked change and signal presentation.** Its Portfolio option,
   portfolio percentage, value delta, minimum-weight control, and unauthenticated
   fallback remain first-class behavior.
3. **Screener owns discovery constraints and saved queries.** Fundamental
   criteria belong here; Movers' period ranking and Watchlist's polling do not.
4. **Shared presentation may still be extracted.** Reusable table primitives,
   formatting, loading/error states, and instrument links can be shared when
   that reduces duplication. Shared rendering must not force the pages onto a
   single endpoint or erase their distinct state and refresh contracts.
5. **Performance work remains local to the responsible data path.** In
   particular, opportunities/Movers latency should be addressed without making
   Screener or Watchlist depend on that endpoint.

## 4. Reconsideration triggers

Revisit this decision only when a shared backend contract can model all three
workflows without losing refresh semantics, ranking semantics, or Portfolio
columns, or when user research shows that the separate destinations cause
material navigation problems. A future consolidation proposal must include:

- migration behavior for existing `/watchlist`, `/movers`, and `/screener`
  links;
- preservation of the Portfolio option and portfolio-aware columns;
- a state model for browser-local symbols, saved queries, and mover periods;
- performance measurements demonstrating that consolidation does not regress
  any workflow; and
- focused implementation scope in a new issue.

Until one of these triggers is met, additions should follow the boundaries in
§3 rather than reopening the information-architecture question.
