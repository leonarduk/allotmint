# Stable CloudFormation export names shared between producer and consumer stacks.
# Renaming any value here requires a two-phase deployment:
#   1. Add the new export name alongside the old one.
#   2. Migrate consumers to the new name.
#   3. Remove the old export name.
BACKEND_API_URL_EXPORT = "BackendLambdaStack-BackendApiUrl"
