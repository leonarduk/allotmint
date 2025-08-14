from pathlib import Path

from aws_cdk import (
    Stack,
    BundlingOptions,
    aws_apigateway as apigw,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[2]
        backend_path = project_root / "backend"

        dependencies_layer = _lambda.LayerVersion(
            self,
            "BackendDependencies",
            code=_lambda.Code.from_asset(
                str(backend_path),
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output/python",
                    ],
                ),
            ),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
        )

        backend_code = _lambda.Code.from_asset(str(backend_path))

        backend_fn = _lambda.Function(
            self,
            "BackendLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="backend.lambda_api.handler.lambda_handler",
            code=backend_code,
            layers=[dependencies_layer],
        )

        apigw.LambdaRestApi(self, "BackendApi", handler=backend_fn)

        # Scheduled function to refresh prices daily
        refresh_fn = _lambda.Function(
            self,
            "PriceRefreshLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="backend.lambda_api.price_refresh.lambda_handler",
            code=backend_code,
            layers=[dependencies_layer],
        )

        events.Rule(
            self,
            "DailyPriceRefresh",
            schedule=events.Schedule.cron(minute="0", hour="0"),
            targets=[targets.LambdaFunction(refresh_fn)],
        )
