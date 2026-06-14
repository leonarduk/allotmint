# Authentication

AllotMint supports two identity providers: Google and AWS Cognito. Both converge on the same backend JWT that protects API endpoints.

## Google (default)

1. The frontend renders a Google One Tap / Sign-In button via the Google Identity SDK.
2. On success, Google returns an ID token to the browser.
3. The frontend POSTs `{ id_token }` to `POST /token`.
4. The backend verifies the token with Google's JWKS, checks the allowed-emails list, and returns a short-lived backend JWT.
5. All subsequent API calls include the backend JWT as `Authorization: Bearer <token>`.

## AWS Cognito (hosted UI / PKCE)

The Cognito flow uses PKCE to avoid exposing client secrets in the browser. It is enabled by setting `awsUiAuth.enabled = true` in `config.json`.

### Flow

```
Browser                        Cognito Hosted UI          Backend
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
  │                                   │                     │
  │── POST /token/cognito { id_token, client_id } ─────────►│
  │◄─────────────────── { access_token: <backend-jwt> } ────│
  │   setAuthToken(backend-jwt)       │                     │
  │                                   │                     │
  │── GET /owners  Authorization: Bearer <backend-jwt> ────►│
```

### Key implementation points

- **`frontend/src/awsUiAuth.ts`** — handles the entire PKCE redirect/callback loop. After the Cognito code exchange it stores the Cognito session in `sessionStorage` (tab-scoped; cleared on close). `getStoredCognitoIdToken()` exposes the token to the bootstrap layer.
- **`frontend/src/main.tsx`** — `exchangeCognitoForBackendToken()` runs after `ensureAwsUiAuth` returns. It reads the stored Cognito ID token and exchanges it for a backend JWT via `POST /token/cognito`, then calls `setAuthToken`.
- **`backend/auth.py`** — `verify_cognito_token()` validates the Cognito ID token against the issuer's JWKS endpoint. The `PyJWKClient` is cached per issuer in `_jwks_clients` to avoid a round-trip to the JWKS URL on every request.
- **`backend/app.py`** — `POST /token/cognito` accepts `{ id_token, client_id }`, delegates to `verify_cognito_token`, enforces the allowed-emails list, and returns a backend JWT in the same shape as the Google endpoint. This endpoint was added to `main` in PR #2896 (merged before this PR) and is present in the codebase; this PR wires the frontend caller.

### config.json fields

| Field | Description |
|---|---|
| `awsUiAuth.enabled` | `true` or `"true"` to enable Cognito auth |
| `awsUiAuth.domain` | Cognito hosted UI base URL (e.g. `https://my-pool.auth.eu-west-2.amazoncognito.com`) |
| `awsUiAuth.clientId` | Cognito app client ID |
| `awsUiAuth.redirectPath` | Optional redirect path after login (default `/`) |

### Security notes

- Cognito tokens are stored in `sessionStorage` only (cleared on tab close).
- The backend JWT is stored in `localStorage` via `setAuthToken` (consistent with the Google flow).
- The allowed-emails list is enforced server-side in `verify_cognito_token` → `_authorize_email`.
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
