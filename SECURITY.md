# Security

## Content Security Policy

AllotMint's frontend is served from S3 behind CloudFront. Implementing a Content Security Policy (CSP) header limits the sources the browser may load resources from. The stack currently does **not** set a CSP header, so browsers accept resources from any origin.

A restrictive policy might look like:

```
default-src 'self';
img-src 'self' data:;
script-src 'self';
style-src 'self' 'unsafe-inline';
connect-src 'self' https://www.alphavantage.co;
frame-ancestors 'none';
```

This would prevent third‑party scripts or styles from executing unless explicitly whitelisted.

### Adding or updating the policy

To enforce a CSP:

1. Define a CloudFront response headers policy (or function) in `cdk/stacks/static_site_stack.py` that sets the `content-security-policy` header.
2. Add your directives to the header string.
3. Associate the policy with the distribution's behavior and redeploy:
   ```bash
   cd cdk
   cdk deploy StaticSiteStack
   ```

For temporary local testing you may instead inject a `<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but prefer the header-based policy in production.
