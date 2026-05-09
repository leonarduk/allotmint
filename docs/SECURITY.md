# Security

## Content Security Policy

AllotMint's frontend is served from S3 behind CloudFront. The static-site CDK stack attaches a CloudFront response headers policy that emits a restrictive Content Security Policy (CSP) for the SPA.

The policy allows:

- same-origin resources by default;
- the Google Identity Services script and iframe used for sign-in;
- browser API calls to the deployed AllotMint backend API; and
- Cognito hosted UI requests on `https://*.amazoncognito.com`.

### Dynamic backend API source

The backend API source in `connect-src` is built from the `BackendApiUrl` CloudFormation parameter in `cdk/stacks/static_site_stack.py`. Deployment workflows pass the Backend Lambda stack's `BackendApiUrl` output to that parameter, and CloudFormation substitutes the exact API Gateway URL into the CloudFront response headers policy at deploy time.

This keeps `connect-src` pinned to the API that the frontend is configured to call rather than permitting broad AWS hostnames.

### Why API Gateway cannot use a wildcard CSP source

API Gateway URLs include the API ID and the AWS region in different hostname labels:

```text
https://{api-id}.execute-api.{region}.amazonaws.com
```

CSP only allows a wildcard as the leftmost hostname label. As a result:

- `https://*.execute-api.*.amazonaws.com` is invalid CSP syntax because the second `*` is in the middle of the hostname, so browsers ignore that source expression;
- `https://*.execute-api.amazonaws.com` is syntactically valid but does not match regional API Gateway hostnames such as `abc123.execute-api.eu-west-1.amazonaws.com`; and
- `https://*.amazonaws.com` is syntactically valid but too broad because it permits any AWS service endpoint under `amazonaws.com`.

Use the dynamic `BackendApiUrl` parameter instead of any `*.amazonaws.com` pattern when adding or updating frontend API connectivity.

### Adding or updating the policy

To update the CSP:

1. Edit the CloudFront response headers policy in `cdk/stacks/static_site_stack.py`.
2. Keep the backend API entry in `connect-src` tied to the `BackendApiUrl` parameter.
3. Update `cdk/tests/test_static_site_stack.py` if the expected directives change.
4. Redeploy the static site stack with the backend URL parameter, for example:
   ```bash
   npm ci
   cd cdk
   npx cdk deploy StaticSiteStack \
     --parameters StaticSiteStack:BackendApiUrl=https://abc123.execute-api.eu-west-1.amazonaws.com
   ```

For temporary local testing you may instead inject a `<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but prefer the header-based policy in production.
