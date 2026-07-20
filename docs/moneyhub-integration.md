# Moneyhub Integration (Feasibility Spike)

Design note for [issue #2749](https://github.com/leonarduk/allotmint/issues/2749):
automating transaction import from Moneyhub instead of manual entry. This is a
spike deliverable only — no production wiring. Downstream implementation is
tracked in #3425 (chosen-approach import) and #3426 (CSV/OFX export fallback,
independent of this spike).

## Status: blocked on a human prerequisite

Moneyhub has no self-service API — registering a developer/business account
and obtaining sandbox credentials requires a human with a genuine Moneyhub
account. Nothing in this repo or its CI can perform that registration. This
note therefore covers everything that *can* be decided without live
credentials: access method, auth flow, secret storage, and the field-mapping
plan. The "working sandbox call retrieving sample transactions" success
criterion from the issue remains open until a human completes account
registration and hands credentials to an agent via SSM (see
[Handoff to a human](#handoff-to-a-human) below).

## Access method decision

**Use the official Moneyhub Open Banking API. Do not scrape
`client.moneyhub.co.uk`.**

Moneyhub is an Account Information Service Provider (AISP) built on the UK
Open Banking standard, exposed via OAuth2 / OpenID Connect. There is no
public, scraping-friendly surface, and scraping the authenticated web client:

- would break on any front-end change with no warning,
- likely violates Moneyhub's terms of service, and
- would require storing the user's Moneyhub login credentials directly,
  which is a materially worse security posture than holding an OAuth token
  scoped to `transactions:read`.

The two integration options considered:

| Option | Verdict |
| --- | --- |
| Official Moneyhub API (OAuth2/OIDC, `transactions:read` scope) | **Chosen.** Standards-based, revocable, no credential storage for the underlying bank. |
| Scrape `client.moneyhub.co.uk` | Rejected — against the explicit constraint in #2749, fragile, and a strictly worse security posture. |

## Auth flow

Moneyhub's transaction API is consent-based (AISP), not machine-to-machine,
because it re-exposes data the end user consented to share from their own
bank. The flow an AllotMint owner would go through:

1. **Client registration.** A human registers an AllotMint OAuth2 client with
   Moneyhub (sandbox first, then production), receiving a `client_id` /
   `client_secret` pair and agreeing the redirect URI(s).
2. **User consent (authorization code grant).** The AllotMint owner is
   redirected to Moneyhub's consent screen, authorizes read access to their
   connected bank accounts, and is redirected back with an authorization
   code.
3. **Token exchange.** The backend exchanges the code for an access token
   and a refresh token, scoped to `transactions:read` (exact scope name to
   be confirmed against the sandbox — Moneyhub's docs use
   `accounts:read`/`transactions:read`-style granular scopes per data
   cluster).
4. **Token refresh.** Access tokens are short-lived; the refresh token is
   used to mint new access tokens without re-prompting the user, until the
   user revokes consent or the refresh token itself expires (Open Banking
   consents typically require re-authorization every 90 days per the UK
   Open Banking standard).
5. **Transaction pull.** Authenticated `GET` calls against the transactions
   endpoint, scoped to the connected account(s).

This is a per-owner consent grant, not a single shared credential — each
AllotMint owner who wants Moneyhub import must go through step 2 themselves.
That has UX and multi-tenant storage implications for #3425 (one token set
per owner, not one for the whole app).

## Secret storage decision

Follow the existing `ssm://` pattern in
[`backend/common/storage.py`](../backend/common/storage.py) rather than
inventing a new secret-loading mechanism — this repo's `cdk/` has no
existing `secretsmanager`/`ssm` constructs to copy, but the backend already
has a working pluggable JSON storage abstraction selected by URI scheme:

- `file://` — local file (tests/dev)
- `s3://bucket/key.json` — S3 object
- `ssm://parameter-name` — SSM Parameter Store, via
  `ParameterStoreJSONStorage` (`backend/common/storage.py:86-112`), which
  calls `boto3.client("ssm").get_parameter(..., WithDecryption=True)` on
  read and `put_parameter(..., Type="String", Overwrite=True)` on write.

**Decision:** store each owner's Moneyhub OAuth token set (access token,
refresh token, expiry, connected account IDs) as one JSON blob per owner
under an `ssm://` parameter, e.g. `ssm:///allotmint/moneyhub/tokens/{owner}`,
loaded through `get_storage()` exactly like the alerts module already does.
Two changes needed on top of the existing abstraction (out of scope for this
spike, listed for #3425):

- `ParameterStoreJSONStorage` should use `Type="SecureString"` (not
  `String`) when persisting token material — the current alerts use case
  doesn't carry secrets, so this wasn't needed before.
- A CDK `StringParameter`/`Secret` construct and IAM grant so the Lambda
  execution role can read/write the `/allotmint/moneyhub/*` parameter
  namespace — there is no existing CDK precedent for this in `cdk/stacks/`,
  so it is new construct work, not a copy of an existing pattern.

Token refresh should happen lazily on read (check expiry, refresh if
needed, write back the updated blob) rather than a separate scheduled job,
consistent with how the rest of the backend has no background workers.

## Field-mapping plan: Moneyhub → AllotMint `Transaction`

AllotMint's transaction model is `Transaction` in
[`backend/routes/transactions.py:33-57`](../backend/routes/transactions.py).
Provider-specific import already follows a plugin pattern — see
`backend/importers/__init__.py` (`_IMPORTER_PATHS` dict) and
`backend/importers/degiro.py` for a worked example — so a `moneyhub`
importer added in #3425 should register itself the same way as `degiro` and
`hargreaves` do, rather than introducing a new import mechanism.

Moneyhub's transaction resource (per their public Open Banking-derived
schema) exposes roughly: `id`, `accountId`, `amount` (with `currency`),
`description`, `date`, `category`, `status` (`posted`/`pending`), and
`merchant`/`counterparty` info. Proposed mapping to `Transaction`:

