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
def template(tmp_path_factory):
    """Synthesise StaticSiteStack with a plain URL (used by most tests)."""
    dist = tmp_path_factory.mktemp("dist")
    (dist / "index.html").write_text("<html></html>")
    app = App()
    stack = StaticSiteStack(
        app,
        "TestStaticSiteStack",
        api_base_url=_DUMMY_API_URL,
        frontend_dist_path=str(dist),
    )
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


def test_three_separate_bucket_deployments(template):
    """There must be three separate BucketDeployment resources:
    one for assets, one for HTML, one for config.json.

    This confirms config.json is deployed as a distinct resource with its
    own cache-control settings, not bundled with the asset or HTML deployments.
    Source.json_data content is baked into a CDK asset zip and cannot be
    directly inspected from the CloudFormation template — the existence of
    a third separate deployment is the best proxy assertion available.
    """
    resources = template.find_resources("Custom::CDKBucketDeployment")
    assert len(resources) >= 3, (
        f"Expected at least 3 BucketDeployment resources (assets, html, config.json); "
        f"found {len(resources)}"
    )


def test_backend_api_url_parameter_exists(template):
    """StaticSiteStack must expose BackendApiUrl as a CloudFormation parameter.

    BucketDeployment.Source.json_data() only accepts intra-stack tokens
    (Ref / Fn::GetAtt / Fn::Select).  The CfnParameter produces a Ref token
    and avoids the renderData validator rejection that occurs with Fn::ImportValue.
    The actual URL is injected at deploy time via --parameters.
    """
    template.has_parameter(
        "BackendApiUrl",
        {"Type": "String"},
    )


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
