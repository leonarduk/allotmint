"""
AWS Lambda entry-point (Python 3.11 runtime or container).
Handler: backend.lambda_api.handler.lambda_handler
"""

from mangum import Mangum

from backend.app import create_app

lambda_handler = Mangum(create_app())
