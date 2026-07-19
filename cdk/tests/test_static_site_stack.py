"""CDK assertion tests for StaticSiteStack.

Run from the repo root:
    pip install aws-cdk-lib constructs pytest --quiet
    pytest cdk/tests/test_static_site_stack.py -v
"""

import json
import os
from pathlib import Path

import pytest

# sys.path setup for `cdk.stacks...` imports lives in cdk/tests/conftest.py (#4929).
aws_cdk = pytest.importorskip("aws_cdk", reason="aws-cdk-lib not installed")

import aws_cdk as cdk  # noqa: E402
from aws_cdk import App, assertions  # noqa: E402

from cdk.stacks.static_site_stack import StaticSiteStack  # noqa: E402

_TEST_ACCOUNT = "123456789012"
_TEST_REGION = "us-east-1"
_TEST_HOSTED_ZONE_ID = "Z1234567890ABCDEFGHIJ"
_CUSTOM_DOMAIN_CONTEXT = {
    "customDomain": "true",
    "hostedZoneId": _TEST_HOSTED_ZONE_ID,
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
    assert "style-src 'self' 'unsafe-inline'" in static_text
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


def test_distribution_domain_output_has_no_scheme_prefix(template):
    """DistributionDomain must be the bare CloudFront hostname, not prefixed
    with a scheme.

    The deploy workflow builds FRONTEND_ORIGIN as
    f"https://{DISTRIBUTION_DOMAIN}" (.github/workflows/deploy-lambda.yml); if
    this output ever gained a "https://" prefix, FRONTEND_ORIGIN would become
    "https://https://..." and break CORS for the deployed frontend (#3990).
    distribution.domain_name resolves to a CloudFormation intrinsic
    (Fn::GetAtt) at synth time, so asserting that structure (rather than a
    literal string) guards against a future edit wrapping it in a scheme
    prefix.
    """
    outputs = template.to_json()["Outputs"]
    value = outputs["DistributionDomain"]["Value"]
    assert "Fn::GetAtt" in value, (
        f"Expected DistributionDomain to resolve to a bare Fn::GetAtt token, got: {value}"
    )
    assert "https://" not in json.dumps(value), (
        f"DistributionDomain output must not embed a scheme prefix: {value}"
    )


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


def test_smoke_test_client_has_user_password_auth(template):
    """CI smoke-test client must enable USER_PASSWORD_AUTH for non-interactive token fetches."""
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "ExplicitAuthFlows": assertions.Match.array_with(["ALLOW_USER_PASSWORD_AUTH"]),
        },
    )


def test_smoke_test_client_output_exists(template):
    """SmokeTestUserPoolClientId must be exported so the deploy workflow can look it up."""
    template.has_output("SmokeTestUserPoolClientId", {})


def test_ui_auth_client_does_not_have_user_password_auth(template):
    """The public UI client must NOT have USER_PASSWORD_AUTH — only the smoke-test client should."""
    clients = template.find_resources(
        "AWS::Cognito::UserPoolClient",
        {"Properties": {"AllowedOAuthFlows": ["code"]}},
    )
    assert len(clients) == 1, "Expected exactly one OAuth code-flow client (UiAuthClient)"
    ui_client = next(iter(clients.values()))
    auth_flows = ui_client["Properties"].get("ExplicitAuthFlows", [])
    assert "ALLOW_USER_PASSWORD_AUTH" not in auth_flows, (
        "UiAuthClient must not have USER_PASSWORD_AUTH enabled"
    )


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


def test_ui_auth_user_pool_is_retained_for_prod_context(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "GITHUB_DEPLOY_ROLE_ARN", "arn:aws:iam::123456789012:role/allotmint-github-deploy"
    )
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


