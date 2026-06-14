# Authentication

AllotMint supports two identity providers: Google and AWS Cognito. They protect
the API differently:

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
JWT exchange on this path — the gateway's Cognito JWT authorizer validates the
ID token's `aud` claim against the UI app client ID, so the token issued by
Cognito is exactly what the authorizer expects.

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

> **Why the ID token, not the access token?** The HTTP API JWT authorizer matches
> the token's `aud` claim against the configured audience
> (`cdk/stacks/backend_lambda_stack.py` → `JwtConfiguration.Audience` =
> `UiAuthUserPoolClientId`). Cognito sets `aud` on the **ID token**; access tokens
> carry `client_id` instead and have no `aud`, so sending the access token here
> would fail authorization.

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

A request rejected by the Cognito JWT authorizer at API Gateway (for example the
`/owners` 401 in issue #4256) is returned **before** the backend Lambda runs, so
it appears in neither the Lambda logs nor `/whoami`. The HTTP API `$default`
stage is configured (in `cdk/stacks/backend_lambda_stack.py`) to write access
logs to a CloudWatch log group (`BackendApiAccessLogGroup`). Each entry is JSON
including:

| Field | `$context` source | Use |
|---|---|---|
| `status` | `$context.status` | HTTP status returned to the client |
| `routeKey` | `$context.routeKey` | Which route was hit (e.g. `GET /owners`) |
| `authorizerError` | `$context.authorizer.error` | Why the JWT authorizer rejected the request |
| `errorMessage` | `$context.error.message` | Gateway-level error detail |
| `integrationStatus` | `$context.integrationStatus` | Status from the Lambda integration |

To investigate a gateway 401: open the `BackendApiAccessLogGroup` log group in
CloudWatch, filter to the failing `routeKey`, and read `authorizerError`. The
format deliberately logs claims/status only — the raw `Authorization` header /
bearer token is never logged.
