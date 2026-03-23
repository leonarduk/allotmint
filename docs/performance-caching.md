# Backend request-path caching notes

## Current hotspot addressed

Issue #2411 identified owner/account discovery plus `person.json` metadata loading as a hot request-path cost. The `/owners` and owner-portfolio flows repeatedly scanned `data/accounts/*`, re-read `person.json`, and rebuilt account-name lists during normal request handling.

The backend now builds a local owner index read model for filesystem-backed account data. The index stores:

- owner slug,
- discovered account stems,
- parsed `person.json` metadata used by owner summaries and authorization checks.

## Refresh and invalidation rules

The cache is local-process memory only and applies to local/filesystem-backed discovery.

A cached index is reused only when the directory signature is unchanged. The signature currently includes:

- each owner directory mtime/size,
- each `person.json` file mtime/size.

That means the cache refreshes when:

- an owner directory is added or removed,
- an account file is added/removed/renamed inside an owner directory,
- `person.json` is edited,
- the in-process cache is explicitly cleared in tests.

The cache does **not** attempt cross-process coordination. A new process rebuilds its own index on first use.

## Validation

The regression tests cover three important scenarios:

1. repeated discovery calls reuse the cached index when the signature is unchanged;
2. metadata edits invalidate the cache and surface updated `full_name` values;
3. account-file changes invalidate the cache and surface updated account lists.

These checks live in `tests/backend/common/test_data_loader.py`.
