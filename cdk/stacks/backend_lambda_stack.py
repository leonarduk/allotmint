from pathlib import Path

from aws_cdk import Stack, aws_apigateway as apigw, aws_lambda as _lambda
from constructs import Construct


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[2]

        backend_fn = _lambda.Function(
            self,
            "BackendLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="backend.lambda_api.handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(project_root),
                bundling=_lambda.BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r backend /asset-output",
                    ],
                ),
            ),
        )

        apigw.LambdaRestApi(self, "BackendApi", handler=backend_fn)