| Moneyhub field | AllotMint `Transaction` field | Notes |
| --- | --- | --- |
| `id` | `id` | Prefix with `moneyhub:` or similar to keep IDs unambiguous across providers — AllotMint's own `id` format is `{owner}:{account}:{index}`, so the raw Moneyhub ID should go in a preserved field, not overwrite the position-based `id`. |
| `accountId` | `account` | Requires a mapping table from Moneyhub account IDs to AllotMint `account` slugs — no automatic correspondence exists; likely a one-time manual link step per connected account. |
| `date` | `date` | Both ISO 8601; direct copy. |
| `amount.amount` + `amount.currency` | `amount_minor`, `currency` | Moneyhub amounts are typically decimal major units; convert to minor units (pence/cents) to match `amount_minor`'s existing convention (see `docs/transactions.md`). |
| `description` | `comments` | Free text, direct copy. |
| `category` | *(no direct field)* | AllotMint's `Transaction` has no spend-category field — it's an investment-transaction model (`ticker`, `shares`, `type: BUY/SELL`), not a bank-statement model. Category would need to go in `comments` or be dropped, pending a decision on whether Moneyhub cash-account transactions (non-investment) are even in scope. |
| `status` | *(no direct field)* | `pending` transactions should likely be excluded from import until `posted`, to avoid double-counting when the pending transaction later settles under a different Moneyhub `id`. |
| — | `ticker`, `type` (`BUY`/`SELL`), `shares` | **No direct source.** Moneyhub's Open Banking data is bank/current-account transaction data (payments, direct debits, card spend), not brokerage trade data with tickers and share counts. If the target accounts are ISA/SIPP dealing accounts, Moneyhub likely cannot see the underlying trades at all — only cash movements into/out of the account. This is the single biggest open question for #3425: confirm during sandbox testing whether Moneyhub-connected accounts return investment trade detail or only cash-level transactions, since it changes the entire scope of the mapping. |
| — | `synthetic` | Leave `false`; this flag marks derived/computed rows elsewhere in the model, not imported ones. |

**Key open question for #3425**, to be resolved once sandbox access exists:
Moneyhub is a cash/bank-account aggregator by design. Unless a specific
Moneyhub data cluster exposes brokerage-level trade detail (ticker, units,
price), this integration likely maps cleanly onto AllotMint's `kind:
"account"` cash-movement transactions but *not* onto `kind: "portfolio"`
share trades. That should be confirmed against a real sandbox response
before #3425 starts, since it determines whether Moneyhub import is a
cash-reconciliation feature or a trade-import feature.

## Handoff to a human

To close out the remaining success criteria in #2749:

1. Register an AllotMint OAuth2 client with Moneyhub and obtain sandbox
   credentials (`client_id`, `client_secret`, redirect URI approval).
2. Complete one user-consent flow against the sandbox and capture a real
   transaction list response — confirm field names against the table above
   and answer the cash-vs-trade-data question.
3. Store the sandbox credentials via `ssm://` per [Secret storage
   decision](#secret-storage-decision) (SecureString) and hand the parameter
   name to the agent implementing #3425.

## #3425 implementation status

The importer infrastructure described above has been built against the
field-mapping plan and auth flow decided here, ahead of real sandbox access
(tracked in #3425):

- [`backend/integrations/moneyhub_api.py`](../backend/integrations/moneyhub_api.py) —
  stateless OAuth2 HTTP client (`refresh_access_token`, `fetch_transactions`)
  against `https://api.moneyhub.co.uk`.
- [`backend/common/moneyhub_tokens.py`](../backend/common/moneyhub_tokens.py) —
  per-owner token storage via the `ssm://` scheme
  (`/allotmint/moneyhub/tokens/{owner}` by default, overridable via
  `MONEYHUB_TOKENS_STORAGE_URI` for tests/local dev), with lazy refresh-on-read.
- [`backend/importers/moneyhub_api.py`](../backend/importers/moneyhub_api.py) —
  maps raw API transaction records onto `Transaction` (`kind="account"`,
  `external_id` prefixed `moneyhub:`, pending transactions excluded), reusing
  the same `dedupe_against_existing` helper #3426's CSV importer uses.
- `POST /transactions/import/moneyhub` (`backend/routes/transactions.py`) —
  pulls an owner's transactions live and persists new ones through the same
  `_persist_transaction` path as the file-upload importer.

**Still blocked on the human prerequisite above**: this was built against
the documented-but-unconfirmed Moneyhub schema (`id`, `accountId`, `date`,
`amount.amount`/`amount.currency`, `description`, `category`, `status`), and
tests mock the HTTP layer rather than hitting a real sandbox. Once real
sandbox credentials and a sample response exist, verify the field names and
the cash-vs-trade-data question above, and adjust the mapping in
`backend/importers/moneyhub_api.py` if they differ. The CDK `StringParameter`
construct and IAM grant for the `/allotmint/moneyhub/*` namespace, and the
account-id linking table (Moneyhub `accountId` → AllotMint account slug),
remain open follow-up work.
