# Security

To report a vulnerability, see [.github/SECURITY.md](../.github/SECURITY.md).

## AWS-hosted UI authentication

The AWS static site stack protects the hosted frontend with an Amazon Cognito user pool and hosted UI. `StaticSiteStack` creates the user pool, a public SPA client that uses the OAuth 2.0 authorization-code flow with PKCE, and a Cognito domain. The deployed `/config.json` includes the Cognito domain and client ID so the React app redirects unauthenticated visitors before rendering the portfolio dashboard.

After deploying `StaticSiteStack`, create or invite users in the `UiAuthUserPoolId` output before sharing the CloudFront URL. Self sign-up is disabled, so only administrator-created Cognito users can pass the UI gate.

Useful outputs:

```bash
aws cloudformation describe-stacks --stack-name StaticSiteStack \
  --query "Stacks[0].Outputs[?starts_with(OutputKey, 'UiAuth')].[OutputKey,OutputValue]" \
  --output table
```

## Content Security Policy

AllotMint's frontend is served from S3 behind CloudFront. The static-site CDK stack attaches a CloudFront response headers policy that emits a restrictive Content Security Policy (CSP) for the SPA. The policy allows same-origin resources by default, Google Identity Services for sign-in, the deployed backend API, and Cognito hosted UI/token exchange requests.

The deployed CSP is defined in `cdk/stacks/static_site_stack.py` and has this shape:

```text
default-src 'self';
script-src 'self' https://accounts.google.com/gsi/client;
frame-src 'self' https://accounts.google.com/gsi/;
connect-src 'self' {BackendApiUrl} https://*.amazoncognito.com;
frame-ancestors 'none';
object-src 'none';
base-uri 'self';
```

`{BackendApiUrl}` is a documentation placeholder for the CloudFormation `BackendApiUrl` parameter. Deployment workflows pass the Backend Lambda stack's `BackendApiUrl` output to that parameter, and CloudFormation substitutes the exact API Gateway URL into the CloudFront response headers policy at deploy time (for example, `https://abc123.execute-api.eu-west-1.amazonaws.com`). The CDK parameter rejects non-empty values that do not start with `https://`, so deploy-time overrides must include the scheme.

Note: `https://*.amazoncognito.com` is required for the PKCE token exchange because the Cognito hosted UI token endpoint (`/oauth2/token`) lives under `amazoncognito.com`, not `amazonaws.com`.

### Why API Gateway cannot use a wildcard CSP source

API Gateway URLs include the API ID and the AWS region in different hostname labels:

```text
https://{api-id}.execute-api.{region}.amazonaws.com
```

A static wildcard cannot substitute for the `BackendApiUrl` parameter:

- `https://*.execute-api.*.amazonaws.com` is invalid CSP syntax because CSP only permits wildcards as the leftmost hostname label, so browsers ignore that source expression.
- `https://*.execute-api.amazonaws.com` is syntactically valid but does not match regional API Gateway hostnames such as `abc123.execute-api.eu-west-1.amazonaws.com`.
- `https://*.amazonaws.com` is syntactically valid but too broad because it permits any AWS service endpoint under `amazonaws.com`.

Use the dynamic `BackendApiUrl` parameter instead of any `*.amazonaws.com` pattern when adding or updating frontend API connectivity. This keeps `connect-src` pinned to the exact API origin the frontend is configured to call.

### Adding or updating the policy

To update the CSP:

1. Edit the CloudFront response headers policy in `cdk/stacks/static_site_stack.py`.
2. Add the minimum directive needed for the new integration.
3. Keep the backend API entry in `connect-src` tied to the `BackendApiUrl` parameter.
4. Update `cdk/tests/test_static_site_stack.py` if the expected directives change.
5. Run the CDK static site tests and redeploy with an HTTPS backend URL parameter, for example:
   ```bash
   PYENV_VERSION=3.11.15 pytest cdk/tests/test_static_site_stack.py -v
   cd cdk
   npx cdk deploy StaticSiteStack \
     --parameters StaticSiteStack:BackendApiUrl=https://abc123.execute-api.eu-west-1.amazonaws.com
   ```

For temporary local testing you may instead inject a `<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but prefer the header-based policy in production.

## Backend API authentication — trust boundary

The backend Lambda sets `DISABLE_AUTH=true` in production. This means FastAPI does not independently validate the Cognito JWT; it trusts API Gateway's `HttpUserPoolAuthorizer` to reject requests that lack a valid token before they reach the Lambda.

**Known risk:** This is a trust-delegation architecture. If the Lambda is invoked through any path that bypasses API Gateway — a Lambda function URL, a direct `Invoke` API call, a VPC endpoint, or a misconfigured API Gateway route — the backend will accept all requests with no authentication check.

**Mitigations in place:**

- The Lambda has no function URL configured.
- IAM permissions restrict direct invocation to the API Gateway service principal only.
- Both API Gateway routes (`/` and `/{proxy+}`) attach the Cognito JWT authorizer — there is no unprotected route.

**If you need an additional layer of defense:** implement Cognito RS256 signature verification directly in FastAPI using the JWKS endpoint (`/.well-known/jwks.json`) from the Cognito user pool. Libraries such as `python-jose` or `cognitojwt` can validate the token without a network round-trip to Cognito after the first JWKS fetch. This would ensure the Lambda itself rejects requests even if API Gateway is bypassed.
