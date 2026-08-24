# Decision: client-side caching of end-of-day price data (#6911)

Status: **Proposed** — design for
[#6911](https://github.com/leonarduk/allotmint/issues/6911).
Scope: the client-side caching strategy for every price-derived read path
(instrument history, sparklines, portfolio valuation, movers, screener), and the
version/identity contract that makes caching them safe.

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
therefore stable between refreshes. That is the premise — §1 sets out where it
holds and the two places it does not.

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

> A cached response is immutable for the lifetime of the **version vector** it
> was fetched under, scoped to the **identity** that fetched it.

The naive form of this — "prices are EOD, so everything price-derived is stable
for a day" — is the premise that motivated this work, and taken literally it is
**wrong**. Two things break it, and both are load-bearing:

**A portfolio response is not price-derived alone.** It is a join of EOD prices
with holdings, and holdings are user-mutable at any moment: `POST/PUT/DELETE
/transactions`, `POST /transactions/import`, `POST /holdings/import`,
`POST /holdings/reconcile`, `POST /holdings/manual` and `POST /accounts`
(`backend/routes/transactions.py:656,683,760,816,960,986,1021,1073`) all rewrite
account documents without touching `_PRICE_SNAPSHOT`. Keying `/portfolio/{owner}`
on a price-only epoch would serve a stale valuation until the next 00:00 UTC
refresh — a user could add a transaction and not see it for a day.

**A cache entry is not identity-free.** The browser store is shared by every user
of that profile, so an entry keyed only by route and params can be read back by a
different logged-in user. `Cache-Control: private` does not help here; it governs
the HTTP cache, not an application-managed IndexedDB.

So the version is a **vector, not a scalar**:

| Component | Changes when | Applies to |
|---|---|---|
| `price_epoch` | EOD price data changes (§2) | every price-derived route |
| `accounts_rev` | any holdings/transactions/accounts write (§2.3) | portfolio routes only |
| `identity` | the authenticated user changes (§4.2) | every cached entry |

A route caches against exactly the components it actually depends on. Market data
(`/instrument/`, `/movers`, `/screener`) depends on `price_epoch`; portfolio
routes depend on `price_epoch` **and** `accounts_rev`; everything is namespaced by
`identity`. Getting this mapping wrong is the difference between a fast app and
one that shows people stale valuations or, worse, someone else's.

Three layers, in increasing order of effort and payoff:

```
Layer 1  HTTP validators        backend only, no FE change      ~free revalidation
Layer 2  Persistent client cache IndexedDB, keyed on vector+id  survives reload
Layer 3  Batch + payload diet   collapses N+1 fan-out           fixes first paint
```

Layers 1 and 2 make the *second* visit fast. Layer 3 is the one that makes the
*first* visit fast; it is not optional garnish.

---

## 2. Layer 0 — the version vector (`GET /data/version`)

Nothing today tells a client "the data changed". `_PRICE_SNAPSHOT_TS` exists in
process memory (`backend/common/portfolio_utils.py:325`) but is only surfaced by
`/prices/refresh`, which *performs* a full refresh as a side effect and is
exposed as both GET and POST (`backend/routes/portfolio.py:989,994`) — unusable
as a polling endpoint.

Add a new, cheap, side-effect-free endpoint:

```http
GET /data/version
```
```json
{
  "price_epoch":  "2026-05-16.9f2c1a4b7e03a1",
  "accounts_rev": "c40b1e77d9f2",
  "snapshot_ts":  "2026-05-17T00:04:11Z",
  "next_refresh_utc": "2026-05-18T00:00:00Z"
}
```

Named `/data/version` rather than `/prices/version`: it now reports more than
prices, and it must not sit under the `/prices/*` prefix whose neighbour
`/prices/refresh` has side effects.

### 2.1 `price_epoch` must be content-derived

```python
def price_epoch(snapshot: dict, series_manifest: list[tuple[str, int, int]]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(payload.encode())
    for name, mtime_ns, size in sorted(series_manifest):   # see 2.2
        h.update(f"{name}:{mtime_ns}:{size}".encode())
    latest = max((v.get("last_price_date") or "" for v in snapshot.values()), default="")
    return f"{latest}.{h.hexdigest()[:14]}"
```

**This is the one decision most likely to be got wrong.** The obvious
implementation — return `_PRICE_SNAPSHOT_TS` — is broken: that timestamp is set
on every process start by `refresh_snapshot_in_memory()`
(`portfolio_utils.py:328-340`), so a Lambda cold start or a redeploy would mint
a new epoch and invalidate every client cache in the fleet without a single
price having changed. Under Lambda's concurrency model, two simultaneous
requests could even report different epochs.

Hashing content makes the epoch stable across restarts, identical across
concurrent workers, and different if and only if the data differs. The `latest`
date prefix is cosmetic but valuable: it makes the epoch human-readable in
devtools and sorts naturally in logs.

### 2.2 Hashing the snapshot alone is not enough — parquet must be covered

`latest_prices.json` is not the only source of EOD data, and treating it as such
leaves a hole. Instrument history is read from the **parquet series** via
`load_meta_timeseries_range`, and `POST /timeseries/edit`
(`backend/routes/timeseries_edit.py:239`) rewrites that parquet directly without
touching `_PRICE_SNAPSHOT`. An admin correcting a bad close would therefore leave
`price_epoch` unchanged — so the ETag would still match, conditional requests
would return `304`, and other tabs and devices would never learn of the edit.
The editor would "fix" a price and keep being served the old one.

The epoch must therefore also cover a **series manifest**: for every cached
`(ticker, exchange)`, its mtime and size. The pieces already exist —
`list_cached_meta_tickers()`, `meta_timeseries_cache_path()` and
`_s3_object_mtime()` in `backend/timeseries/cache.py`.

Be precise about why this is affordable, because the obvious justification is
wrong. The existing S3 mtime cache is **not** a general-purpose one: it holds
entries for 30 seconds (`_S3_MTIME_TTL_SECONDS = 30.0`,
`backend/timeseries/cache.py:355`), so it absorbs a burst and nothing more. What
makes the manifest cheap is the memoisation strategy below, not that cache.

Three constraints on the manifest:

- **Never rebuild it per request.** Compute it on refresh and on any admin
  mutation, and memoise; a per-request `HEAD` per ticker would make the version
  endpoint more expensive than the data it guards — and the 30-second TTL would
  not save it.
- **Recompute on the existing invalidation hook.** `invalidate_s3_cache_metadata()`
  (`backend/timeseries/cache.py:377`) is already called after a write or delete;
  that is the natural place to mark the manifest dirty, rather than a parallel
  path that a new write site can miss.
- If enumerating every series proves too costly at scale, the fallback is an
  explicit durable counter bumped by every parquet write path. That is more
  code and easier to forget on a new write path, which is why the derived
  manifest is preferred — but a counter that is actually maintained beats a
  manifest that is skipped for cost.

The digest is 14 hex chars (56 bits) rather than 12. At this dataset size
collision probability is negligible either way, but the failure mode of a
collision is silently serving stale prices, so the cheaper-than-free margin is
worth taking.

### 2.3 `accounts_rev` — the holdings component

`accounts_rev` must change on every write listed in §1. Do **not** derive it from
a timestamp for the same reason as the epoch.

The backend already computes exactly the right thing: `_safe_file_signature` and
`_safe_dir_signature` (`backend/common/data_loader.py:64,103`) produce content
digests over owner directories and account files, and the owner-index cache
described in `docs/performance-caching.md` already invalidates on that signature.
`accounts_rev` should be a digest over those same signatures rather than a
parallel mechanism that can drift from it.

Two properties this must have:

- **Per-user scoping is a nice-to-have, not a requirement.** A global
  `accounts_rev` means one user's write invalidates every user's portfolio cache.
  That is wasteful but correct, and correct-and-wasteful is the right starting
  point. Scope it per owner later if the churn proves noticeable.
- **Client-side mutations invalidate synchronously too.** A successful holdings
  write from this tab should evict the affected portfolio entries immediately
  rather than waiting for the next version poll — the server revision is what
  makes *other* tabs and devices converge, not what makes the acting tab feel
  responsive.

### 2.4 Cost and caching of the endpoint itself

It reads already-in-memory state plus the memoised manifest digest. The endpoint
must be served `Cache-Control: no-store` — it is the thing that invalidates
everything else and must never be cached.

---

## 3. Layer 1 — HTTP validators (backend only)

The highest value per line of code: it requires **no frontend change** and
benefits every existing `fetch` call immediately.

### 3.1 Headers

For price-derived GET routes:

```
Cache-Control: private, max-age=<min(seconds_to_next_refresh, 3600)>, stale-while-revalidate=604800, no-transform
ETag: W/"<version-vector>:<route-key>"
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
rest on the TTL — it rests on the version check in §4.3.

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
| Per-user portfolio | `/portfolio/{owner}`, `/portfolio-group/{slug}` | `private`; ETag over `price_epoch` **+** `accounts_rev` (§2.3) |
| Market-wide, non-identifying | `/instrument/`, `/movers`, `/screener` | `private`; ETag over `price_epoch` (see note) |
| Historical `as_of=` | any route with `as_of` | `private, max-age=604800`; not `immutable` (§6.2) |
| Mutations, auth, `/data/version` | `POST` routes, `/token` | `no-store` |

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
db "allotmint-cache-<identityHash>", version 1     ← one database per identity
├── store "responses"   key: cacheKey
│     { key, identityHash, priceEpoch, accountsRev, fetchedAt, url, payload }
│     index "by_version" on [priceEpoch, accountsRev]
└── store "meta"        key: name
      { name: "version", priceEpoch, accountsRev, identityHash, checkedAt }
```

`cacheKey` is `${identityHash}:${routeKey}:${stableParamsHash}` — query params
sorted before hashing so `?a=1&b=2` and `?b=2&a=1` share an entry.

**Identity must be in the key, and this is a correctness requirement, not
hygiene.** A browser profile is shared: log out as one user, log in as another,
and a key built only from route and params resolves to the previous user's entry
— which §4.3 then renders *before* any network validation. `/instrument/` makes
this concrete, since its response embeds the caller's `positions`
(`backend/routes/instrument.py:399,479`). The §3.4 `private`/`Vary` rules do not
help: those govern the HTTP cache, whereas this is an application-managed store
the browser applies no policy to at all.

Three defences, all required:

1. `identityHash` is a salted digest of the authenticated subject — never the raw
   email. `StoredUserProfile` carries `email` (`frontend/src/authStorage.ts:1-5`);
   the token's `sub` claim is the better source where reachable. Hash it so the
   store never holds an identifier in the clear.
2. It is in both the **database name** and the **key**. Per-identity databases
   mean a wrong-identity read is not merely improbable but unaddressable, and
   deleting one user's cache never touches another's.
3. **Purge on every identity transition.** On login, logout, and on the
   `UNAUTHORIZED_EVENT` already dispatched on 401 (`frontend/src/api.ts:185,305`),
   drop the databases of any identity that is not the current one. Logout is the
   important one: leaving a populated store behind for the next person to sign in
   on that machine is the whole failure mode.

An entry whose `identityHash` does not match the live identity is **discarded,
never served** — no "probably fine" fallback.

### 4.3 Boot sequence

```
0. resolve identityHash; if it differs from meta.identityHash,
   DROP the store and skip to 3 — never render another user's cache
1. read meta.{priceEpoch, accountsRev} from IndexedDB   (fast, local)
2. render immediately from cache                        (optimistic, no network)
3. GET /data/version  { cache: "no-store" }             (one small request)
4. if priceEpoch changed:
       evict every entry (all cached routes depend on it)
   else if accountsRev changed:
       evict portfolio-route entries only; market data stands
   write meta.{priceEpoch, accountsRev, identityHash}
   signal subscribers to refetch what was evicted
```

Step 0 comes before everything and has no optimistic path: an identity mismatch
means drop, never render. Step 2 before step 3 is the point of the rest — the
user sees data on the first frame, and the version check resolves in the
background confirming what is already on screen in the common case.

Splitting eviction at step 4 is what makes `accounts_rev` cheap: adding a
transaction should invalidate the user's portfolio views, not their whole
instrument-history cache.

**Bounding the staleness this introduces.** Rendering before the version check
means a user whose cache is a day old sees yesterday's closes for the duration of
one `/data/version` round trip. That is a real, if brief, window and this being
financial data it should be bounded explicitly rather than waved through:

- The check is a single small uncached GET issued during app bootstrap, so the
  window is one RTT — sub-second on any normal connection, and it is *not*
  gated behind the page's other data fetches.
- Cached values must render with the epoch's own date visible (the existing
  "prices as of" affordance in `AppHeader.tsx:50-60` already has the slot for
  this), so optimistic content is never presented as more current than it is.