def test_ui_auth_user_pool_retain_not_required_in_prod_env_vars(monkeypatch, tmp_path):
    """retainUserPool is a CDK context flag, not a required-in-prod env var.

    Synthesising with prod=true and no retainUserPool context (and without
    any retain-related env var) must not raise via assert_prod_env_vars, and
    the pool must still be retained because prod alone forces RETAIN. See
    #4771: retainUserPool is intentionally exempt from required-in-prod
    validation since it has a safe default under prod.
    """
    monkeypatch.setenv(
        "GITHUB_DEPLOY_ROLE_ARN", "arn:aws:iam::123456789012:role/allotmint-github-deploy"
    )
    monkeypatch.delenv("RETAIN_USER_POOL", raising=False)
    template = _template_with_context(tmp_path, {"prod": "true"})
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
    """Synthesise StaticSiteStack with customDomain=true.

    Uses from_hosted_zone_attributes (not from_lookup) so no AWS credentials are
    needed at synth time — only the hosted zone ID context value is required.
    """
    dist = tmp_path_factory.mktemp("dist_custom")
    (dist / "index.html").write_text("<html></html>")
    app = App(context=_CUSTOM_DOMAIN_CONTEXT)
    stack = StaticSiteStack(
        app,
        "CustomDomainStack",
        api_base_url=_DUMMY_API_URL,
        frontend_dist_path=str(dist),
        env=cdk.Environment(account=_TEST_ACCOUNT, region=_TEST_REGION),
    )
    return assertions.Template.from_stack(stack)


def _viewer_request_function_code(rendered_template) -> str:
    """Return the inline FunctionCode source of the ViewerRequestFn CloudFront Function.

    Asserts exactly one CloudFront Function exists so the helper fails loudly
    if the resource is renamed/removed rather than silently returning None.
    """
    resources = rendered_template.find_resources("AWS::CloudFront::Function")
    assert len(resources) == 1, f"Expected exactly one CloudFront Function; found {len(resources)}"
    properties = next(iter(resources.values()))["Properties"]
    return properties["FunctionCode"]


def test_viewer_request_function_validates_target_host_before_building_redirect(
    template, custom_domain_template
):
    """The Host-charset safety check must guard `targetHost` unconditionally,
    before it is ever interpolated into a redirect Location.

    Regression test for a host-header injection / open redirect: an earlier
    revision of this Function only forced `targetHost` back to a trusted value
    inside an `if (canonical)` branch, so when `canonical` is `null` (no custom
    domain configured) an attacker-controlled `Host` header could flow straight
    into the 301 `Location` header unvalidated. The fixed source must apply the
    `/^[A-Za-z0-9.-]+$/` charset test to `targetHost` ahead of (i.e. at a lower
    string offset than) the `'https://' + targetHost` Location construction, in
    both the custom-domain and non-custom-domain builds, and must refuse to
    redirect using an unsafe host when no trusted canonical host is configured.
    """
    host_charset_check = "/^[A-Za-z0-9.-]+$/.test(targetHost)"
    location_construction = "'https://' + targetHost"
    no_safe_target_fallback = "return request"

    for rendered_template in (template, custom_domain_template):
        source = _viewer_request_function_code(rendered_template)
        check_index = source.index(host_charset_check)
        location_index = source.index(location_construction)
        assert check_index < location_index, (
            "targetHost must be validated against the host charset before "
            "being interpolated into the redirect Location header"
        )
        assert no_safe_target_fallback in source, (
            "Function must pass the request through (rather than redirect to "
            "an untrusted Host header value) when no canonical host is "
            "configured and the incoming Host fails the safety check"
        )


def test_viewer_request_function_skips_redirect_target_without_custom_domain(template):
    """When customDomain is disabled, the Function source must not hardcode a
    redirect target host — it must substitute `null` for __CANONICAL_HOST__.

    Regression test for issue #3693: the deployed Function previously redirected
    ALL traffic to https://app.allotmint.io regardless of whether that domain had
    an alias, ACM certificate, or DNS record for this distribution, causing a
    production outage (NXDOMAIN on every request).
    """
    source = _viewer_request_function_code(template)
    assert "__CANONICAL_HOST__" not in source, (
        "Function source must not contain the unsubstituted template placeholder"
    )
    assert "app.allotmint.io" not in source, (
        "Function source must not hardcode the custom-domain host when "
        "customDomain is disabled for this deployment"
    )
    assert "var canonical = null;" in source, (
        "Function source must substitute `null` for __CANONICAL_HOST__ so "
        "host-based canonicalization is skipped entirely"
    )


def test_viewer_request_function_defaults_proto_to_https_when_header_absent(
    template, custom_domain_template
):
    """The Function must default proto to 'https' when cloudfront-forwarded-proto
    is absent, not null.

    Regression test for issue #3763: defaulting to null caused proto !== 'https'
    to always be true when the header was missing (common in viewer-request
    events), triggering an infinite self-redirect loop (301 → same HTTPS URL →
    301 again) and ERR_TOO_MANY_REDIRECTS / CHROME_INTERSTITIAL_ERROR in both
    Lighthouse CI and real browsers when customDomain is disabled.
    """
    safe_fallback = "? 'http' : 'https'"
    avoid_null_fallback = ": null"

    for rendered_template in (template, custom_domain_template):
        source = _viewer_request_function_code(rendered_template)
        assert safe_fallback in source, (
            "cloudfront-forwarded-proto absent/unrecognised must default to "
            "'https', not null — null causes an infinite self-redirect loop"
        )
        assert avoid_null_fallback not in source, (
            "proto must never default to null; use 'https' as the safe fallback"
        )


