# Issue 6297: index-constituent instrument ingestion plan

This document records the repository review and proposed implementation plan for
[issue 6297](https://github.com/leonarduk/allotmint/issues/6297). It is a design
plan, not approval to redistribute index constituent data. Implementation must
remain sequenced after issue 6296 so it can reuse the resulting ticker-resolution
and persistence boundary.

## Review findings

- The bundled catalogue currently contains only a small seed set under
  `data/instruments/<exchange>/<symbol>.json`. Runtime reads may instead use
  `DATA_ROOT`, and `METADATA_BUCKET`/`METADATA_PREFIX` add an S3 persistence
  path. An ingestion command therefore cannot assume that writing the checkout
  is the production deployment mechanism.
- `get_instrument_meta()` is intentionally read-only with respect to upstream
  providers. This invariant should remain: catalogue reads must not trigger
  hundreds of network requests.
- `_auto_create_instrument_meta()` already performs explicit Yahoo enrichment,
  respects offline/test gating, adds `ticker` and `exchange`, and writes through
  `save_instrument_meta()`. Issue 6296 is expected to improve the unresolved
  bare-symbol/exchange case; issue 6297 should call the resulting public service
  function rather than import a private helper or duplicate suffix rules.
- The existing single-instrument admin refresh route only refreshes a record
  that already exists. It is useful precedent for preview-before-write behavior,
  but it is not a batch ingestion API.
- Index membership is not instrument metadata. A security can belong to several
  overlapping indices, membership changes over time, and every observation needs
  source/as-of provenance. Embedding a single `index` field in each instrument
  JSON file would lose that information.
- `uk_sector_endpoint` and `default_sector_region` configure market-sector
  performance, not constituent discovery. They provide no reusable licensing or
  ingestion convention.
- The graphify snapshot identifies `get_instrument_meta()` as a high-fan-in
  function (degree 52), even though the finding is function-level rather than a
  verdict on the whole `backend/common/instruments.py` module. Changes around
  this read/enrichment boundary therefore warrant focused regression testing.
  The snapshot is manually refreshed and must not replace source inspection when
  issue 6296 lands.

## Data-source decision gate

Do not implement a production scraper until the maintainer records all of the
following for each source:

1. provider and exact endpoint/file;
2. permission to fetch, store, and (if applicable) commit or redistribute the
   constituent list;
3. symbol and exchange identifiers supplied by the provider;
4. authentication, rate limits, availability expectations, and cost;
5. effective-date/change semantics and expected refresh frequency.

**Recommendation:** define a provider-neutral manifest contract first, then use a
licensed API or maintainer-supplied file adapter. A checked-in static list is an
acceptable MVP only when its provenance, as-of date, and redistribution terms are
documented. Do not make Wikipedia/HTML scraping the unattended production source:
page shape, ticker conventions, timeliness, and licensing/provenance are not a
stable data contract. Yahoo enrichment also needs an explicit terms-of-use review;
availability through `yfinance` alone is not evidence that bulk or commercial use
is permitted.

The source decision is a blocking product/legal decision. The code can support
multiple adapters, but engineering should not silently choose a questionable
source.

## Proposed contracts

### Constituent manifest

Store source snapshots separately from generated instrument files, for example:

```text
data/index_constituents/<index-id>.json
```

Each snapshot should contain:

- stable index ID and display name;
- provider/source ID and source URL or dataset identifier;
- `as_of` date, retrieval timestamp, and optional effective date;
- declared license/provenance reference;
- constituents with the provider symbol plus an unambiguous exchange/MIC or a
  documented mapping status;
- schema version and optional source checksum.

The canonical ingestion input must be `(symbol, exchange)`, not a bare ticker.
Provider-specific adapters own translation to the repository's exchange codes.
Unknown or ambiguous translations go to a failure report and are never guessed.

### Enrichment service

After issue 6296, expose a non-private domain function that accepts a canonical
ticker, resolves metadata, validates required fields, and persists through
`save_instrument_meta()`. Return a structured result such as `created`, `updated`,
`unchanged`, `skipped`, or `failed` with a reason. Required success fields for
this issue are non-empty `name`, `currency`, `ticker`, and `exchange`.

Before that service reports `created` or `updated`, strengthen the persistence
boundary so it exposes the outcome for every configured target. In particular,
when `METADATA_BUCKET` is configured, an S3 `put_object` failure must be returned
as an explicit failure or raised to the caller; a successful local write must not
mask it. The batch must classify that ticker as failed, remain eligible for retry,
and include the failed target in its report. Tests should cover local-only,
S3-only/read-only-local, dual-write success, and local-success/S3-failure cases.

Keep membership snapshot storage and metadata enrichment as separate stages. This
makes source parsing deterministic and testable without Yahoo, and lets a failed
enrichment run resume from the same constituent snapshot.

## Delivery plan

### Phase 0 — decisions and issue 6296 dependency

1. Land issue 6296 and review its final public resolution API and exchange-code
   mapping; do not design against the issue's suggested private helper name.
2. Select and document the initial source, allowed storage/redistribution model,
   and owner of any credentials or subscription.
3. Choose the first vertical slice. Prefer one index (not all five) so identifier
   mapping, rate limits, and operational output are proven before scaling out.
4. Record a quarterly default review cadence, but use manual dispatch until two
   clean refreshes demonstrate that source changes and failure thresholds work.

### Phase 1 — deterministic source ingestion

1. Add a small module under `backend/utils/` with a provider adapter protocol and
   a JSON/file adapter for hermetic tests.
2. Validate manifests strictly: schema version, unique constituents, ISO dates,
   supported exchange mappings, provenance, and a non-empty list.
3. Write normalized snapshots atomically and retain the prior snapshot so a bad
   upstream response cannot erase the known universe.
4. Compute an added/removed/unchanged membership diff. Reject suspicious changes
   (empty response or a configurable large percentage change) unless an explicit
   override is supplied.

### Phase 2 — batch metadata enrichment

1. Add a CLI entrypoint with `--index`, `--source-file`/provider configuration,
   `--dry-run` (default), `--write`, and bounded request/concurrency controls.
2. Deduplicate canonical tickers across selected indices and skip complete,
   unchanged metadata unless `--refresh` is requested.
3. Call the post-6296 enrichment service for missing/incomplete entries. Use
   bounded retries with backoff for transient failures; do not retry validation,
   ambiguity, or unsupported-exchange failures.
4. Emit a machine-readable run report containing source/as-of data, membership
   diff, per-ticker outcome/reason, totals, duration, and the exact target
   (checkout/`DATA_ROOT`/S3). Exit non-zero for invalid input or when the configured
   failure threshold is exceeded.
5. Ensure reruns are idempotent and do not overwrite manually curated optional
   metadata with empty provider values.

### Phase 3 — operational workflow

1. Add `workflow_dispatch` first, with index/source, dry-run/write, and force
   inputs. Install pinned dependencies and upload the run report as an artifact.
2. Select one persistence model explicitly:
   - open a generated-data PR when redistribution permits committed snapshots and
     metadata; or
   - use an environment-protected job with scoped AWS credentials to write S3,
     when data must not be committed.
3. Grant least privilege only to the metadata prefix (and a separate snapshot
   prefix if used). Never expose provider secrets to pull-request workflows.
4. Add a quarterly schedule only after the manual runs are reliable. Scheduling
   should create a reviewable diff/report and alert on failure; it must not accept
   large membership removals silently.

### Phase 4 — expand and consume the universe

1. Add indices one at a time with mapping fixtures, starting with the chosen
   vertical slice.
2. Expose membership to screener/search through a bounded, indexed read path only
   when a consumer is specified. `list_instruments()` currently scans every JSON
   file, so catalogue growth should not automatically be coupled to an unbounded
   API response.
3. Document operator ownership, credential rotation, expected run time/cost,
   rollback, stale-data alerting, and how to handle corporate actions and ticker
   changes.

## Test and validation matrix

- Unit-test manifest validation, provider-to-canonical exchange mapping,
  duplicates, malformed/empty payloads, and membership diffs with local fixtures.
- Unit-test dry-run versus write, idempotent reruns, required-field enforcement,
  merge preservation, retry classification, and partial-failure reporting with
  all network and S3 calls mocked.
- Test local filesystem and mocked S3 persistence through the existing public
  storage boundary, including cache invalidation.
- Add a CLI smoke test using a tiny fixture containing overlapping membership,
  one unsupported exchange, one enrichment failure, and one existing record.
- Validate workflow syntax and confirm its command exists in the repository.
- Run the focused backend tests plus `make lint`; no automated test should depend
  on a live constituent provider or Yahoo.

## Acceptance criteria refinement

In addition to the issue's current checklist, implementation is complete only
when:

- at least one index can be ingested end-to-end from an approved, documented
  source;
- membership snapshots preserve source and as-of provenance independently of
  instrument metadata;
- ambiguous exchange mappings fail visibly rather than selecting the first ticker
  match;
- dry-run is safe by default, writes are idempotent, and every run produces an
  auditable summary;
- stale or suspiciously small/large upstream results cannot replace a valid
  snapshot without explicit review;
- required metadata fields are verified after enrichment, not merely requested;
- the operator documentation states where production data is persisted and how
  to roll it back.

## Principal risks

- **Licensing and provider terms:** the issue's largest blocker; resolve before
  committing data or enabling a schedule.
- **Identifier ambiguity:** the same symbol can exist on multiple venues, and US
  exchange codes currently collapse to the same Yahoo suffix. Require source
  exchange identity and preserve provenance.
- **Upstream fragility/rate limiting:** batch enrichment magnifies intermittent
  failures. Bound traffic, resume safely, and report partial results.
- **Repository/runtime divergence:** generated files in the checkout do not prove
  production S3 was updated. Reports must name the write target.
- **Catalogue scalability:** hundreds or thousands of JSON files increase scan and
  PR-review costs. Measure `list_instruments()` and introduce a generated catalogue
  index or datastore query before relying on it for broad search.
- **Corporate actions:** ticker changes, mergers, and removals must not delete
  historical metadata merely because a security leaves an index.