- If `/data/version` fails outright, keep serving cache but surface the staleness
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

Instead, cache the **canonical 365-day series** per ticker and derive the shorter
ranges in the client. One fetch then serves every range, cache entries drop by the
number of distinct ranges, and — usefully — `mini` becomes pure redundancy that
can be dropped from the wire entirely (§5.2).

**Derive by date cutoff, never by row count.** This is the trap:

```ts
rows.slice(-30)                                  // ✗ 30 trading sessions ≈ 6 weeks
rows.filter(r => r.date >= isoDaysAgo(30))       // ✓ 30 calendar days
```

`days` is a **calendar** lookback throughout the backend — `resolve_date_range`
computes `today - days` and documents "`days` means 'calendar days back'"
(`backend/utils/timeseries_helpers.py:171-196`). Taking the last N rows of a
365-day series instead selects N *trading sessions*, which spans roughly half as
long again: `slice(-30)` covers about six calendar weeks, not thirty days. Every
sparkline would silently start showing a longer period than it does today, with
no visible error — the chart still renders, it just quietly means something else.

Worth knowing why this is easy to miss: the existing `mini` **is** row-based
(`out[-7:]`, `out[-30:]`, `out[-180:]` at `backend/common/instrument_api.py:304-308`),
so the row-count idiom is already in the codebase and looks like the precedent to
follow. It reads as correct today only because the caller requesting `days=30` gets
a series that is already clipped to 30 calendar days, leaving `out[-30:]` a no-op.
Widen the cached window to 365 and that coincidence disappears. Migrate to the date
cutoff and the ambiguity goes with it.

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

