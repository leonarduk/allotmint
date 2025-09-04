# Security

## Content Security Policy

AllotMint's frontend is served from S3 behind CloudFront. A Content Security Policy (CSP) header restricts where the browser may load resources from. The default policy allows only the site itself and the APIs it relies on:

```
default-src 'self';
img-src 'self' data:;
script-src 'self';
style-src 'self' 'unsafe-inline';
connect-src 'self' https://www.alphavantage.co;
frame-ancestors 'none';
```

This prevents third‑party scripts or styles from executing unless explicitly whitelisted.

### Updating allowed sources

To allow resources from a new domain:

1. Edit the CSP string in the CloudFront response headers policy defined in `cdk/stacks/static_site_stack.py`.
2. Add the domain to the appropriate directive (e.g. `script-src` for scripts).
3. Redeploy the stack:
   ```bash
   cd cdk
   cdk deploy StaticSiteStack
   ```

For temporary local testing you may instead inject a `<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but prefer the header-based policy in production.
