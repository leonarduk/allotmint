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