def test_viewer_request_function_redirects_to_custom_domain_when_enabled(custom_domain_template):
    """When customDomain is enabled, the Function source must canonicalize to
    the configured custom domain (which has a matching alias/cert/DNS record)."""
    source = _viewer_request_function_code(custom_domain_template)
    assert "__CANONICAL_HOST__" not in source, (
        "Function source must not contain the unsubstituted template placeholder"
    )
    assert 'var canonical = "app.allotmint.io";' in source, (
        "Function source must substitute the configured custom domain literal "
        "for __CANONICAL_HOST__ when customDomain is enabled"
    )


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


def test_custom_domain_certificate_uses_dns_validation(custom_domain_template):
    """Certificate validation must use DNS (not email) so it can be automated."""
    custom_domain_template.has_resource_properties(
        "AWS::CertificateManager::Certificate",
        {"ValidationMethod": "DNS"},
    )


def test_custom_domain_route53_alias_record_targets_cloudfront(custom_domain_template):
    """Route53 A record AliasTarget.DNSName must reference the CloudFront distribution.

    CDK resolves the CloudFront hosted zone ID via Fn::FindInMap (partition mapping),
    so we verify the DNSName is a Fn::GetAtt pointing at the distribution's DomainName
    rather than checking the literal HostedZoneId string.
    """
    resources = custom_domain_template.find_resources(
        "AWS::Route53::RecordSet",
        {"Properties": {"Name": "app.allotmint.io.", "Type": "A"}},
    )
    assert len(resources) == 1, (
        f"Expected exactly one A record for app.allotmint.io.; found {len(resources)}"
    )
    alias_target = next(iter(resources.values()))["Properties"]["AliasTarget"]
    dns_name = alias_target.get("DNSName", {})
    assert isinstance(dns_name, dict) and "Fn::GetAtt" in dns_name, (
        f"AliasTarget.DNSName must be Fn::GetAtt referencing the distribution; got {dns_name!r}"
    )
    get_att_args = dns_name["Fn::GetAtt"]
    assert len(get_att_args) == 2 and get_att_args[1] == "DomainName", (
        f"Fn::GetAtt must reference DomainName; got {get_att_args!r}"
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


def test_explicit_false_custom_domain_no_certificate(tmp_path):
    """Explicitly setting customDomain=false must also produce no certificate."""
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"customDomain": "false"})
    stack = StaticSiteStack(app, "FalseCustomDomainStack", frontend_dist_path=str(tmp_path))
    t = assertions.Template.from_stack(stack)
    resources = t.find_resources("AWS::CertificateManager::Certificate")
    assert len(resources) == 0, (
        f"customDomain=false must produce no certificate; found {len(resources)}"
    )


def test_custom_domain_wrong_region_raises(tmp_path):
    """Instantiating the stack with customDomain=true outside us-east-1 must raise."""
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context=_CUSTOM_DOMAIN_CONTEXT)
    with pytest.raises(ValueError, match="us-east-1"):
        StaticSiteStack(
            app,
            "WrongRegionStack",
            frontend_dist_path=str(tmp_path),
            env=cdk.Environment(account=_TEST_ACCOUNT, region="eu-west-1"),
        )


def test_custom_domain_missing_hosted_zone_id_raises(tmp_path):
    """customDomain=true without hostedZoneId context must raise ValueError."""
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"customDomain": "true"})
    with pytest.raises(ValueError, match="hostedZoneId"):
        StaticSiteStack(
            app,
            "MissingZoneStack",
            frontend_dist_path=str(tmp_path),
            env=cdk.Environment(account=_TEST_ACCOUNT, region=_TEST_REGION),
        )


