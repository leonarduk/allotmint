# Authentication

AllotMint supports two identity providers, Google and AWS Cognito, plus a
third, additive path: a scoped, read-only **demo link** (see [Demo link
(scoped read-only token)](#demo-link-scoped-read-only-token) below). The demo
link is **not** an identity provider — it never satisfies `_allowed_emails()`,
and it does not interact with `disable_auth` or `ALLOWED_EMAILS` at all; treat
it as a narrow, additive read-only carve-out layered on top of the two real
identity providers, not a third way to "log in".

The two identity providers protect the API differently:

- **Google** issues an ID token that the backend exchanges for a short-lived
  **backend HS256 JWT**, which FastAPI verifies on each request. This is the
  local / non-gateway path.
- **AWS Cognito** (deployed path) sends the **Cognito ID token** directly as the
  `Authorization: Bearer` header. API Gateway's Cognito JWT authorizer validates
  it before the request ever reaches the Lambda; the backend JWT is not used.

## Google (default)

1. The frontend renders a Google One Tap / Sign-In button via the Google Identity SDK.
2. On success, Google returns an ID token to the browser.
3. The frontend POSTs `{ id_token }` to `POST /token`.
4. The backend verifies the token with Google's JWKS, checks the allowed-emails list, and returns a short-lived backend JWT.
5. All subsequent API calls include the backend JWT as `Authorization: Bearer <token>`.

## AWS Cognito (hosted UI / PKCE)

The Cognito flow uses PKCE to avoid exposing client secrets in the browser. It is enabled by setting `awsUiAuth.enabled = true` in `config.json`.

### Flow

The Cognito ID token is sent **directly** to API Gateway. There is no backend
JWT exchange on this path — the gateway authorizer (`GatewayAuthorizerLambda`,
see "Deployed-gateway auth: the demo/Cognito Lambda authorizer" below) checks
the ID token's signature and `aud` claim against the UI app client ID, so the
token issued by Cognito is exactly what the authorizer expects.

```
Browser                        Cognito Hosted UI          API Gateway + Lambda
  │                                   │                     │
  │── bootstrapRuntimeConfig ─────────►                     │
  │   ensureAwsUiAuth()               │                     │
  │── redirect to /oauth2/authorize ──►                     │
  │                         user logs in                    │
  │◄── redirect back with ?code= ─────│                     │
  │   exchangeCode() (PKCE)           │                     │
  │── POST /oauth2/token ─────────────►                     │
  │◄── { id_token, access_token } ────│                     │
  │   storeSession() → sessionStorage │                     │
  │   applyCognitoIdToken()           │                     │
  │   setAuthToken(id_token)          │                     │
  │                                   │                     │
  │── GET /owners  Authorization: Bearer <cognito-id-token> ───────────────────►│
  │      (gateway authorizer validates aud == UI client ID, then invokes Lambda) │
```

> **Why the ID token, not the access token?** The gateway authorizer
> (`backend.auth.is_cognito_id_token`) matches the token's `aud` claim against
> the configured UI app client ID (`UiAuthUserPoolClientId`, passed through as
> the `UI_AUTH_USER_POOL_CLIENT_ID` env var — see
> `cdk/stacks/backend_lambda_stack.py`). Cognito sets `aud` on the **ID
> token**; access tokens carry `client_id` instead and have no `aud`, so
> sending the access token here would fail authorization.

### Token expiry / refresh

Cognito ID tokens are short-lived (~1h), so the Authorization header is kept
fresh two ways:

- **Silent in-session refresh.** The authorization-code grant returns a
  `refresh_token` (stored in the session alongside the ID/access tokens).
  `main.tsx` `scheduleCognitoRefresh()` arms a timer to fire ~5 minutes before
  expiry; it calls `refreshCognitoSession()` (`awsUiAuth.ts`), which POSTs
  `grant_type=refresh_token` to the hosted UI's `/oauth2/token` endpoint, stores
  the new ID/access tokens (preserving the refresh token, which Cognito does not
  re-issue), re-applies the fresh ID token via `setAuthToken`, and re-arms the
  timer. If a refresh fails (e.g. the refresh token has expired), the session is
  cleared and the app logs out so the next load restarts the hosted-UI login.
- **Bootstrap fallback.** On page load `ensureAwsUiAuth()` treats a session
  within 60s of expiry as invalid (`hasValidSession()`) and redirects back to the
  hosted UI to re-issue tokens before `applyCognitoIdToken()` runs.

### Key implementation points

- **`frontend/src/awsUiAuth.ts`** — handles the entire PKCE redirect/callback loop. After the Cognito code exchange it stores the Cognito session in `sessionStorage` (tab-scoped; cleared on close). `getStoredCognitoIdToken()` exposes the token to the bootstrap layer.
- **`frontend/src/main.tsx`** — `applyCognitoIdToken()` runs after `ensureAwsUiAuth` returns. It reads the stored Cognito ID token and applies it directly as the API auth token via `setAuthToken`, which attaches it as `Authorization: Bearer` on every API call. No `POST /token/cognito` exchange happens on the deployed path.
- **`backend/app.py` / `backend/auth.py`** — `POST /token/cognito` (which exchanges a Cognito token for a backend HS256 JWT via `verify_cognito_token`) still exists for any non-gateway use, but the deployed frontend no longer calls it: against the API Gateway authorizer the backend JWT cannot be validated. The Google path (`POST /token`) continues to use the backend HS256 JWT against the FastAPI-enforced (non-gateway) setup.

> **Local development note:** The ID-token-direct flow requires API Gateway's
> Cognito JWT authorizer. Local testing of the Cognito authentication path is
> not supported without a local API Gateway instance. For local development, use
> the Google authentication flow instead.

### config.json fields

| Field | Description |
|---|---|
| `awsUiAuth.enabled` | `true` or `"true"` to enable Cognito auth |
| `awsUiAuth.domain` | Cognito hosted UI base URL (e.g. `https://my-pool.auth.eu-west-2.amazoncognito.com`) |
| `awsUiAuth.clientId` | Cognito app client ID |
| `awsUiAuth.redirectPath` | Optional redirect path after login (default `/`) |

### Security notes

- The authoritative Cognito session (`id_token` + `access_token` + `refresh_token` + expiry) is held in `sessionStorage` only (tab-scoped, cleared on close). The refresh token enables silent in-session renewal but never leaves `sessionStorage` except as the body of the `/oauth2/token` refresh request.
- `applyCognitoIdToken()` additionally mirrors the **ID token** into `localStorage` via `setAuthToken` so the API client can attach it as `Authorization: Bearer` (consistent with how the Google flow stores its backend JWT). On a fresh tab a stale `localStorage` copy is never used for an API call: with no `sessionStorage` session, `ensureAwsUiAuth()` redirects to the hosted UI to obtain a fresh token before anything renders.
- The allowed-emails list is enforced at the gateway/Cognito layer (the authorizer only admits tokens from the configured user pool / client) on the deployed path, and server-side in `verify_cognito_token` → `_authorize_email` for the `POST /token/cognito` exchange.
- The JWKS issuer is validated to start with `cognito-idp.` and end with `.amazonaws.com` to prevent attacker-controlled JWKS endpoints.
- A third, additive identity type also exists — the demo link (short-lived,
  read-only, single-owner). See [Demo link (scoped read-only
  token)](#demo-link-scoped-read-only-token) below. It never satisfies
  `_allowed_emails()` and is never treated as a Cognito (or Google) identity
  by any code path here.

## Demo link (scoped read-only token)

A third, additive identity path: a signed, short-lived token that grants
read-only access to a single, pre-designated "demo" owner without going
through Google or Cognito. It is not an identity provider — it does not
touch `disable_auth`, `ALLOWED_EMAILS`, or either flow above, and (unlike
either of those) it can only ever resolve to one specific, config-designated
owner, never an arbitrary caller. See #7402 for the original design and
#7404–#7411 for the implementation steps referenced below.

### Claim shape, and where it's minted/verified

A demo token is an HS256 JWT signed with the same `SECRET_KEY` as every other
backend JWT (`backend/auth.py:40-51`), but carries a distinct claim shape:

```json
{ "scope": "demo-readonly", "owner": "<demo_link_owner>", "exp": <unix-timestamp> }
```

- `create_demo_access_token(owner, expires_delta)` (`backend/auth.py:290`)
  mints it. It deliberately never sets `sub` (or any claim
  `_user_from_token`/`_resolve_identity_when_auth_disabled` would treat as an
  email/username).
- `decode_demo_token(token)` (`backend/auth.py:310`) verifies the signature,
  `exp`, and that `scope == "demo-readonly"`, returning a
  `DemoTokenClaims(owner, scope)` or `None` — never raising, so callers can
  chain it after/alongside `decode_token()`.
- Crucially, `decode_token(token)` (`backend/auth.py:237`) — the normal
  backend-JWT verifier every other identity path calls — explicitly returns
  `None` for a well-signed demo token (`backend/auth.py:255-256`) rather than
  handing back its (absent) `sub`. This is the single control that keeps a
  demo token from ever traversing `_user_from_token` (`backend/auth.py:395`)
  or `_resolve_identity_when_auth_disabled` (`backend/auth.py:425`) as if it
  were a real login — both treat any non-empty return value as a fully
  authenticated identity.

### Identity resolution

`_resolve_demo_request(token)` (`backend/auth.py:476`) is the demo-specific
resolution path, tried first — and independently of `config.disable_auth` —
by both `get_current_user` (`backend/auth.py:515`) and `get_active_user`
(`backend/auth.py:717`):

1. Not a demo token at all → returns `None`; both callers fall through to
   their normal Google/Cognito/disable_auth resolution, untouched.
2. A demo token, but `config.demo_link_enabled` is `False` → `401 Invalid
   authentication credentials`. This is the real kill switch: flipping the
   config flag off stops the token being accepted immediately, even though
   the token itself hasn't expired.
3. A demo token whose `owner` claim doesn't match the configured
   `config.demo_link_owner` → also `401` (covers a token minted for a now
   different owner, or minted before the config changed).
4. Otherwise: sets `current_user` to the demo owner and `demo_readonly` (a
   `ContextVar`, reset to `False` at the top of *every* request regardless of
   whether it's a demo request — see the docstring at `backend/auth.py:68-81`
   on why a Lambda's potentially-reused execution environment makes that
   reset mandatory rather than relying on the ContextVar default) to `True`,
   and returns the owner id.

`is_demo_request()` (`backend/auth.py:85`) is the read used by every
downstream enforcement point below.

### Enforcement gate 1 — the global scope/write-blocking middleware

`demo_scope_gate` (`backend/bootstrap/middleware.py:86`, named
`demo_write_gate` before a same-day production incident forced a redesign —
see below), registered for every request, has two jobs:

1. **Resolve demo identity for every request.** Sets the `current_user`/
   `demo_readonly` ContextVars from a valid demo-scoped token, exactly as
   `get_current_user`/`get_active_user` do — but unconditionally, before
   FastAPI dispatches to any handler.
2. Rejects any non-safe HTTP method carried by a demo-scoped token with
   `403 "Demo access is read-only"`. `_SAFE_METHODS`
   (`backend/bootstrap/middleware.py:39`) is `{GET, HEAD, OPTIONS}` — a
   safelist, not a denylist, so a future new mutating verb is rejected by
   default instead of accidentally allowed.

Both exist as *global* gate logic rather than a per-route dependency because
router registration in this app is not uniform:
`backend/bootstrap/routers.py:56-109` registers several routers (e.g.
`transactions_router`) with no router-level `Depends(auth.get_current_user)`
at all, and `ensure_owner_access` (below) is called from only a handful of
modules. A single check here is enforced regardless of which router or
handler the request eventually reaches.

Because this runs as HTTP middleware, it executes *before* FastAPI resolves
dependencies — so the `demo_readonly` ContextVar set by
`get_current_user`/`get_active_user` isn't populated yet when this runs. The
middleware therefore independently decodes the raw `Authorization` bearer
header with `decode_demo_token` itself, and does so **regardless of
`config.disable_auth`** — a syntactically valid demo token (one signed with
this process's own `SECRET_KEY`) must never reach a mutating handler under
any configuration, including one where the feature has since been disabled.
(`decode_demo_token` itself is scope-only; the identity-resolution half below
still separately enforces `config.demo_link_enabled` and the owner match via
`_resolve_demo_request`, and does 401 once the feature is disabled — only the
raw-token *decode* used for the write-block ignores that flag, since a
disabled deployment must still block a leaked token from writing.)

**Why identity resolution moved into this middleware (#7522 follow-up,
same-day incident).** The gate originally (this section, before the
incident) only performed job 2 above — the write-block — reasoning that
"the demo_readonly ContextVar isn't populated yet" here so identity
resolution had to stay in `get_current_user`/`get_active_user`. That
reasoning covered the write-block correctly (middleware can independently
decode the token for that one check) but missed a bigger structural problem:
**many GET routes never invoke `get_current_user`/`get_active_user` as a
dependency at all**, on the actual deployed Lambda. Router-level
`dependencies=protected` in `backend/bootstrap/routers.py:56-109` is `[]`
whenever `config.disable_auth` is true (`protected = [] if
cfg.disable_auth else [Depends(auth.get_current_user)]`) — and it is true on
every real AWS deployment, since API Gateway is the auth boundary there
(`DISABLE_AUTH=true` is set on the Lambda for exactly that reason — see
"Deployed-gateway auth" below). Several individual handlers don't declare the
dependency themselves either: `GET /owners`'s `disable_auth` branch
(`backend/routes/portfolio.py:503-509`) takes no `current_user` parameter,
and every route under `GET /portfolio-group/{slug}` (the default "all
owners" landing dashboard) never resolves identity at all. For any of these,
`_resolve_demo_request` was simply never called, so `is_demo_request()`
stayed `False`, and every check built on it downstream — `ensure_owner_access`
(gate 2, below), `_list_aws_plots`/`_list_local_plots`'s demo filtering — was
a silent no-op. Confirmed live, the day this shipped: a minted demo-link
token could read every real owner's full portfolio (holdings included) via
the default landing dashboard and via `GET /owners`, not just the configured
demo owner. Moving identity resolution into this middleware — which,
unlike a FastAPI dependency, is guaranteed to run for literally every
request regardless of a route's own wiring — closes the gap at its root
instead of chasing individual routes. `get_current_user`/`get_active_user`
still call `_resolve_demo_request` themselves too (harmless and idempotent
for an already-valid token); they remain the *only* path for two flows
that never pass through this middleware's demo-token branch in the same
way — Google-token identity resolution, and the `disable_auth`-with-no-token
local-dev fallback — neither of which this middleware's demo-specific
branch touches.

### Enforcement gate 2 — per-owner scoping

`ensure_owner_access(identity, owner, ...)` (`backend/common/authz.py:69`)
checks `is_demo_request()` first, before its `config.disable_auth` no-op: a
demo request is allowed only when `owner` matches `config.demo_link_owner`
(a config comparison, not a `person.json` `viewers` lookup — a `viewers`
entry that happens to equal the demo owner id cannot widen access), and
denied — `403 "Not authorized for this owner"`, via `PermissionDeniedError`
— for every other owner. This ordering matters: the deployed Lambda runs
with `disable_auth` true (API Gateway's Cognito authorizer is the real gate
there — see below), so without this check running first, a demo token would
inherit the `disable_auth` no-op and see every owner.

The `/owners` listing applies the same rule directly rather than going
through `ensure_owner_access`, since it isn't a per-owner endpoint:
`_list_local_plots` (`backend/common/data_loader.py:525`, demo check around
`:550-561`) and `_list_aws_plots` (`backend/common/data_loader.py:833`, demo
check around `:862-871`) both check `is_demo_request()` before their own
`disable_auth`/viewer filtering and, when true, return a listing containing
at most the single configured demo owner.

### Config

| Field | Default | Description |
|---|---|---|
| `demo_link_enabled` | `False` | Master kill switch. Ships **off** — this whole feature is inert on any deployment that hasn't explicitly opted in. Checked both when a token is minted and, independently, every time one is used (`_resolve_demo_request`). |
| `demo_link_owner` | `None` | The single owner id a demo token may read. Required (non-empty) for both minting and use — an unset value returns `503` from the mint endpoint (below) and `401` from every use path. |
| `demo_link_ttl_hours` | `72` | Hours until a freshly-minted token's `exp`. Applied at mint time via `create_demo_access_token`; changing it does not retroactively affect already-minted tokens. |
| `demo_link_mint_rate_limit` | `"5/minute"` | Per-IP rate limit on `POST /demo-link`, enforced the same way as `config.signup_rate_limit`. |

(`backend/config.py:137-155`; see also `config.example.yaml`.)

### Minting a token — `POST /demo-link`

Admin-gated (`backend/app.py:285`): `Depends(require_admin)`
(`backend/app.py:97`), the same dependency guarding `/whoami` and
`/api-console`. `require_admin` has a documented local-dev quirk
(`backend/app.py:97-111`): with no `ADMIN_EMAILS` configured *and*
`disable_auth` true, it lets the request through with `current_user is None`
rather than raising. That's acceptable for a read-only debug endpoint, but
not for a token mint on a deployed box, so `mint_demo_link` layers a second,
independent check on top: `config.demo_link_enabled` must also be true, or
the endpoint returns `404 "Not Found"` (rather than `403`) — a deployment
that hasn't opted in doesn't even reveal the endpoint exists.

- `503 "Demo link owner is not configured"` when `config.demo_link_owner` is
  unset.
- On success, returns `{ token, expires_at, owner }` (`DemoLinkResponse`,
  `backend/app.py:45`); `expires_at` is decoded back out of the freshly
  signed token's own `exp` rather than independently recomputed, so it's
  guaranteed to match what the token actually carries.
- The mint is logged at `info` level (owner and TTL only — never the token
  itself).

### Frontend — `/demo?token=...`

`applyDemoTokenFromUrl()` (`frontend/src/demoAuth.ts:22`) detects a
`/demo?token=<...>` visit and, if a token is present, applies it via
`setAuthToken` (the same call `applyCognitoIdToken()` uses), marks the tab as
a read-only demo session in `sessionStorage` (tab-scoped, mirroring the
Cognito session), and rewrites the URL to `/` so the token never lingers in
the address bar, the tab title, or a screenshot.

This runs in `main.tsx` (`:687`) *before* `ensureAwsUiAuth()` — a demo-token
visit fully replaces the Cognito/Google bootstrap for that tab rather than
running alongside it. `demoReadOnly` (surfaced via `AuthContext` /
`useDemoReadOnly()`, `frontend/src/hooks/useDemoReadOnly.ts`) drives the
persistent `DemoReadOnlyBanner` and disables/hides individual mutating
controls app-wide (#7411). This is explicitly a UX courtesy, not the
enforcement boundary — every component using it says so in its own
docstring; the two backend gates above are what actually make a demo-scoped
token read-only, and a control that skipped the hook would still be rejected
server-side.

### Sequence

```
Admin (Cognito)          Backend                     Browser (visitor)          API Gateway + Lambda
     │                      │                             │                          │
     │── POST /demo-link ───►                             │                          │
     │   (require_admin +                                  │                          │
     │    demo_link_enabled)                                │                          │
     │◄─ { token, expires_at, owner } ─────                │                          │
     │                      │                             │                          │
     │── share link: https://…/demo?token=<token> ────────►│                          │
     │                      │      applyDemoTokenFromUrl()  │                          │
     │                      │      setAuthToken(token)      │                          │
     │                      │      sessionStorage marker    │                          │
     │                      │      URL rewritten to /       │                          │
     │                      │                             │                          │
     │                      │      GET /owners  Authorization: Bearer <demo-token> ───►│
     │                      │                             │      demo_scope_gate (middleware, resolves identity) │
     │                      │                             │      ensure_owner_access()   │
     │                      │◄──────────────── 200: demo owner only ────────────────────│
     │                      │                             │                          │
     │                      │      POST /transactions  Authorization: Bearer <demo-token> ►│
     │                      │                             │      demo_scope_gate (middleware, blocks the write) │
     │                      │◄──────────────── 403 Demo access is read-only ────────────────│
```

### Deployed-gateway auth: the demo/Cognito Lambda authorizer (#7522)

The rest of this section walks through why a demo-scoped token needed a
gateway-level fix at all, and how that fix works.

`cdk/stacks/backend_lambda_stack.py` puts every route except an explicit
bypass list (`/health`, `GET /config`, `POST /token`, `POST /token/google`,
`/signup/*`, and `OPTIONS`) behind a gateway authorizer on the `ANY /` and
`ANY /{proxy+}` catch-alls. Neither `POST /demo-link` nor the routes a demo
token is used against afterward (`GET /owners`, portfolio reads, etc.) are in
that bypass list — by design, since those routes must still require *some*
authentication. A demo-scoped token is signed with the backend's own
`SECRET_KEY` via HS256 — it is not issued by Cognito — so API Gateway's
*native* Cognito JWT authorizer (the architecture originally described
earlier in this document and in `README.md`) rejected a request bearing a
demo token *before it ever reached the Lambda* where all of the logic
described above runs. This repo's test suite (`tests/test_demo_link_mint.py`,
`tests/test_auth_demo_token.py`, `tests/test_demo_write_gate.py`) exercises
the flow through FastAPI's `TestClient` directly, which bypasses API Gateway
entirely, so it did not catch this — the feature was fully non-functional on
a real deployment beyond the six bypassed routes (issue #7522).

**The fix**: `cdk/stacks/backend_lambda_stack.py` replaces the native Cognito
`HttpUserPoolAuthorizer` on `ANY /` and `ANY /{proxy+}` with a custom
`apigwv2.HttpLambdaAuthorizer` (`GatewayAuthorizerLambda`, backed by
`backend/lambda_api/demo_authorizer.py`). Two options were on the table (see
the issue): widen the no-auth bypass list and rely solely on the app-layer
`demo_scope_gate`/`ensure_owner_access` checks, or add a Lambda authorizer
that keeps API Gateway itself as the trust boundary. The Lambda-authorizer
option was chosen — it does not widen the set of routes API Gateway lets
through unauthenticated, so a request still needs *some* valid, signed
credential before the backend Lambda ever runs.

`GatewayAuthorizerLambda` admits a request when its `Authorization: Bearer
<token>` header carries **either**:

- a demo-scoped token — verified with `backend.auth.decode_demo_token`
  (signature + `scope`/`owner` claim shape + expiry); or
- a Cognito ID token — verified with `backend.auth.is_cognito_id_token`
  (signature via the issuer's JWKS endpoint, `iss`/`aud`/`token_use`/expiry)
  against the UI app client ID and, if configured, the deploy workflow's
  smoke-test client ID.

It deliberately checks only *structural* token validity. It does **not**
re-run `_authorize_email`/`_allowed_emails()` (the S3-backed allowed-emails
allowlist) for a Cognito token, nor `_resolve_demo_request`'s
`demo_link_enabled`/`demo_link_owner` checks for a demo token — both already
run, exactly once, downstream in the backend Lambda's own
`get_current_user`/`_resolve_demo_request` regardless of what the authorizer
decides (`DISABLE_AUTH=true` only skips the backend's own *Cognito* JWT
decode, never the demo-token path — see the enforcement gates documented
above). Re-running the S3-backed allowlist check in the authorizer too would
double that cost on every single API request without adding a security
guarantee. This is also why the authorizer's result caching is disabled
(`AuthorizerResultTtlInSeconds: 0`): a cached "authorized" decision could
otherwise admit a Cognito token past its real `exp` for up to the cache TTL,
since the backend Lambda trusts the gateway authorizer's decision for a
Cognito token rather than independently re-verifying its signature/expiry.

`GatewayAuthorizerLambda` reuses the same Docker image as the backend Lambda
(a distinct entry point, `backend.lambda_api.demo_authorizer.lambda_handler`,
mirroring `PriceRefreshLambda`/`TradingAgentLambda`/etc.) so it can call
`backend.auth` directly rather than re-implementing JWT verification in a
second codebase. It receives its own `JWT_SECRET` (to verify a demo token's
HS256 signature) and the same Cognito app client ID(s) the old
`HttpUserPoolAuthorizer` validated against, but no S3 permissions — it never
calls the allowed-emails allowlist.

`POST /demo-link` itself stays exactly as before: admin-gated
(`Depends(require_admin)`) and additionally gated on
`config.demo_link_enabled`, reached via the same `ANY /{proxy+}` catch-all
and therefore the same gateway authorizer — an admin's Cognito ID token
satisfies it like any other Cognito-authenticated route.

### Revocation and blast radius

There is **no per-token revocation list**. A minted token stays valid until
exactly one of:

1. It reaches its own `exp` — `demo_link_ttl_hours` after minting (default
   72h).
2. `config.demo_link_enabled` is set to `false` and the change is deployed.
   `_resolve_demo_request` checks this on every use, so an already-issued,
   unexpired token stops being accepted immediately — but this disables
   minting *and* using demo links for every owner, not just the leaked one.
3. `JWT_SECRET` is rotated (`backend/auth.py:39-50`). This also invalidates
   every real user's backend JWT (the Google-flow path), not just demo
   tokens — a blunt instrument.

There is no narrower way to kill one specific leaked link. An operator
relying on this feature should know that going in: a leaked link stays live,
read-only, and scoped to its one owner until one of the three options above
is exercised.

### Security notes

- Short TTL by default (72h), deliberately shorter-lived than a persistent
  session: this is meant to be shared for a demo, not to be a durable login.
- Scoped to exactly one owner (`config.demo_link_owner`), enforced
  independently at two points (`_resolve_demo_request`, called
  unconditionally from `demo_scope_gate` middleware for every request, and
  `ensure_owner_access`) plus the `/owners` listing.
- Read-only, enforced by a global method safelist (`demo_scope_gate`), not
  per-route — see Enforcement gate 1 above.
- Never satisfies `_allowed_emails()` — `decode_token` returns `None` for a
  demo token, so it can never be treated as a normal authenticated identity
  by any pre-existing code path.
- Never carries a `sub`/email claim, so it cannot be mistaken for — or
  logged as — a real user identity.
- Ships disabled by default (`demo_link_enabled: false`); this entire path is
  inert on a deployment that hasn't explicitly opted in.

## Diagnosing auth failures

Auth can fail at two distinct boundaries, and each is observed differently.

### Backend token handling — `GET /whoami` (admin only)

`GET /whoami` reports what the **backend** decodes from the bearer token on the
current request:

```json
{
  "token_present": true,
  "claims": { "sub": "...", "email": "...", "exp": 0, "iss": "...", "token_use": "id", "aud": "..." },
  "allowed_email_match": true,
  "note": "Diagnoses backend token handling only. ..."
}
```

- **Admin-gated.** It is protected by the same `require_admin` dependency as
  `/api-console` (the `ADMIN_EMAILS` allowlist), so decoded claims are never
  exposed to non-admin users. It never returns the raw token, and only an
  allowlist of claims (`sub`, `email`, `exp`, `iss`, `token_use`, `aud`) is
  echoed back.
- **How to call it:** authenticate through the app as an admin (so the backend
  JWT is sent), then `GET /whoami` with `Authorization: Bearer <backend-jwt>`.
  `allowed_email_match` reflects whether the token's email is in the backend
  allowed-emails set.
- **Limitation:** when the API Gateway Cognito JWT authorizer rejects a request,
  it never reaches the Lambda — so `/whoami` cannot diagnose gateway-level 401s.
  Those are covered by access logging below.

Implemented in `backend/auth.py` (`describe_token`) and `backend/app.py`
(`GET /whoami`).

### Gateway authorizer rejections — API Gateway access logs (CloudWatch)

A request rejected by the gateway authorizer (`GatewayAuthorizerLambda`, see
above) on `ANY /`/`ANY /{proxy+}` — for example the `/owners` 401 in issue
#4256, or an invalid demo token — is returned **before** the backend Lambda
runs, so it appears in neither the Lambda logs nor `/whoami`. The HTTP API
`$default` stage is configured (in `cdk/stacks/backend_lambda_stack.py`) to
write access logs to a CloudWatch log group (`BackendApiAccessLogGroup`).
Each entry is JSON including:

| Field | `$context` source | Use |
|---|---|---|
| `status` | `$context.status` | HTTP status returned to the client |
| `routeKey` | `$context.routeKey` | Which route was hit (e.g. `GET /owners`) |
| `authorizerError` | `$context.authorizer.error` | Populated for an authorizer *error* (e.g. the old JWT authorizer's own rejections); a clean `isAuthorized: false` from GatewayAuthorizerLambda is a valid deny decision, not an error, so this field is typically empty for a gateway-authorizer 403 — `status`/`routeKey` are what to check instead |
| `errorMessage` | `$context.error.message` | Gateway-level error detail |
| `integrationStatus` | `$context.integrationStatus` | Status from the Lambda integration |

To investigate a gateway rejection: open the `BackendApiAccessLogGroup` log
group in CloudWatch and filter to the failing `routeKey`/`status` (403 from
`GatewayAuthorizerLambda`, or check `GatewayAuthorizerLambdaLogGroup` itself
for the authorizer's own CloudWatch logs — it logs an exception, never the
raw token, if it fails closed). The access-log format deliberately logs
claims/status only — the raw `Authorization` header / bearer token is never
logged.

## Account creation

### Bootstrapping the first owner account (AWS)

On a fresh AWS deployment there are no owner accounts in S3 yet, so
`_allowed_emails()` (`backend/auth.py`) — consulted by `get_current_user` /
`_resolve_identity_when_auth_disabled` on every protected route, including
Cognito-authenticated ones — has nothing to admit. Historically this meant
even the deployment's own owner got a 403 `"Unauthorized email"`, with no way
to bootstrap in: the signup-approval flow below requires already being able
to use the tool (#6130).

`_allowed_emails()` now always includes a **bootstrap allowlist** sourced from
`config.allowed_emails`, in addition to whatever is provisioned in S3/locally:

- `config.lambda.yaml`'s `auth.allowed_emails` ships with the deployment
  owner's email pre-seeded, so it works out of the box.
- Setting the `ALLOWED_EMAILS` env var (comma-separated emails) overrides the
  yaml value entirely — set it as the `ALLOWED_EMAILS` GitHub Actions secret
  to rotate the owner list without a code change; `cdk/stacks/backend_lambda_stack.py`
  passes it through to the Lambda when present.
- This is a fix, not a broadening: it is still an explicit, small allowlist —
  it does not open access to arbitrary Cognito users, and per-owner data
  access is still gated separately by `ensure_owner_access`.
- If the S3 owner listing fails (e.g. a transient AWS error), the bootstrap
  allowlist alone is still honoured rather than rejecting everyone, so a
  transient error can't lock the owner out.

This deployment's owner is pre-seeded directly in `config.lambda.yaml`, but
that's a one-time step for *this* repo, not a requirement going forward: a
future deployment (or rotating this one's owner) only needs the
`ALLOWED_EMAILS` GitHub Actions secret set, no code change.

Two distinct paths can create an owner's data directory:

### Admin-provisioned (signup-approval flow)

A visitor submits `POST /signup/request` with their email. An admin clicks the
approve link in the resulting notification email. The backend then:

1. Calls `ensure_owner_scaffold()` (`backend/common/compliance.py`) to create
   the default compliance scaffold under `data/accounts/<owner>/`.
2. Writes the visitor's email into `person.json` so that `_allowed_emails()`
   (`backend/auth.py`) admits them at login.
3. Sends the user a "login ready" email.

The account exists and the user can authenticate **before** making any write.

### Implicit (first-write path)

If a user reaches a write endpoint (`POST /transactions`, `POST /holdings/manual`)
without having been provisioned via the approval flow, `ensure_owner()`
(`backend/common/accounts_store.py`) creates a minimal `person.json` as a
side-effect. There is no dedicated `POST /accounts` endpoint. Note that
implicitly-created accounts contain no email, so `_allowed_emails()` will not
admit the user until their email is recorded — typically this only applies in
local/test environments where auth is relaxed.