- Cap `tickers` (100 suggested) to bound worst-case work; the client chunks past
  that. Overflow is a **`400`, never a silent truncation** — a response that
  quietly covers the first 100 of 140 tickers reads as complete and would leave
  40 holdings mysteriously blank. Deduplicate before applying the cap.
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

| Route | Keyed on | Notes |
|---|---|---|
| `/instrument/`, `/instrument/batch` | `price_epoch` | canonical 365-day series |
| `/portfolio/{owner}`, `/portfolio-group/{slug}` | `price_epoch` + `accounts_rev` | `private`; price epoch alone is **not** sufficient (§1) |
| `/movers`, `/screener`, `/opportunities` | `price_epoch` | derived from EOD closes |
| `/timeseries/edit`, `/instrument/admin/*` | **no** | mutable; admin-edited |
| `/instrument/intraday` | **no** | intraday by definition; not EOD |
| `/prices/refresh`, `/data/version` | **no** | `no-store` |

`/instrument/intraday` (`frontend/src/api.ts:945`) is the explicit exception to
the whole premise — it is the one price path that is *not* end-of-day and must
never be version-cached.

Admin edit routes are equally important to exclude: `saveTimeseries`
(`api.ts:1018`) and `rebuildTimeseriesCache` (`api.ts:1045`) mutate the series a
user is looking at. Two things are needed and neither is sufficient alone: the
acting client force-rechecks the version and drops affected entries immediately,
**and** `price_epoch` covers the parquet manifest (§2.2) so every *other* client
converges too. With only the first, an editor fixes a price on one machine and
keeps seeing the old value everywhere else.

