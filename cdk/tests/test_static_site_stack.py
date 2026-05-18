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

import aws_cdk as cdk  # noqa: E402
from aws_cdk import App, assertions  # noqa: E402

from cdk.stacks.static_site_stack import StaticSiteStack  # noqa: E402

_TEST_ACCOUNT = "123456789012"
_TEST_REGION = "us-east-1"
_HOSTED_ZONE_CONTEXT_KEY = (
    f"hosted-zone:account={_TEST_ACCOUNT}:domainName=allotmint.io:region={_TEST_REGION}"
)
_HOSTED_ZONE_CONTEXT_VALUE = {
    "Id": "/hostedzone/Z1234567890ABCDEFGHIJ",
    "Name": "allotmint.io.",
}

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
        {
            "AllowedPattern": "^$|^https://.+",
            "Type": "String",
        },
    )


def test_static_site_stack_synthesises_without_api_base_url(tmp_path):
    """StaticSiteStack must synthesise successfully without an api_base_url argument.

    This mirrors the production app.py path where no URL is passed at synth time —
    the real URL is supplied by the workflow via --parameters at deploy time.
    A regression here would mean the stack can only be synthesised in tests, not
    deployed from CI.
    """
    from aws_cdk import App  # noqa: PLC0415

    from cdk.stacks.static_site_stack import StaticSiteStack  # noqa: PLC0415

    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    # Must not raise — no api_base_url, CfnParameter default is empty string.
    StaticSiteStack(app, "NoUrlStack", frontend_dist_path=str(tmp_path))
    app.synth()


def _response_headers_policy_csp(template: assertions.Template) -> object:
    resources = template.find_resources("AWS::CloudFront::ResponseHeadersPolicy")
    assert len(resources) == 1, f"Expected one response headers policy, found {len(resources)}"
    policy = next(iter(resources.values()))
    return policy["Properties"]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"][
        "ContentSecurityPolicy"
    ]["ContentSecurityPolicy"]


# ---------------------------------------------------------------------------
# CloudFront security headers
# ---------------------------------------------------------------------------


def test_csp_connect_src_uses_backend_api_url_parameter(template):
    """CSP connect-src must reference BackendApiUrl directly, not a static wildcard.

    API Gateway URLs have the form {api-id}.execute-api.{region}.amazonaws.com.
    No valid static CSP wildcard can match this structure while staying narrower
    than *.amazonaws.com, so the BackendApiUrl parameter is injected directly,
    producing a CloudFormation Fn::Join that resolves to the exact origin at
    deploy time.
    """
    resources = template.find_resources("AWS::CloudFront::ResponseHeadersPolicy")
    csp_values = [
        security_headers["ContentSecurityPolicy"]["ContentSecurityPolicy"]
        for resource in resources.values()
        if (
            security_headers := resource["Properties"]["ResponseHeadersPolicyConfig"].get(
                "SecurityHeadersConfig", {}
            )
        )
        if "ContentSecurityPolicy" in security_headers
    ]

    assert len(csp_values) == 1, "Expected exactly one ResponseHeadersPolicy with a CSP"
    csp = csp_values[0]

    # The CSP value must be a Fn::Join because it contains a parameter reference.
    assert isinstance(csp, dict) and "Fn::Join" in csp, (
        "CSP must be a Fn::Join (BackendApiUrl token interpolation); got a plain string, "
        "which means the connect-src is using a static value instead of the parameter"
    )
    join_parts = csp["Fn::Join"][1]

    # The join must include a direct Ref to BackendApiUrl for the narrowest connect-src.
    assert {"Ref": "BackendApiUrl"} in join_parts, (
        "CSP Fn::Join must contain a Ref to BackendApiUrl"
    )

    # No static *.amazonaws.com wildcard should appear in any string fragment.
    static_text = "".join(p for p in join_parts if isinstance(p, str))
    assert "amazonaws.com" not in static_text, (
        "CSP must not contain any static amazonaws.com wildcard in its string fragments"
    )
    assert "connect-src 'self' " in static_text
    assert "https://*.amazoncognito.com" in static_text
    assert "script-src 'self' https://accounts.google.com/gsi/client" in static_text
    assert "frame-src 'self' https://accounts.google.com/gsi/" in static_text
    assert "frame-ancestors 'none'" in static_text
    assert static_text.count("object-src 'none'") == 1
    assert static_text.count("base-uri 'self'") == 1
    assert "; ;" not in static_text
    assert "'self'object-src" not in static_text, "Missing semicolon between base-uri and object-src"


def test_csp_header_overrides_origin_csp(template):
    """CloudFront must emit the managed CSP rather than preserving an origin CSP."""
    resources = template.find_resources("AWS::CloudFront::ResponseHeadersPolicy")
    assert len(resources) == 1, f"Expected one response headers policy, found {len(resources)}"
    policy = next(iter(resources.values()))
    csp_header = policy["Properties"]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"][
        "ContentSecurityPolicy"
    ]
    assert csp_header["Override"] is True


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


def _template_with_context(tmp_path: Path, context: dict[str, object]) -> assertions.Template:
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context=context)
    stack = StaticSiteStack(app, "ContextStaticSiteStack", frontend_dist_path=str(tmp_path))
    return assertions.Template.from_stack(stack)


def test_ui_auth_user_pool_created(template):
    """Static site deploys a Cognito user pool to gate the hosted UI."""
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {
            "AccountRecoverySetting": {
                "RecoveryMechanisms": assertions.Match.array_with(
                    [assertions.Match.object_like({"Name": "verified_email", "Priority": 1})]
                )
            },
            "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
        },
    )


