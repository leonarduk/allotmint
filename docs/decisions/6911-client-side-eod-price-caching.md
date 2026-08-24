# Decision: client-side caching of end-of-day price data (#6911)

Status: **Proposed** — design for
[#6911](https://github.com/leonarduk/allotmint/issues/6911).
Scope: the client-side caching strategy for every price-derived read path
(instrument history, sparklines, portfolio valuation, movers, screener).

This document is the design of record for that work. Child tasks should cite it
by section number rather than re-deciding any of it. If a child task believes a
decision here is wrong, say so on #6911 and get this document amended — do not
diverge silently.

Related but distinct: `docs/performance-caching.md` covers *backend in-process*
caching of owner/account discovery (#2411). It does not overlap with this
document, which is about what the *browser* keeps and for how long.

---

## 0. Findings that frame the design

Four facts, established by reading the current code, drive everything below.

**Finding A — the data really is end-of-day, and it changes on a schedule.**
`_rolling_cache` clamps its window to `today - 1 day` because "we have close
prices only" (`backend/timeseries/cache.py:205-206`), and the `DailyPriceRefresh`
EventBridge rule fires once daily at 00:00 UTC
(`cdk/stacks/backend_lambda_stack.py:970-974`). Every price-derived response is
therefore a pure function of *(dataset version, query params)* and can change at
most once per day.

**Finding B — there is no HTTP caching at all.**
`grep -rn "Cache-Control\|ETag\|max-age\|If-None-Match\|304" backend/` returns
**zero** hits. `register_middleware` (`backend/bootstrap/middleware.py:43`)
installs CORS and rate limiting and nothing else. No response the backend emits
carries a freshness lifetime or a validator, so nothing can be reused or cheaply
revalidated.

**Finding C — the client caches that exist die on reload.**
There are exactly two, both process-memory:

| Cache | Location | Survives reload? |
|---|---|---|
| `Map<ticker, Map<days, InstrumentDetail>>` | `frontend/src/hooks/useInstrumentHistory.ts:7` | No |
| `groupInstrumentCache` (in-flight promise dedupe only) | `frontend/src/api.ts:607` | No |

The app has no `@tanstack/react-query` and no service worker
(`frontend/vite.config.ts:29` notes the PWA plugin was deliberately removed), so
`fetchJson` (`frontend/src/api.ts:364`) is the single un-cached chokepoint that
~60 exported API functions call.

**Finding D — a per-ticker fan-out is fighting the rate limiter.**
`HoldingsTable.tsx:150` and `GroupPortfolioView.tsx:543` call
`preloadInstrumentHistory(tickers, days)`, which issues **one HTTP request per
ticker** at concurrency 5 (`useInstrumentHistory.ts:92-116`). A 40-holding
portfolio is 40 requests for data that last changed yesterday. The strongest
evidence that this hurts is that 429 `Retry-After` backoff has been written
**twice, independently** — `useInstrumentHistory.ts:162-186` and
`api.ts:959-1010`. Both exist only to survive this fan-out.

Two aggravating details:

- `timeseries_for_ticker` returns `mini` (7/30/180-day slices) *in addition to*
  the full `prices` array (`backend/common/instrument_api.py:304-308`). Those
  217 rows are already present in the 365 returned — roughly **37% of the body
  is duplicated**, on every request.
- `rate_limit_per_minute` defaults to `6000` on the dataclass
  (`backend/config.py:117`) but the loader falls back to **`60`** when the key is
  absent from the config data (`backend/config.py:473`). A deployment whose YAML
  omits the key gets 60/min, which a 40-ticker fan-out can trip on its own.
  Out of scope here; filed as
  [#6918](https://github.com/leonarduk/allotmint/issues/6918).

---

## 1. The central invariant

> A price-derived response is immutable for the lifetime of a **cache epoch**.
> The epoch changes only when the underlying EOD dataset changes.

Every decision below follows from that single sentence. The design's job is to
(a) give the epoch a cheap, trustworthy representation, and (b) let each caching
layer key off it.

Three layers, in increasing order of effort and payoff:

```
Layer 1  HTTP validators        backend only, no FE change      ~free revalidation
Layer 2  Persistent client cache IndexedDB, keyed on epoch      survives reload
Layer 3  Batch + payload diet   collapses N+1 fan-out           fixes first paint
```

Layers 1 and 2 make the *second* visit fast. Layer 3 is the one that makes the
*first* visit fast; it is not optional garnish.

---

## 2. Layer 0 — the cache epoch (`GET /prices/version`)

Nothing today tells a client "the data changed". `_PRICE_SNAPSHOT_TS` exists in
process memory (`backend/common/portfolio_utils.py:325`) but is only surfaced by
`/prices/refresh`, which *performs* a full refresh as a side effect and is
exposed as both GET and POST (`backend/routes/portfolio.py:989,994`) — unusable
as a polling endpoint.

Add a new, cheap, side-effect-free endpoint:

```http
GET /prices/version
```
```json
{
  "epoch": "2026-05-16.9f2c1a4b7e03",
  "snapshot_ts": "2026-05-17T00:04:11Z",
  "next_refresh_utc": "2026-05-18T00:00:00Z"
}
```

### 2.1 The epoch must be content-derived

```python
def price_epoch(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    latest = max((v.get("last_price_date") or "" for v in snapshot.values()), default="")
    return f"{latest}.{digest}"
```

**This is the one decision most likely to be got wrong.** The obvious
implementation — return `_PRICE_SNAPSHOT_TS` — is broken: that timestamp is set
on every process start by `refresh_snapshot_in_memory()`
(`portfolio_utils.py:328-340`), so a Lambda cold start or a redeploy would mint
a new epoch and invalidate every client cache in the fleet without a single
price having changed. Under Lambda's concurrency model, two simultaneous
requests could even report different epochs.

Hashing the snapshot content makes the epoch stable across restarts, identical
across concurrent workers, and different if and only if the data differs.

The `latest` date prefix is cosmetic but valuable: it makes the epoch
human-readable in devtools and sorts naturally in logs.

### 2.2 Cost and caching of the endpoint itself

It reads already-in-memory state (`_PRICE_SNAPSHOT`) and hashes it. Memoise the
digest against the snapshot's identity so repeated calls are a dict lookup. The
endpoint itself must be served `Cache-Control: no-store` — it is the thing that
invalidates everything else and must never be cached.

---

## 3. Layer 1 — HTTP validators (backend only)

The highest value per line of code: it requires **no frontend change** and
benefits every existing `fetch` call immediately.

### 3.1 Headers

For price-derived GET routes:

```
Cache-Control: private, max-age=<min(seconds_to_next_refresh, 3600)>, stale-while-revalidate=604800, no-transform
ETag: W/"<epoch>:<route-key>"
Vary: Authorization, Accept-Encoding
```

`stale-while-revalidate` is what buys perceived speed: past `max-age` the
browser paints from cache **instantly** and revalidates in the background, so
the user never waits on the network for data that is almost certainly unchanged.

**The ETag must stay weak (`W/`), and that is deliberate — do not "fix" it to a
strong one.** A strong ETag asserts byte-for-byte identity, which stops holding
the moment the same payload is served under a different content-coding (gzip vs
identity vs br). A weak validator asserts only semantic equivalence, which is
exactly the claim being made here: the epoch is unchanged, therefore the data is
unchanged, whatever the transfer encoding. `no-transform` closes the same gap
from the other side by telling intermediaries not to re-encode the body
underneath the validator.

### 3.2 Why `max-age` is capped at an hour rather than "until midnight"

The tempting choice is `max-age = seconds until 00:00 UTC`. Reject it. A fresh
(non-stale) entry is not revalidated *at all* — the browser will not even ask.
The Support page can trigger an out-of-band refresh at any time
(`frontend/src/pages/Support.tsx:237` → `POST /prices/refresh`), so a
multi-hour `max-age` would leave users pinned to superseded prices with no
recovery path short of a hard reload.

Capping `max-age` at an hour and leaning on a week of
`stale-while-revalidate` gives instant paint *and* a revalidation opportunity at
least hourly. Revalidation is nearly free because of §3.3. Correctness does not
rest on the TTL — it rests on the epoch check in §4.3.

### 3.3 Conditional requests

Handle `If-None-Match` and return `304 Not Modified` with an empty body. Since
the ETag embeds the epoch, a matching request is answered without touching the
parquet layer at all: compare, return 304, done. This turns the daily
"has anything changed?" question into a few hundred bytes.

### 3.4 Privacy — the sharp edge

Portfolio responses are per-user and go out with `Authorization` plus
`credentials: "include"` (`frontend/src/api.ts:298`). Get this wrong and a
shared cache serves one household's holdings to another.

Rules, non-negotiable:

- **Never `public`** on any route carrying per-user data. `private` only.
- Always emit `Vary: Authorization`. Belt-and-braces alongside `private`, and
  the thing that saves you if API traffic is ever put behind CloudFront.
- Split the policy by data class rather than applying one blanket rule:

| Data class | Example routes | Policy |
|---|---|---|
| Per-user portfolio | `/portfolio/{owner}`, `/portfolio-group/{slug}` | `private`, epoch ETag |
| Market-wide, non-identifying | `/instrument/`, `/movers`, `/screener` | `private`, epoch ETag (see note) |
| Historical `as_of=` | any route with `as_of` | `private, max-age=604800, immutable` (§6.2) |
| Mutations, auth, `/prices/version` | `POST` routes, `/token` | `no-store` |

Note: market data is not user-specific and *could* be `public`, but these routes
are served by the same authenticated app and some (e.g. `/instrument/`) embed
`positions` for the calling user (`backend/routes/instrument.py:399,479`). Keeping
everything `private` costs nothing here — the win comes from the browser's own
cache, not a shared one — and removes a whole class of leak. Revisit only if a
genuinely anonymous market-data origin is introduced.

### 3.5 Implementation shape

A small ASGI middleware or a route decorator in
`backend/bootstrap/middleware.py`, driven by an explicit allowlist of
price-derived paths. Prefer an **allowlist over a denylist**: a new route that
accidentally inherits caching is a privacy incident, whereas one that
accidentally misses it is merely slow.

---

## 4. Layer 2 — persistent client cache (IndexedDB)

### 4.1 Why IndexedDB and not `localStorage`

Measured against the actual payload: a price row serialises to roughly 55 bytes
(`{"date":"2026-05-16","close":97.5,"close_gbp":97.5}`). At 365 days that is
~20KB per ticker, plus ~12KB of duplicated `mini` — call it 32KB. **A single
40-holding portfolio is therefore ~1.3MB**, or about a quarter of
`localStorage`'s ~5MB budget, for one view at one range.

`localStorage` is also synchronous: parsing 1.3MB of JSON on the main thread
blocks paint, which defeats the point. IndexedDB is asynchronous, stores
structured clones (no `JSON.parse` cost), and its quota is typically hundreds of
MB.

The repo already has a thin `utils/storage.ts` wrapper over `localStorage`; it
is right for the small preference values it holds today
(`ConfigContext.tsx:143`, `HoldingsTable.tsx:124`) and should not be extended to
carry price series.

### 4.2 Schema

```
db "allotmint-cache", version 1
├── store "responses"   key: cacheKey
│     { key, epoch, fetchedAt, url, payload }
│     index "by_epoch" on epoch
└── store "meta"        key: name
      { name: "epoch", value: "2026-05-16.9f2c1a4b7e03", checkedAt }
```

`cacheKey` is `${routeKey}:${stableParamsHash}` — query params sorted before
hashing so `?a=1&b=2` and `?b=2&a=1` share an entry.

### 4.3 Boot sequence

```
1. read meta.epoch from IndexedDB              (fast, local)
2. render immediately from cache               (optimistic, no network wait)
3. GET /prices/version  { cache: "no-store" }  (one small request)
4. if fetched epoch !== stored epoch:
       delete all "responses" where epoch !== fetched   (via by_epoch index)
       write meta.epoch = fetched
       signal subscribers to refetch
   else:
       cache stands; no further price requests this session
```

Step 2 before step 3 is the point. The user sees data on the first frame; the
version check resolves in the background and, in the overwhelmingly common case
(same day, unchanged epoch), confirms what is already on screen.

**Bounding the staleness this introduces.** Rendering before the epoch check
means a user whose cache is a day old sees yesterday's closes for the duration of
one `/prices/version` round trip. That is a real, if brief, window and this being
financial data it should be bounded explicitly rather than waved through:

- The check is a single small uncached GET issued during app bootstrap, so the
  window is one RTT — sub-second on any normal connection, and it is *not*
  gated behind the page's other data fetches.
- Cached values must render with the epoch's own date visible (the existing
  "prices as of" affordance in `AppHeader.tsx:50-60` already has the slot for
  this), so optimistic content is never presented as more current than it is.
- If `/prices/version` fails outright, keep serving cache but surface the staleness
  rather than silently pretending it is fresh — an unreachable backend is exactly
  when a user most needs to know the age of what they are looking at.

What this must never become is a *deliberate* staleness budget: the window is
"however long one request takes", not a tunable TTL.

### 4.4 Where it hooks in

Wrap `fetchJson` (`frontend/src/api.ts:364`) rather than editing ~60 call sites:

```ts
export const fetchJson = withPriceCache(defaultClient.fetchJson);
```

`withPriceCache` consults a route allowlist; anything not price-derived passes
straight through. This keeps the change to a handful of files and means new
price endpoints opt in by adding one entry.

The two existing in-memory caches (Finding C) then collapse into this one layer.
Keep `useInstrumentHistory`'s **in-flight promise dedupe**
(`useInstrumentHistory.ts:12`) — that solves a different problem (concurrent
callers and StrictMode double-effects) and is still needed on a cache miss.

### 4.5 Cache the superset, slice on the client

Today the cache key includes `days`, so the same series is fetched separately at
30 (`HoldingsTable.tsx:135`, `GroupPortfolioView.tsx:543`) and 365
(`InstrumentResearch.tsx:156`) — overlapping data stored twice.

Instead, cache the **canonical 365-day series** per ticker and derive 7/30/180
by slicing in the client. One fetch then serves every range, cache entries drop
by the number of distinct ranges, and — usefully — `mini` becomes pure
redundancy that can be dropped from the wire entirely (§5.2).

### 4.6 Degradation

IndexedDB can be unavailable (private browsing) or throw (`QuotaExceededError`).
Every cache read and write must be wrapped so failure falls back to the existing
in-memory map and then the network. **A cache problem must never surface as a
failed data load.** On quota exhaustion, evict oldest-first by `fetchedAt`
before giving up.

---

## 5. Layer 3 — batch endpoint and payload diet

Layers 1–2 do nothing for a first visit with a cold cache; the fan-out of
Finding D still costs 40 round trips.

### 5.1 Batch endpoint

```http
GET /instrument/batch?tickers=VWRL.L,ERNS.L,PFE.N&days=365
```
```json
{
  "epoch": "2026-05-16.9f2c1a4b7e03",
  "instruments": { "VWRL.L": { "prices": [...] }, "ERNS.L": { "prices": [...] } },
  "empty":   ["PFE.N"],
  "unknown": ["BOGUS.L"]
}
```

- Cap `tickers` (100 suggested) to bound worst-case work; the client chunks past that.
- `empty` vs `unknown` preserves the current contract: `preloadInstrumentHistory`
  returns tickers that *resolved* but had no history, which drives the single
  consolidated "no price history" notice
  (`useInstrumentHistory.ts:86-91`, `HoldingsTable.tsx:151`). Collapsing the two
  would regress that message.
- One request means one ETag and one cache entry — it composes with Layers 1–2
  rather than sitting beside them.
- The three buckets are a **partition**: every requested ticker appears in exactly
  one of `instruments`, `empty`, or `unknown`, and their union equals the request
  (post-deduplication). Say so in the response contract and assert it in tests —
  a ticker silently absent from all three, or double-counted across two, is the
  failure mode that makes the caller's "no price history" count wrong.

Once this lands, the duplicated 429-backoff machinery
(`useInstrumentHistory.ts:162-186`, `api.ts:959-1010`) has no fan-out left to
defend against and one copy can go.

### 5.2 Drop `mini` from the default payload

With §4.5 slicing client-side, `mini` is 217 duplicated rows of pure waste
(`backend/common/instrument_api.py:304-308`). Make it opt-in
(`?include_mini=true`), default off, and delete the flag once no caller sets it.
Roughly **37% off every instrument payload** for no behaviour change.

---

## 6. Cacheability rules

### 6.1 By route class

| Route | Epoch-keyed | Notes |
|---|---|---|
| `/instrument/`, `/instrument/batch` | yes | canonical 365-day series |
| `/portfolio/{owner}`, `/portfolio-group/{slug}` | yes | `private`; per-user |
| `/movers`, `/screener`, `/opportunities` | yes | derived from EOD closes |
| `/timeseries/edit`, `/instrument/admin/*` | **no** | mutable; admin-edited |
| `/instrument/intraday` | **no** | intraday by definition; not EOD |
| `/prices/refresh`, `/prices/version` | **no** | `no-store` |

`/instrument/intraday` (`frontend/src/api.ts:945`) is the explicit exception to
the whole premise — it is the one price path that is *not* end-of-day and must
never be epoch-cached.

Admin edit routes are equally important to exclude: `saveTimeseries`
(`api.ts:1018`) and `rebuildTimeseriesCache` (`api.ts:1045`) mutate the series a
user is looking at. After any admin mutation the client must force an epoch
re-check and drop affected entries, or an editor will "fix" a price and keep
seeing the old one.

### 6.2 Historical (`as_of`) queries

`getPortfolio` and `getGroupPortfolio` accept `as_of` (`api.ts:376-418`). A
completed historical date is immutable — it does not change at the next daily
refresh. Give those entries their own long-lived rule
(`max-age=604800, immutable`) and exempt them from epoch eviction, keyed by the
`as_of` value.

One caveat: only for `as_of` strictly *before* the current EOD date. An `as_of`
of yesterday can still be revised by a late data correction, so treat only dates
older than the epoch's own date as immutable.

---

## 7. Failure modes and mitigations

| Risk | Mitigation |
|---|---|
| Shared cache leaks per-user data | `private` + `Vary: Authorization`; allowlist not denylist (§3.4/§3.5); test asserts no price route emits `public` |
| Epoch changes on redeploy, nulling all caches | Content-derived hash, never `_PRICE_SNAPSHOT_TS` (§2.1) |
| Stale prices after out-of-band `/prices/refresh` | `max-age` capped at 1h (§3.2); re-check epoch on `visibilitychange` and on window focus |
| Admin edits invisible to the editor | Admin mutations force epoch re-check + targeted eviction (§6.1) |
| IndexedDB quota exceeded | Evict oldest by `fetchedAt`; fall back to memory; never fail the load (§4.6) |
| Two tabs disagreeing on epoch | `BroadcastChannel("allotmint-epoch")` on change; each tab drops stale entries |
| Cache masks a real backend fault | Epoch check is `no-store`, so a broken backend surfaces on the next check rather than being papered over indefinitely |

---

## 8. Phasing

Each phase ships independently and is useful alone.

| Phase | Work | Depends on | Payoff |
|---|---|---|---|
| 0 | `GET /prices/version` + content hash | — | enables everything |
| 1 | Cache headers, ETag, `304` | 0 | backend-only; instant win, no FE change |
| 2 | IndexedDB cache keyed on epoch | 0 | survives reload |
| 3 | Batch endpoint; `mini` opt-in | — | fixes cold-cache first paint |
| 4 | Idle prefetch, `BroadcastChannel`, drop duplicate 429 backoff | 2, 3 | polish |

Phases 1 and 3 are independent of each other and can run in parallel. **Phase 3
is the one to do first if only one phase is ever done** — it is the only one
that helps a first-time visitor, and Finding D says that is where the current
pain is.

---

## 9. Alternatives considered and rejected

**Adopt `@tanstack/react-query`.** The idiomatic answer, and genuinely good at
this. Rejected for now: it is a new runtime dependency plus a migration across
~60 API functions, and its default persistence story still needs an IndexedDB
persister and an epoch-equivalent for invalidation — so it does not remove any
of the design work above, it only relocates it. Worth revisiting as a Phase 5
refactor once the epoch contract is proven; the `withPriceCache` wrapper (§4.4)
is deliberately shaped so it could be swapped for a query client later.

**A service worker with a cache-first strategy.** Would deliver Layer 2 without
touching `api.ts`. Rejected: the PWA plugin was removed from this repo
deliberately (`frontend/vite.config.ts:29`), service-worker lifecycle and
update-skew bugs are notoriously hard to debug, and a cache-first SW intercepting
authenticated responses reintroduces the §3.4 privacy problem in a place that is
much harder to reason about.

**Put the API behind CloudFront and cache there.** Reduces backend load but not
round-trip latency, which is what users feel, and shared-cache semantics on
per-user authenticated responses is exactly the risk §3.4 exists to avoid.

**Snapshot the whole dataset into the client on load.** Attractive given how
small the universe is, but it does not scale with the instrument count and turns
first paint into one large blocking download. §5.1's bounded batch gets most of
the benefit with none of the cliff.

---

## 10. Test plan

Backend (`tests/backend/`):
- epoch is stable across repeated calls with unchanged snapshot content;
- epoch changes when snapshot content changes, and **not** when only
  `_PRICE_SNAPSHOT_TS` is reset (guards §2.1);
- price-derived GET returns `ETag`; replaying it as `If-None-Match` yields `304`
  with an empty body;
- **no price route ever emits `public`**, and every cached route emits
  `Vary: Authorization` (guards §3.4);
- `/instrument/intraday`, admin edit routes and `/prices/version` emit
  `no-store`;
- batch endpoint splits `empty` vs `unknown` correctly, partitions the request
  with no ticker missing or double-counted (§5.1), and honours the ticker cap;
- every cached route emits a **weak** `ETag` in the agreed
  `W/"<epoch>:<route-key>"` shape — a strong ETag anywhere is a failure, since
  it breaks revalidation across content-codings (§3.1).

Frontend (`frontend/src/**/__tests__/`):
- a cache hit on a matching epoch resolves without a network call;
- an epoch change evicts non-matching entries and refetches;
- IndexedDB unavailable or throwing falls back to network, and the component
  still renders (guards §4.6);
- 365-day cached series slices correctly to 7/30/180 (guards §4.5);
- `as_of` entries survive an epoch change (guards §6.2);
- two tabs observing an epoch change concurrently converge on one eviction pass
  and do not thrash each other's cache via `BroadcastChannel` (guards §7);
- on simulated `QuotaExceededError`, eviction proceeds oldest-first by
  `fetchedAt` and the fetch still resolves (guards §4.6).

Measurable acceptance, on a 40-holding portfolio:
- cold load: 1 batch request, not 40;
- warm reload, same epoch: **zero** instrument-history requests;
- instrument payload shrinks ~37% with `mini` off.
