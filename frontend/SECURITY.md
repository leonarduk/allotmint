# Frontend Security Practices

## Client-Side Request Forgery (CSRF/SSRF) Prevention

### Overview
The frontend API client (`src/api.ts`) implements comprehensive protections against client-side request forgery attacks (CWE-918) to prevent malicious URL redirection or unintended API calls.

### Protection Layers

#### 1. URL Format Validation
**Location**: `validateApiBase()` function (lines 68-84)

Ensures all API base URLs:
- Are valid, parseable absolute URLs
- Use only `http://` or `https://` protocols
- Are normalized (trailing slashes removed)

This prevents attacks using:
- Invalid protocol schemes (e.g., `javascript:`, `data:`)
- Malformed URLs that could bypass security checks
- Protocol-relative URLs (e.g., `//evil.com`)

**Example Blocked URLs**:
```javascript
setApiBase("javascript:alert('xss')");      // ❌ Error: Invalid protocol
setApiBase("ftp://example.com");              // ❌ Error: FTP not allowed
setApiBase("http://evil.com");                // ✅ Valid, but later origin check blocks it
```

#### 2. Initialization-Time Validation
**Location**: Lines 94-104 (DEFAULT_API_BASE validation with IIFE)

Validates the configured API base URL immediately when the module loads, ensuring:
- Configuration errors surface early with clear error messages
- Failed initialization prevents the app from silently using a malicious base URL
- Fails fast before any API calls are made

#### 3. Runtime Validation
**Location**: `setApiBase()` function (lines 108-116)

Validates any changes to the API base URL at runtime using the same rules as startup validation, ensuring:
- Dynamic API base configuration cannot introduce vulnerabilities
- All validation rules are consistently enforced
- Clear error messages for invalid runtime changes

#### 4. Request-Level Guards
**Location**: `fetchJson()` function (lines 176-212)

Two-layer origin and path validation:

**Layer 1 - Origin Check** (lines 196-199):
```typescript
const parsedFull = new URL(fullUrl);
if (parsedFull.origin !== baseOrigin) {
  throw new Error(`Blocked request to unexpected host: ${parsedFull.origin}`);
}
```
- Prevents absolute URLs from targeting different hosts
- Blocks same-origin policy bypasses
- Stops open redirect attacks that switch domains

**Layer 2 - Path-Prefix Check** (lines 205-212):
```typescript
const allowedPathPrefix = new URL(allowedPrefix).pathname.replace(/\/+$/, "");
const requestPath = parsedFull.pathname;
if (
  !requestPath.startsWith(`${allowedPathPrefix}/`) &&
  requestPath !== allowedPathPrefix
) {
  throw new Error(`Blocked request: ${parsedFull.href} does not start with configured API base`);
}
```
- Prevents path traversal attacks using `../`
- Blocks same-origin open redirects to other application paths
- Handles trailing slash normalization correctly
- Prevents substring prefix attacks (e.g., `/api/v1` → `/api/v1other`)

### Attack Scenarios Prevented

#### Scenario 1: Absolute URL to Different Host
```javascript
// Attacker tries to redirect request to their server
await fetchJson("http://attacker.example.com/steal");
// ❌ Blocked by Layer 1 (origin check)
```

#### Scenario 2: Same-Origin Path Traversal
```javascript
// Attacker tries to access admin endpoint when API base is /api/v1
const client = createClient("http://localhost:8000/api/v1");
await client.fetchJson("http://localhost:8000/admin/steal");
// ❌ Blocked by Layer 2 (path-prefix check)
```

#### Scenario 3: Invalid Protocol
```javascript
// Attacker tries to use javascript: protocol
setApiBase("javascript:alert('xss')");
// ❌ Error thrown at startup
```

#### Scenario 4: Substring Path Match
```javascript
// Attacker tries substring prefix match
const client = createClient("http://localhost:8000/api/v1");
await client.fetchJson("http://localhost:8000/api/v1other/endpoint");
// ❌ Blocked by Layer 2 (exact slash boundary required)
```

### Test Coverage

Security tests are located in `frontend/tests/unit/api.test.ts`:

**CSRF/SSRF Guard Tests** (8 tests):
- Blocks absolute URLs to different hosts
- Allows same-origin absolute URLs
- Allows relative paths resolving to configured host
- Maintains protection after runtime API base changes
- Provides clear error messages for misconfiguration
- Handles protocol-relative URLs correctly
- Validates empty base string rejection

**Path-Prefix Guard Tests** (8 tests):
- Blocks same-origin URLs with wrong path prefix
- Prevents substring prefix bypass attacks
- Allows correct absolute URLs with proper prefix
- Normalizes trailing slashes correctly
- Allows query parameters and fragments at base URL

Run tests:
```bash
npm test -- api.test.ts
```

### CWE/CVE References

- **CWE-918**: Server-Side Request Forgery (SSRF)
- **CWE-352**: Cross-Site Request Forgery (CSRF)
- **CodeQL Alert #218**: Client-side request forgery
- **GitHub Issue #3244**: Fix CSRF vulnerability in API URL construction
- **GitHub Issue #3170**: Path-prefix SSRF guard

### Related Code

- `frontend/src/api.ts`: Main API client with security guards
- `frontend/tests/unit/api.test.ts`: Comprehensive test suite
- `frontend/src/types.ts`: Type definitions for API responses
