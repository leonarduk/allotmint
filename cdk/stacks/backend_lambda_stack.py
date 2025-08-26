from pathlib import Path

from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
)
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[2]
        backend_path = project_root / "backend"

        backend_fn = PythonFunction(
            self,
            "BackendLambda",
            entry=str(backend_path),
            runtime=_lambda.Runtime.PYTHON_3_11,
            index="lambda_api/handler.py",
            handler="lambda_handler",
        )

        apigw.LambdaRestApi(self, "BackendApi", handler=backend_fn)

        # Scheduled function to refresh prices daily
        refresh_fn = PythonFunction(
            self,
            "PriceRefreshLambda",
            entry=str(backend_path),
            runtime=_lambda.Runtime.PYTHON_3_11,
            index="lambda_api/price_refresh.py",
            handler="lambda_handler",
        )

        events.Rule(
            self,
            "DailyPriceRefresh",
            schedule=events.Schedule.cron(minute="0", hour="0"),
            targets=[targets.LambdaFunction(refresh_fn)],
        )