### 6.2 Historical (`as_of`) queries

`getPortfolio` and `getGroupPortfolio` accept `as_of` (`api.ts:376-418`). A
completed historical date does not change at the next daily refresh, so those
entries get their own long-lived rule (`max-age=604800`) and are exempt from
`price_epoch` eviction, keyed by the `as_of` value.

Three caveats, and the second is the one that bites:

- **Only for `as_of` strictly before the current EOD date.** An `as_of` of
  yesterday can still be revised by a late data correction, so treat only dates
  older than the epoch's own date as settled.
- **Exempt from `price_epoch`, *not* from `accounts_rev`.** "Historical" describes
  the price window, not the holdings: a backdated or corrected transaction changes
  what the portfolio *was* on a past date. `POST /transactions` with an old
  `date`, or a `PUT`/`DELETE` on an existing one, rewrites history — so a
  historical valuation cached before that edit is simply wrong. These entries must
  still be evicted on an `accounts_rev` change. This is the §1 finding applied to
  the case where it is easiest to forget.
- **A future-dated `as_of` is not cacheable at all.** It is not a settled
  historical query; it resolves against whatever the latest data happens to be and
  changes meaning as time passes. Reject it or treat it as live — never as
  immutable.

Note the deliberate omission of `immutable` from the `Cache-Control` above:
`immutable` tells the browser not to revalidate even on an explicit reload, which
is the wrong contract for something a backdated edit can invalidate.

