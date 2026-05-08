# Security

## Content Security Policy

AllotMint's frontend is served from S3 behind CloudFront. The static site stack sets a Content Security Policy (CSP) header to limit the sources the browser may load resources from.

The deployed CloudFront policy is:

```
default-src 'self';
script-src 'self' https://accounts.google.com/gsi/client;
frame-src 'self' https://accounts.google.com/gsi/;
connect-src 'self' https://*.execute-api.*.amazonaws.com https://*.amazoncognito.com;
frame-ancestors 'none';
object-src 'none';
base-uri 'self';
```

The `connect-src` directive intentionally permits only API Gateway and Amazon Cognito hosted UI/token exchange endpoints in the AWS namespace. If the frontend adds calls to another AWS service, add the narrowest service-specific host pattern instead of broadening this to `https://*.amazonaws.com`.

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
