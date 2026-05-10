# Security

## AWS-hosted UI and API authentication

AllotMint uses two AWS-managed authentication layers for the deployed web app:

1. **UI gate** – `StaticSiteStack` creates an Amazon Cognito user pool, hosted UI domain, and public SPA client. The deployed `/config.json` includes the hosted UI settings, and the React bootstrap code redirects unauthenticated visitors to Cognito before rendering portfolio screens.
2. **Backend API authorization** – `BackendLambdaStack` receives the `UiAuthUserPool` and client IDs exported by `StaticSiteStack` as deploy-time parameters and attaches a JWT authorizer to the HTTP API routes. API Gateway rejects requests that do not include a valid `Authorization: Bearer <Cognito ID token>` header before invoking the Lambda.

The browser stores the Cognito session in `sessionStorage`, so closing the tab clears the API authorizer token. The frontend API client reads that session and sends the ID token on authenticated backend calls. Administrator-created Cognito users are required because self sign-up is disabled.

Useful outputs:

```bash
aws cloudformation describe-stacks --stack-name StaticSiteStack \
  --query "Stacks[0].Outputs[?starts_with(OutputKey, 'UiAuth')].[OutputKey,OutputValue]" \
  --output table
```

Create or invite users in the emitted `UiAuthUserPoolId` before sharing the CloudFront URL.

## Content Security Policy

AllotMint's frontend is served from S3 behind CloudFront. `StaticSiteStack` attaches a response headers policy with a restrictive CSP that allows the app shell, Google Identity Services, API Gateway, and Cognito endpoints required by the hosted UI flow:

```
default-src 'self';
script-src 'self' https://accounts.google.com/gsi/client;
connect-src 'self' https://*.amazonaws.com https://*.amazoncognito.com;
frame-src 'self' https://accounts.google.com/gsi/;
frame-ancestors 'none';
object-src 'none';
base-uri 'self'
```

The `connect-src` directive intentionally uses syntactically valid
leftmost-label wildcards because CSP host sources only support an optional
leading wildcard. The broader `*.amazonaws.com` entry covers API Gateway and
Cognito IdP endpoints; `*.amazoncognito.com` covers the Cognito hosted UI token
endpoint. When adding third-party services, update the CloudFront response
headers policy in `cdk/stacks/static_site_stack.py` rather than relying on a
page-level meta tag. For temporary local testing you may inject a
`<meta http-equiv="Content-Security-Policy">` tag in `frontend/index.html`, but
prefer the header-based policy in production.