---

## 7. Failure modes and mitigations

| Risk | Mitigation |
|---|---|
| Shared cache leaks per-user data | `private` + `Vary: Authorization`; allowlist not denylist (§3.4/§3.5); test asserts no price route emits `public` |
| `price_epoch` changes on redeploy, nulling all caches | Content-derived hash, never `_PRICE_SNAPSHOT_TS` (§2.1) |
| Stale prices after out-of-band `/prices/refresh` | `max-age` capped at 1h (§3.2); re-check epoch on `visibilitychange` and on window focus |
| IndexedDB quota exceeded | Evict oldest by `fetchedAt`; fall back to memory; never fail the load (§4.6) |
| Two tabs disagreeing on version | `BroadcastChannel("allotmint-version")` on change; each tab drops stale entries |
| **Stale holdings after a transaction write** | `accounts_rev` in the vector, bumped by every account write path; portfolio routes key on it (§1, §2.3) |
| **One user served another's cached data** | Identity in the DB name *and* key; purge on login/logout/401; mismatched entries discarded not served (§4.2) |
| **Admin parquet edit invisible to editor or other clients** | `price_epoch` covers the series manifest, not just snapshot JSON (§2.2), plus forced re-check on the acting client (§6.1) |
| **Sparkline window silently widens** | Slice cached series by date cutoff, never `slice(-N)` (§4.5) |
| Cache masks a real backend fault | The version check is `no-store`, so a broken backend surfaces on the next check rather than being papered over indefinitely |

### 7.1 Cross-tab contract

`BroadcastChannel("allotmint-version")` carries one message shape:

```ts
{ type: "version", priceEpoch, accountsRev, identityHash, observedAt }
```

Rules, so concurrent tabs converge instead of fighting:

- **Only the tab that observed the change posts.** A tab that acts on a received
  message does not re-broadcast — that is what turns two tabs into a loop.
- **Receivers apply, they do not re-fetch the version.** The message is the
  authority for this round; hitting `/data/version` again on receipt just
  multiplies requests by the tab count.
- **Ignore a message whose `identityHash` is not the receiver's.** Tabs can be
  signed in as different users; a version change for one is not a licence to
  evict the other's store.
- **Last-writer-wins on `observedAt`.** A message older than the state already
  applied is dropped, so a slow tab cannot roll a fast one backwards.
- The channel is an **optimisation, not a correctness requirement**: it is
  unavailable in some contexts, and every tab still converges on its own next
  version check. Nothing may depend on delivery.

---

## 8. Phasing

Each phase ships independently and is useful alone.

