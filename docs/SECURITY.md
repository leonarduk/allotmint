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

### Adding or updating the policy

To update the CSP:

1. Edit the CloudFront response headers policy in `cdk/stacks/static_site_stack.py`.
2. Add the minimum directive needed for the new integration.
3. Run the CDK static site tests and redeploy:
   ```bash
   PYENV_VERSION=3.11.15 pytest cdk/tests/test_static_site_stack.py -v
   cd cdk
   npx cdk deploy StaticSiteStack
   ```

For temporary local testing you may instead inject a `<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but prefer the header-based policy in production.
