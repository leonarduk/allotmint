# Stable CloudFormation export names shared between producer and consumer stacks.
# Renaming any value here requires a two-phase deployment:
#   1. Add the new export name alongside the old one.
#   2. Migrate consumers to the new name.
#   3. Remove the old export name.
BACKEND_API_URL_EXPORT = "BackendLambdaStack-BackendApiUrl"

UI_AUTH_USER_POOL_ID_EXPORT = "StaticSiteStack-UiAuthUserPoolId"
UI_AUTH_USER_POOL_CLIENT_ID_EXPORT = "StaticSiteStack-UiAuthUserPoolClientId"
UI_AUTH_DOMAIN_EXPORT = "StaticSiteStack-UiAuthDomain"