| Phase | Work | Depends on | Payoff |
|---|---|---|---|
| 0 | `GET /data/version`: `price_epoch` (incl. series manifest) + `accounts_rev` | — | enables everything |
| 1 | Cache headers, ETag, `304` | 0 | backend-only; instant win, no FE change |
| 2 | IndexedDB cache keyed on version vector, namespaced by identity | 0 | survives reload |
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

Every ★ test below guards a defect that was live in an earlier draft of this
document — each one is there because the design got it wrong first. They are the
ones not to drop for time.

Backend (`tests/backend/`):
- `price_epoch` is stable across repeated calls with unchanged inputs;
- `price_epoch` changes when snapshot content changes, and **not** when only
  `_PRICE_SNAPSHOT_TS` is reset (guards §2.1);
- ★ `price_epoch` changes after `POST /timeseries/edit` rewrites a parquet
  series, with `latest_prices.json` untouched (guards §2.2 — the manifest is the
  only thing that makes this pass);
- ★ `accounts_rev` changes after **each** write path in §1 — `POST/PUT/DELETE
  /transactions`, `/transactions/import`, `/holdings/import`, `/holdings/reconcile`,
  `/holdings/manual`, `/accounts` — parametrised so a newly added write path
  without a bump fails here rather than in production (guards §2.3);
- a portfolio ETag changes when `accounts_rev` changes even though `price_epoch`
  has not, and `If-None-Match` then returns `200`, not `304`;
- price-derived GET returns `ETag`; replaying it as `If-None-Match` yields `304`
  with an empty body;
- **no price route ever emits `public`**, and every cached route emits
  `Vary: Authorization` (guards §3.4);
- `/instrument/intraday`, admin edit routes and `/data/version` emit `no-store`;
- batch endpoint splits `empty` vs `unknown` correctly, partitions the request
  with no ticker missing or double-counted, and rejects an over-cap request with
  `400` rather than truncating (guards §5.1);
- every cached route emits a **weak** `ETag` in the agreed
  `W/"<version-vector>:<route-key>"` shape — a strong ETag anywhere is a failure,
  since it breaks revalidation across content-codings (§3.1);
- `max-age` never exceeds 3600 even when the next refresh is much further away
  (guards §3.2). Assert on the emitted header value rather than waiting out a
  clock — the timing behaviour is the browser's, but the cap is ours, and a
  regression here silently strands users on superseded prices.

Frontend (`frontend/src/**/__tests__/`):
- a cache hit on a matching vector resolves without a network call;
- a `price_epoch` change evicts everything; an `accounts_rev` change evicts
  portfolio entries **only**, leaving instrument history cached (guards §4.3);
- ★ an entry written under identity A is never served to identity B: switching
  identity drops the store, and a stale-identity entry is discarded rather than
  rendered (guards §4.2 — assert on `/instrument/`, which embeds `positions`);
- ★ logout purges the store, so a subsequent login on the same profile starts
  cold (guards §4.2);
- IndexedDB unavailable or throwing falls back to network, and the component
  still renders (guards §4.6);
- ★ deriving a 30-day range from a cached 365-day series returns rows within
  30 **calendar** days — feed a series with a holiday gap so a row-count
  implementation returns a visibly wider window and fails (guards §4.5);
- `as_of` entries survive a `price_epoch` change (guards §6.2);
- two tabs observing a version change concurrently converge on one eviction pass
  and do not thrash each other's cache via `BroadcastChannel` (guards §7.1);
- ★ a `BroadcastChannel` message carrying a **different** `identityHash` is
  ignored, leaving the receiving tab's store intact (guards §7.1). Convergence
  and identity filtering are separate properties and a convergence test passes
  without exercising this one: two tabs signed in as different users must not be
  able to evict each other, and the same path would otherwise let a crafted
  message clear an unrelated identity's cache;
- on simulated `QuotaExceededError`, eviction proceeds oldest-first by
  `fetchedAt` and the fetch still resolves (guards §4.6).

Measurable acceptance, on a 40-holding portfolio:
- cold load: 1 batch request, not 40;
- warm reload, unchanged vector: **zero** instrument-history requests;
- instrument payload shrinks ~37% with `mini` off;
- adding one transaction refreshes the valuation on the next poll without
  invalidating the instrument-history cache.