def test_custom_domain_bool_true_context(tmp_path):
    """customDomain=True (Python bool, not string) must also enable the custom domain.

    _is_truthy_context handles isinstance(value, bool) before the str branch,
    so a bool True from cdk.json or programmatic context must work identically
    to the string "true" passed via --context.
    """
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"customDomain": True, "hostedZoneId": _TEST_HOSTED_ZONE_ID})
    stack = StaticSiteStack(
        app,
        "BoolTrueStack",
        frontend_dist_path=str(tmp_path),
        env=cdk.Environment(account=_TEST_ACCOUNT, region=_TEST_REGION),
    )
    t = assertions.Template.from_stack(stack)
    resources = t.find_resources("AWS::CertificateManager::Certificate")
    assert len(resources) == 1, (
        f"Expected one ACM certificate when customDomain=True (bool); found {len(resources)}"
    )


def test_boolean_false_context_no_certificate(tmp_path):
    """customDomain=False (native Python bool) must not produce a certificate.

    cdk.json stores JSON booleans which CDK deserialises as Python bools, so
    _is_truthy_context must handle bool False as well as string "false".
    """
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"customDomain": False})
    stack = StaticSiteStack(app, "BoolFalseStack", frontend_dist_path=str(tmp_path))
    t = assertions.Template.from_stack(stack)
    resources = t.find_resources("AWS::CertificateManager::Certificate")
    assert len(resources) == 0, (
        f"customDomain=False (bool) must produce no certificate; found {len(resources)}"
    )


# ---------------------------------------------------------------------------
# GitHub deploy role — changeset permissions (issue #3192)
# ---------------------------------------------------------------------------


def _cfn_changeset_resources_static(raw_template: dict, role_name: str) -> list[object]:
    """Return Resource entries from cloudformation:CreateChangeSet statements for role_name."""
    found: list[object] = []
    for res in raw_template["Resources"].values():
        if res.get("Type") != "AWS::IAM::Policy":
            continue
        if role_name not in res.get("Properties", {}).get("Roles", []):
            continue
        for stmt in res["Properties"]["PolicyDocument"].get("Statement", []):
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if "cloudformation:CreateChangeSet" not in actions:
                continue
            resources = stmt.get("Resource", [])
            if isinstance(resources, (str, dict)):
                resources = [resources]
            found.extend(resources)
    return found


def test_github_deploy_role_gets_changeset_permissions_on_both_stacks(
    monkeypatch, tmp_path
) -> None:
    """StaticSiteStack must grant CreateChangeSet/DescribeChangeSet/DeleteChangeSet on both
    StaticSiteStack and BackendLambdaStack when GITHUB_DEPLOY_ROLE_ARN is set.

    The grant lives here (not in BackendLambdaStack) so it survives BackendLambdaStack
    structural changes that would otherwise briefly remove and recreate the inline policy,
    causing `cdk diff --method=changeset` to fail. See #3192.
    """
    role_arn = "arn:aws:iam::123456789012:role/allotmint-github-deploy"
    monkeypatch.setenv("GITHUB_DEPLOY_ROLE_ARN", role_arn)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    stack = StaticSiteStack(app, "CfnGrantStaticSiteStack", frontend_dist_path=str(tmp_path))
    raw = assertions.Template.from_stack(stack).to_json()

    resources = _cfn_changeset_resources_static(raw, "allotmint-github-deploy")
    assert resources, (
        "cloudformation:CreateChangeSet statement not found in StaticSiteStack template; "
        "GITHUB_DEPLOY_ROLE_ARN was set"
    )
    resources_str = str(resources)
    assert "/*" in resources_str, (
        f"Changeset resource ARNs should end with /* (wildcard stack ID); got: {resources_str}"
    )
    for stack_name in ("CfnGrantStaticSiteStack", "BackendLambdaStack"):
        assert stack_name in resources_str, (
            f"cloudformation:CreateChangeSet not scoped to {stack_name}; got: {resources_str}"
        )


def test_no_changeset_grant_when_github_deploy_role_arn_absent(monkeypatch, tmp_path) -> None:
    """When GITHUB_DEPLOY_ROLE_ARN is unset, StaticSiteStack must not synthesise a
    cloudformation:CreateChangeSet policy."""
    monkeypatch.delenv("GITHUB_DEPLOY_ROLE_ARN", raising=False)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    stack = StaticSiteStack(app, "NoCfnGrantStack", frontend_dist_path=str(tmp_path))
    raw = assertions.Template.from_stack(stack).to_json()
    resources = _cfn_changeset_resources_static(raw, "allotmint-github-deploy")
    assert not resources, (
        "Expected no cloudformation:CreateChangeSet in StaticSiteStack when "
        "GITHUB_DEPLOY_ROLE_ARN is unset"
    )