def test_ui_auth_client_uses_authorization_code_flow(template):
    """Hosted UI auth must use the authorization-code flow for the SPA."""
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "AllowedOAuthFlows": ["code"],
            "AllowedOAuthScopes": assertions.Match.array_with(["email", "openid", "profile"]),
            "SupportedIdentityProviders": ["COGNITO"],
        },
    )


def test_ui_auth_outputs_exist(template):
    template.has_output("UiAuthUserPoolId", {})
    template.has_output("UiAuthUserPoolClientId", {})
    template.has_output("UiAuthDomain", {})


def test_ui_auth_user_pool_destroy_by_default(template):
    """Without the retainUserPool context key the UserPool uses DeletionPolicy: Delete."""
    pools = template.find_resources(
        "AWS::Cognito::UserPool",
        {"DeletionPolicy": "Delete"},
    )
    assert len(pools) >= 1, "Expected UserPool DeletionPolicy to be Delete in default (dev) mode"


def test_ui_auth_user_pool_retain_when_context_set(tmp_path):
    """Setting retainUserPool=true context switches the UserPool to DeletionPolicy: Retain."""
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"retainUserPool": "true"})
    stack = StaticSiteStack(
        app,
        "RetainStack",
        api_base_url=_DUMMY_API_URL,
        frontend_dist_path=str(tmp_path),
    )
    t = assertions.Template.from_stack(stack)
    pools = t.find_resources(
        "AWS::Cognito::UserPool",
        {"DeletionPolicy": "Retain"},
    )
    assert len(pools) >= 1, "Expected UserPool DeletionPolicy to be Retain when retainUserPool=true"


def test_ui_auth_user_pool_is_destroyed_by_default(tmp_path):
    template = _template_with_context(tmp_path, {})
    template.has_resource(
        "AWS::Cognito::UserPool",
        {"DeletionPolicy": "Delete", "UpdateReplacePolicy": "Delete"},
    )


def test_ui_auth_user_pool_is_retained_for_prod_context(tmp_path):
    template = _template_with_context(tmp_path, {"prod": "true"})
    template.has_resource(
        "AWS::Cognito::UserPool",
        {"DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain"},
    )


def test_ui_auth_user_pool_is_retained_for_retain_user_pool_context(tmp_path):
    template = _template_with_context(tmp_path, {"retainUserPool": "true"})
    template.has_resource(
        "AWS::Cognito::UserPool",
        {"DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain"},
    )


def test_ui_auth_outputs_exist(template):
    template.has_output("UiAuthUserPoolId", {})
    template.has_output("UiAuthUserPoolClientId", {})
    template.has_output("UiAuthDomain", {})


# ---------------------------------------------------------------------------
# Custom domain (app.allotmint.io) — gated by customDomain context flag
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def custom_domain_template(tmp_path_factory):
    """Synthesise StaticSiteStack with customDomain=true and a cached hosted zone."""
    dist = tmp_path_factory.mktemp("dist_custom")
    (dist / "index.html").write_text("<html></html>")
    app = App(
        context={
            "customDomain": "true",
            _HOSTED_ZONE_CONTEXT_KEY: _HOSTED_ZONE_CONTEXT_VALUE,
        }
    )
    stack = StaticSiteStack(
        app,
        "CustomDomainStack",
        api_base_url=_DUMMY_API_URL,
        frontend_dist_path=str(dist),
        env=cdk.Environment(account=_TEST_ACCOUNT, region=_TEST_REGION),
    )
    return assertions.Template.from_stack(stack)


def test_custom_domain_distribution_has_domain_names(custom_domain_template):
    """Distribution must list app.allotmint.io in Aliases when customDomain is set."""
    custom_domain_template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": {
                "Aliases": ["app.allotmint.io"],
            }
        },
    )


def test_custom_domain_acm_certificate_created(custom_domain_template):
    """An ACM certificate for app.allotmint.io must be present."""
    custom_domain_template.has_resource_properties(
        "AWS::CertificateManager::Certificate",
        {"DomainName": "app.allotmint.io"},
    )


def test_custom_domain_route53_alias_record_created(custom_domain_template):
    """A Route53 A record aliasing the CloudFront distribution must be present."""
    custom_domain_template.has_resource_properties(
        "AWS::Route53::RecordSet",
        {
            "Name": "app.allotmint.io.",
            "Type": "A",
        },
    )


def test_custom_domain_cognito_callback_uses_custom_domain(custom_domain_template):
    """Cognito callback URL must be https://app.allotmint.io/ when customDomain is set."""
    custom_domain_template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "CallbackURLs": ["https://app.allotmint.io/"],
            "LogoutURLs": ["https://app.allotmint.io/"],
        },
    )


def test_no_custom_domain_by_default(template):
    """Without customDomain context flag the distribution must not have Aliases."""
    resources = template.find_resources("AWS::CloudFront::Distribution")
    for resource in resources.values():
        aliases = (
            resource.get("Properties", {})
            .get("DistributionConfig", {})
            .get("Aliases", [])
        )
        assert aliases == [], f"Expected no Aliases in default mode; got {aliases}"


def test_no_acm_certificate_by_default(template):
    """Without customDomain context flag no ACM certificate should be synthesised."""
    resources = template.find_resources("AWS::CertificateManager::Certificate")
    assert len(resources) == 0, (
        f"Expected no ACM certificate in default mode; found {len(resources)}"
    )
