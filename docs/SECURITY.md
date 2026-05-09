# Security

## Content Security Policy

AllotMint's frontend is served from S3 behind CloudFront. The static site stack sets a Content Security Policy (CSP) header to limit the sources the browser may load resources from.

The deployed CloudFront policy is:

```
default-src 'self';
script-src 'self' https://accounts.google.com/gsi/client;
frame-src 'self' https://accounts.google.com/gsi/;
connect-src 'self' {BackendApiUrl} https://*.amazoncognito.com;
frame-ancestors 'none';
object-src 'none';
base-uri 'self';
```

`{BackendApiUrl}` is replaced at deploy time by the CloudFormation `BackendApiUrl` parameter (e.g. `https://abc123.execute-api.eu-west-1.amazonaws.com`). This produces the narrowest possible `connect-src` — pinned to the exact API origin the app uses.

A static wildcard cannot substitute for this parameter. API Gateway URLs have the form `{api-id}.execute-api.{region}.amazonaws.com`. The CSP spec only permits wildcards as the leftmost hostname label, so patterns like `*.execute-api.*.amazonaws.com` are invalid and silently ignored by browsers. The next valid option (`*.amazonaws.com`) is too broad — it covers every AWS service endpoint. Injecting the exact URL avoids both problems.

The `connect-src` directive also permits `https://*.amazoncognito.com` for the Cognito hosted UI and token exchange endpoints.

### Adding or updating the policy

To enforce a CSP:

1. Define a CloudFront response headers policy (or function) in `cdk/stacks/static_site_stack.py` that sets the `content-security-policy` header.
2. Add your directives to the header string.
3. Associate the policy with the distribution's behavior and redeploy:
   ```bash
   npm ci
   cd cdk
   npx cdk deploy StaticSiteStack
   ```

For temporary local testing you may instead inject a `<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but prefer the header-based policy in production.