# ---------------------------------------------------------------------------
# GitHub deploy role — iam:SimulatePrincipalPolicy (issue #3208)
# ---------------------------------------------------------------------------


def _has_simulate_principal_policy_grant(raw_template: dict, role_name: str) -> bool:
    """Return True if any IAM policy attached to role_name grants iam:SimulatePrincipalPolicy.

    Role-name matching note: CDK calls ``iam.Role.from_role_arn(..., mutable=True)``,
    which extracts the short role name from the ARN and stores it as a **plain string**
    in the synthesised template's ``Roles`` list — NOT as a ``{"Ref": ...}`` object.
    This is different from an owned CDK role, where CDK emits a Ref/GetAtt.

    Verified against a live ``cdk synth`` output::

        "Roles": ["allotmint-github-deploy"]  # plain string, not {"Ref": "..."}

    String equality on ``role_name`` is therefore correct and will NOT pass vacuously.
    """
    for res in raw_template["Resources"].values():
        if res.get("Type") != "AWS::IAM::Policy":
            continue
        if role_name not in res.get("Properties", {}).get("Roles", []):
            continue
        for stmt in res["Properties"]["PolicyDocument"].get("Statement", []):
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if "iam:SimulatePrincipalPolicy" in actions:
                return True
    return False


def test_github_deploy_role_gets_simulate_principal_policy(monkeypatch, tmp_path) -> None:
    """When GITHUB_DEPLOY_ROLE_ARN is set, StaticSiteStack must grant
    iam:SimulatePrincipalPolicy so the CI pre-flight check can call
    simulate-principal-policy on the deploy role. See issue #3208."""
    role_arn = "arn:aws:iam::123456789012:role/allotmint-github-deploy"
    monkeypatch.setenv("GITHUB_DEPLOY_ROLE_ARN", role_arn)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    stack = StaticSiteStack(app, "SimGrantStack", frontend_dist_path=str(tmp_path))
    raw = assertions.Template.from_stack(stack).to_json()
    assert _has_simulate_principal_policy_grant(raw, "allotmint-github-deploy"), (
        "iam:SimulatePrincipalPolicy not found in StaticSiteStack IAM policy for the deploy role; "
        "GITHUB_DEPLOY_ROLE_ARN was set. The pre-flight check will fail until this grant is deployed."
    )


def test_no_simulate_principal_policy_grant_when_role_arn_absent(
    monkeypatch, tmp_path
) -> None:
    """When GITHUB_DEPLOY_ROLE_ARN is unset, no iam:SimulatePrincipalPolicy policy
    should be synthesised."""
    monkeypatch.delenv("GITHUB_DEPLOY_ROLE_ARN", raising=False)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    stack = StaticSiteStack(app, "NoSimGrantStack", frontend_dist_path=str(tmp_path))
    raw = assertions.Template.from_stack(stack).to_json()
    assert not _has_simulate_principal_policy_grant(raw, "allotmint-github-deploy"), (
        "Expected no iam:SimulatePrincipalPolicy in StaticSiteStack when GITHUB_DEPLOY_ROLE_ARN is unset"
    )


# ---------------------------------------------------------------------------
# GitHub deploy role — cognito-idp:UpdateUserPoolClient (issue #3802)
# ---------------------------------------------------------------------------


def _cognito_user_pool_client_resources(raw_template: dict, role_name: str) -> list[object]:
    """Return Resource entries from cognito-idp:UpdateUserPoolClient statements for role_name."""
    found: list[object] = []
    for res in raw_template["Resources"].values():
        if res.get("Type") != "AWS::IAM::Policy":
            continue
        if role_name not in res.get("Properties", {}).get("Roles", []):
            continue
        for stmt in res["Properties"]["PolicyDocument"].get("Statement", []):
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if "cognito-idp:UpdateUserPoolClient" not in actions:
                continue
            assert "cognito-idp:DescribeUserPoolClient" in actions, (
                "cognito-idp:UpdateUserPoolClient grant should be paired with "
                "cognito-idp:DescribeUserPoolClient"
            )
            resources = stmt.get("Resource", [])
            if isinstance(resources, (str, dict)):
                resources = [resources]
            found.extend(resources)
    return found


