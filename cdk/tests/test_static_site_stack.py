"""CDK assertion tests for StaticSiteStack.

Run from the repo root:
    pip install aws-cdk-lib constructs pytest --quiet
    pytest cdk/tests/test_static_site_stack.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

aws_cdk = pytest.importorskip("aws_cdk", reason="aws-cdk-lib not installed")

from aws_cdk import App, assertions  # noqa: E402
from cdk.stacks.static_site_stack import StaticSiteStack  # noqa: E402

_DUMMY_API_URL = "https://abc123.execute-api.eu-west-1.amazonaws.com"


@pytest.fixture(scope="module")
def template():
    """Synthesise StaticSiteStack and return its CloudFormation template."""
    app = App()
    stack = StaticSiteStack(app, "TestStaticSiteStack", api_base_url=_DUMMY_API_URL)
    return assertions.Template.from_stack(stack)


# ---------------------------------------------------------------------------
# SPA error responses
# ---------------------------------------------------------------------------

def test_403_redirects_to_index_html(template):
    """CloudFront must return /index.html for 403 (S3 access-denied) responses."""
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": {
                "CustomErrorResponses": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "ErrorCode": 403,
                                "ResponseCode": 200,
                                "ResponsePagePath": "/index.html",
                            }
                        )
                    ]
                )
            }
        },
    )


def test_404_redirects_to_index_html(template):
    """CloudFront must return /index.html for 404 responses (SPA deep-link routing)."""
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": {
                "CustomErrorResponses": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "ErrorCode": 404,
                                "ResponseCode": 200,
                                "ResponsePagePath": "/index.html",
                            }
                        )
                    ]
                )
            }
        },
    )


# ---------------------------------------------------------------------------
# config.json deployment
# ---------------------------------------------------------------------------

def test_runtime_config_deployment_exists(template):
    """At least one BucketDeployment resource must be present (config.json injection)."""
    # BucketDeployment is backed by Custom::CDKBucketDeployment.
    # resource_count_is expects an int; use find_resources for a '>0' assertion.
    resources = template.find_resources("Custom::CDKBucketDeployment")
    assert len(resources) > 0, "Expected at least one Custom::CDKBucketDeployment resource"


# ---------------------------------------------------------------------------
# CloudFront distribution outputs
# ---------------------------------------------------------------------------

def test_distribution_id_output_exists(template):
    template.has_output("DistributionId", {})


def test_distribution_domain_output_exists(template):
    template.has_output("DistributionDomain", {})


def test_site_bucket_output_exists(template):
    template.has_output("SiteBucket", {})


# ---------------------------------------------------------------------------
# Site bucket security
# ---------------------------------------------------------------------------

def test_site_bucket_blocks_public_access(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )
