# Security

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

AllotMint's frontend is served from S3 behind CloudFront. The static site stack attaches a CloudFront response headers policy that sets a restrictive CSP for production traffic. The policy allows the app itself, Google Identity Services for the existing backend login flow, and AWS endpoints needed for API Gateway and Cognito hosted-UI token exchange.

The current policy is defined in `cdk/stacks/static_site_stack.py` and includes these main directives:

```text
default-src 'self';
script-src 'self' https://accounts.google.com/gsi/client;
connect-src 'self' https://*.amazonaws.com https://*.amazoncognito.com;
frame-src 'self' https://accounts.google.com/gsi/;
frame-ancestors 'none';
object-src 'none';
base-uri 'self'
```

Note: `https://*.amazoncognito.com` is required for the PKCE token exchange — the Cognito hosted UI token endpoint (`/oauth2/token`) lives under `amazoncognito.com`, not `amazonaws.com`.
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
2. Add the minimum directive needed for the new integration.
3. Run the CDK static site tests and redeploy:
2. Keep the backend API entry in `connect-src` tied to the `BackendApiUrl` parameter.
3. Update `cdk/tests/test_static_site_stack.py` if the expected directives change.
4. Redeploy the static site stack with the backend URL parameter, for example:
   ```bash
   PYENV_VERSION=3.11.15 pytest cdk/tests/test_static_site_stack.py -v
   cd cdk
   npx cdk deploy StaticSiteStack \
     --parameters StaticSiteStack:BackendApiUrl=https://abc123.execute-api.eu-west-1.amazonaws.com
   ```

For temporary local testing you may instead inject a `<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but prefer the header-based policy in production.