def test_github_deploy_role_gets_cognito_user_pool_client_permissions(
    monkeypatch, tmp_path
) -> None:
    """StaticSiteStack must grant the deploy role cognito-idp:UpdateUserPoolClient and
    cognito-idp:DescribeUserPoolClient, scoped to the UiAuthUserPool, when
    GITHUB_DEPLOY_ROLE_ARN is set. This lets the deploy workflow re-apply the
    CDK-declared UiAuthClient OAuth settings on every deploy, self-healing the
    drift described in #3802."""
    role_arn = "arn:aws:iam::123456789012:role/allotmint-github-deploy"
    monkeypatch.setenv("GITHUB_DEPLOY_ROLE_ARN", role_arn)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    stack = StaticSiteStack(app, "CognitoGrantStaticSiteStack", frontend_dist_path=str(tmp_path))
    raw = assertions.Template.from_stack(stack).to_json()

    resources = _cognito_user_pool_client_resources(raw, "allotmint-github-deploy")
    assert resources, (
        "cognito-idp:UpdateUserPoolClient statement not found in StaticSiteStack template; "
        "GITHUB_DEPLOY_ROLE_ARN was set"
    )
    resources_str = str(resources)
    assert "userpool/" in resources_str, (
        f"cognito-idp grant should be scoped to a userpool/ resource ARN; got: {resources_str}"
    )


def test_no_cognito_user_pool_client_grant_when_github_deploy_role_arn_absent(
    monkeypatch, tmp_path
) -> None:
    """When GITHUB_DEPLOY_ROLE_ARN is unset, no cognito-idp:UpdateUserPoolClient
    policy should be synthesised."""
    monkeypatch.delenv("GITHUB_DEPLOY_ROLE_ARN", raising=False)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    stack = StaticSiteStack(app, "NoCognitoGrantStack", frontend_dist_path=str(tmp_path))
    raw = assertions.Template.from_stack(stack).to_json()
    resources = _cognito_user_pool_client_resources(raw, "allotmint-github-deploy")
    assert not resources, (
        "Expected no cognito-idp:UpdateUserPoolClient in StaticSiteStack when "
        "GITHUB_DEPLOY_ROLE_ARN is unset"
    )


# ---------------------------------------------------------------------------
# GitHub deploy role — required in prod (issue #3870)
# ---------------------------------------------------------------------------


def test_prod_without_github_deploy_role_arn_raises(monkeypatch, tmp_path) -> None:
    """A prod-context synth must fail loudly when GITHUB_DEPLOY_ROLE_ARN is unset
    rather than silently omitting the IAM grant. See #3847 and #3866."""
    monkeypatch.delenv("GITHUB_DEPLOY_ROLE_ARN", raising=False)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"prod": "true"})
    with pytest.raises(ValueError, match="GITHUB_DEPLOY_ROLE_ARN"):
        StaticSiteStack(app, "ProdNoRoleStack", frontend_dist_path=str(tmp_path))


def test_prod_with_empty_string_github_deploy_role_arn_raises(monkeypatch, tmp_path) -> None:
    """An empty-string GITHUB_DEPLOY_ROLE_ARN in prod context must raise the same
    way as an unset one — the guard treats "" and missing identically. See #4731."""
    monkeypatch.setenv("GITHUB_DEPLOY_ROLE_ARN", "")
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"prod": "true"})
    with pytest.raises(ValueError, match="GITHUB_DEPLOY_ROLE_ARN"):
        StaticSiteStack(app, "ProdEmptyRoleStack", frontend_dist_path=str(tmp_path))


def test_prod_with_github_deploy_role_arn_synthesises(monkeypatch, tmp_path) -> None:
    """A prod-context synth must succeed when GITHUB_DEPLOY_ROLE_ARN is set."""
    monkeypatch.setenv(
        "GITHUB_DEPLOY_ROLE_ARN", "arn:aws:iam::123456789012:role/allotmint-github-deploy"
    )
    (tmp_path / "index.html").write_text("<html></html>")
    app = App(context={"prod": "true"})
    # Must not raise.
    stack = StaticSiteStack(app, "ProdWithRoleStack", frontend_dist_path=str(tmp_path))
    app.synth()
    assert stack is not None


def test_non_prod_without_github_deploy_role_arn_synthesises(monkeypatch, tmp_path) -> None:
    """Non-prod (dev/staging) stacks must synthesise without GITHUB_DEPLOY_ROLE_ARN set."""
    monkeypatch.delenv("GITHUB_DEPLOY_ROLE_ARN", raising=False)
    (tmp_path / "index.html").write_text("<html></html>")
    app = App()
    # Must not raise.
    stack = StaticSiteStack(app, "DevNoRoleStack", frontend_dist_path=str(tmp_path))
    app.synth()
    assert stack is not None
