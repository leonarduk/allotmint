import os
from pathlib import Path

from aws_cdk import Aws, CfnOutput, CfnParameter, Duration, Fn, RemovalPolicy, Stack, Token
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deployment
from constructs import Construct


def _is_truthy_context(value: object) -> bool:
    """Return true when a CDK context value explicitly opts into production."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def _ui_auth_removal_policy(scope: Construct) -> RemovalPolicy:
    """Retain the Cognito user pool when production retention is requested."""
    retain_user_pool = _is_truthy_context(scope.node.try_get_context("retainUserPool"))
    prod = _is_truthy_context(scope.node.try_get_context("prod"))
    if retain_user_pool or prod:
        return RemovalPolicy.RETAIN
    return RemovalPolicy.DESTROY


class StaticSiteStack(Stack):
    """CDK stack that provisions S3 + CloudFront for the frontend."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_base_url: str | None = None,
        frontend_dist_path: str | Path | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ui_auth_removal_policy = _ui_auth_removal_policy(self)

        # BucketDeployment.Source.json_data() only accepts intra-stack tokens
        # (Ref / Fn::GetAtt / Fn::Select) - Fn::ImportValue is explicitly rejected
        # by CDK's renderData validator. A CfnParameter produces a Ref token and
        # therefore works. The real URL is supplied at deploy time via
        # `--parameters StaticSiteStack:BackendApiUrl=<url>`.
        # Pass api_base_url here to use it as the default (useful in tests).
        backend_url_param = CfnParameter(
            self,
            "BackendApiUrl",
            type="String",
            default=api_base_url or "",
            allowed_pattern=r"^$|^https://.+",
            constraint_description=(
                "BackendApiUrl must be empty for synth-only workflows or an "
                "HTTPS URL such as https://abc123.execute-api.us-east-1.amazonaws.com."
            ),
            description=(
                "Backend API base URL - override at deploy time with the "
                "BackendLambdaStack BackendApiUrl output."
            ),
        )

        # CSP connect-src uses the BackendApiUrl parameter directly so that
        # CloudFormation resolves it to the exact API origin at deploy time.
        # A static wildcard like *.execute-api.*.amazonaws.com is invalid CSP
        # syntax (wildcards are only permitted as the leftmost hostname label)
        # and would be silently ignored by browsers, blocking all API calls.
        _csp = "; ".join(
            [
                "default-src 'self'",
                "script-src 'self' https://accounts.google.com/gsi/client",
                "frame-src 'self' https://accounts.google.com/gsi/",
                f"connect-src 'self' {backend_url_param.value_as_string} https://*.amazoncognito.com",
                "frame-ancestors 'none'",
                "object-src 'none'",
                "base-uri 'self'",
            ]
        ) + ";"

        site_bucket = s3.Bucket(
            self,
            "StaticSiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        security_headers = cloudfront.ResponseHeadersPolicy(
            self,
            "SecurityHeaders",
            comment="Security headers for static site",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                # Allow Google Identity Services, API Gateway calls, and Cognito token exchange.
                content_security_policy=cloudfront.ResponseHeadersContentSecurityPolicy(
                    content_security_policy=_csp,
                    override=True,
                ),
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.seconds(63072000),
                    include_subdomains=True,
                    preload=True,
                    override=True,
                ),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(override=True),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=True,
                ),
            ),
        )

        # Origin selection: prefer OAC (CDK >= 2.116), fall back to OAI,
        # then to legacy S3Origin - each path grants CloudFront bucket read.
        if hasattr(origins, "S3BucketOrigin") and hasattr(
            origins.S3BucketOrigin, "with_origin_access_control"
        ):
            # Preferred path: OAC auto-manages the bucket policy grant.
            s3_origin = origins.S3BucketOrigin.with_origin_access_control(site_bucket)
        elif hasattr(origins, "S3BucketOrigin") and hasattr(
            origins.S3BucketOrigin, "with_origin_access_identity"
        ):
            # OAI fallback for CDK versions that have S3BucketOrigin but not OAC.
            oai = cloudfront.OriginAccessIdentity(self, "StaticSiteOAI")
            site_bucket.grant_read(oai)
            s3_origin = origins.S3BucketOrigin.with_origin_access_identity(
                site_bucket, origin_access_identity=oai
            )
        else:
            # Legacy fallback for CDK versions where S3BucketOrigin is unavailable.
            oai = cloudfront.OriginAccessIdentity(self, "StaticSiteOAI")
            site_bucket.grant_read(oai)
            s3_origin = origins.S3Origin(site_bucket, origin_access_identity=oai)

        asset_cache_policy = cloudfront.CachePolicy(
            self,
            "AssetsCachePolicy",
            default_ttl=Duration.days(30),
            # Avoid a cache stampede when invalidating assets by ensuring a
            # minimal amount of caching instead of allowing completely
            # uncached requests.
            min_ttl=Duration.seconds(1),
            max_ttl=Duration.days(30),
            enable_accept_encoding_brotli=True,
            enable_accept_encoding_gzip=True,
        )

        html_cache_policy = cloudfront.CachePolicy(
            self,
            "HtmlCachePolicy",
            default_ttl=Duration.seconds(300),
            # Provide a small floor to mitigate cache stampedes while keeping
            # HTML invalidations responsive.
            min_ttl=Duration.seconds(1),
            max_ttl=Duration.seconds(3600),
            enable_accept_encoding_brotli=True,
            enable_accept_encoding_gzip=True,
        )

        redirect_fn = cloudfront.Function(
            self,
            "ViewerRequestFn",
            code=cloudfront.FunctionCode.from_file(
                file_path=str(
                    Path(__file__).resolve().parents[1] / "functions" / "viewer-request.js"
                )
            ),
        )

        _custom_domain = "app.allotmint.io"
        _enable_custom_domain = _is_truthy_context(self.node.try_get_context("customDomain"))

        _certificate: acm.Certificate | None = None
        _hosted_zone: route53.IHostedZone | None = None
        if _enable_custom_domain:
            # ACM certificates for CloudFront must be in us-east-1; fail fast at synth time
            # so a mis-deployed stack surfaces immediately rather than at CloudFormation execution.
            # Note: when env= is omitted (environment-agnostic stack), self.region is an unresolved
            # CDK token and Token.is_unresolved returns True, so the check is skipped. A deployment
            # to the wrong region would then fail at CloudFormation execution time. Always pass
            # env=cdk.Environment(region="us-east-1") when enabling customDomain.
            if not Token.is_unresolved(self.region) and self.region != "us-east-1":
                raise ValueError(
                    f"customDomain requires deployment to us-east-1 (ACM certificates "
                    f"for CloudFront must reside there); got region={self.region!r}. "
                    f"Pass env=cdk.Environment(region='us-east-1') to the stack."
                )
            _hosted_zone_id = self.node.try_get_context("hostedZoneId") or ""
            if not _hosted_zone_id:
                raise ValueError(
                    "customDomain=true requires a 'hostedZoneId' context value "
                    "(e.g. --context hostedZoneId=Z1234567890ABCDEFGHIJ). "
                    "Find the ID in the Route53 console for allotmint.io."
                )
            _hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "Zone",
                hosted_zone_id=_hosted_zone_id,
                zone_name="allotmint.io",
            )
            _certificate = acm.Certificate(
                self,
                "SiteCertificate",
                domain_name=_custom_domain,
                validation=acm.CertificateValidation.from_dns(_hosted_zone),
            )

        _distribution_extra: dict = (
            {"domain_names": [_custom_domain], "certificate": _certificate}
            if _enable_custom_domain
            else {}
        )

        distribution = cloudfront.Distribution(
            self,
            "StaticSiteDistribution",
            default_root_object="index.html",
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            default_behavior=cloudfront.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=html_cache_policy,
                response_headers_policy=security_headers,
                compress=True,
                function_associations=[
                    cloudfront.FunctionAssociation(
                        function=redirect_fn,
                        event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            ),
            additional_behaviors={
                "assets/*": cloudfront.BehaviorOptions(
                    origin=s3_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=asset_cache_policy,
                    response_headers_policy=security_headers,
                    compress=True,
                )
            },
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(1),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(1),
                ),
            ],
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            **_distribution_extra,
        )

        if _enable_custom_domain and _hosted_zone is not None:
            route53.ARecord(
                self,
                "SiteARecord",
                zone=_hosted_zone,
                record_name="app",
                target=route53.RecordTarget.from_alias(
                    route53_targets.CloudFrontTarget(distribution)
                ),
            )

        ui_auth_pool = cognito.UserPool(
            self,
            "UiAuthUserPool",
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=ui_auth_removal_policy,
        )
        ui_auth_callback_url = (
            f"https://{_custom_domain}/"
            if _enable_custom_domain
            else Fn.join("", ["https://", distribution.domain_name, "/"])
        )
        ui_auth_client = ui_auth_pool.add_client(
            "UiAuthClient",
            # auth_flows gates the direct Cognito API auth endpoints (USER_SRP_AUTH,
            # USER_PASSWORD_AUTH). The hosted UI uses browser redirects and does not
            # go through these API flows. user_srp=True is kept to avoid enabling the
            # weaker ALLOW_USER_PASSWORD_AUTH endpoint on this public client.
            auth_flows=cognito.AuthFlow(user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=[ui_auth_callback_url],
                logout_urls=[ui_auth_callback_url],
            ),
            prevent_user_existence_errors=True,
        )
        # Backend-only client for CI smoke tests. USER_PASSWORD_AUTH is intentionally
        # enabled here so the deploy workflow can fetch a fresh token without SRP.
        # This client is never referenced in config.json or exposed to the browser.
        smoke_test_client = ui_auth_pool.add_client(
            "SmokeTestClient",
            auth_flows=cognito.AuthFlow(user_password=True),
            prevent_user_existence_errors=True,
        )
        ui_auth_domain_prefix = Fn.join("-", ["allotmint", Aws.ACCOUNT_ID, Aws.REGION])
        ui_auth_pool.add_domain(
            "UiAuthDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=ui_auth_domain_prefix,
            ),
        )
        ui_auth_domain = Fn.join(
            "",
            ["https://", ui_auth_domain_prefix, ".auth.", Aws.REGION, ".amazoncognito.com"],
        )

        frontend_dir = (
            Path(frontend_dist_path)
            if frontend_dist_path is not None
            else Path(__file__).resolve().parents[2] / "frontend" / "dist"
        )

        asset_deploy = s3_deployment.BucketDeployment(
            self,
            "DeployAssets",
            sources=[s3_deployment.Source.asset(str(frontend_dir))],
            destination_bucket=site_bucket,
            exclude=["*.html", "config.json"],  # deployed separately to control caching
            cache_control=[
                s3_deployment.CacheControl.max_age(Duration.days(365)),
                s3_deployment.CacheControl.immutable(),
            ],
            prune=True,
        )

        # Deploy HTML without triggering a CloudFront invalidation here.
        # The HTML cache TTL is short (5 minutes), so changes propagate quickly
        # without risking long invalidation waits that can fail the deployment.
        html_deploy = s3_deployment.BucketDeployment(
            self,
            "DeployHtml",
            sources=[s3_deployment.Source.asset(str(frontend_dir))],
            destination_bucket=site_bucket,
            exclude=["*"],
            include=["*.html"],
            cache_control=[s3_deployment.CacheControl.no_cache()],
            prune=False,
        )
        html_deploy.node.add_dependency(asset_deploy)

        config_deploy = s3_deployment.BucketDeployment(
            self,
            "DeployRuntimeConfig",
            sources=[
                s3_deployment.Source.json_data(
                    "config.json",
                    {
                        "apiBaseUrl": backend_url_param.value_as_string,
                        "awsUiAuth": {
                            "enabled": True,
                            "domain": ui_auth_domain,
                            "clientId": ui_auth_client.user_pool_client_id,
                            "redirectPath": "/",
                        },
                    },
                )
            ],
            destination_bucket=site_bucket,
            cache_control=[
                s3_deployment.CacheControl.no_cache(),
                s3_deployment.CacheControl.no_store(),
                s3_deployment.CacheControl.must_revalidate(),
            ],
            prune=False,
        )
        config_deploy.node.add_dependency(asset_deploy)

        # Grant the GitHub Actions deploy role changeset permissions so `cdk diff
        # --method=changeset` succeeds before BackendLambdaStack is deployed.
        # Placed in StaticSiteStack (deployed first in the workflow) rather than in
        # BackendLambdaStack so the grant is stable: BackendLambdaStack structural
        # changes cause CDK to regenerate inline policy names, briefly removing then
        # recreating the policy and leaving the diff step without changeset access.
        # Covers both stacks because `cdk diff` targets both. See #3192.
        github_deploy_role_arn = os.getenv("GITHUB_DEPLOY_ROLE_ARN", "")
        if github_deploy_role_arn:
            github_role = iam.Role.from_role_arn(
                self, "GithubDeployRole", github_deploy_role_arn, mutable=True
            )
            github_role.add_to_principal_policy(
                iam.PolicyStatement(
                    actions=[
                        "cloudformation:CreateChangeSet",
                        "cloudformation:DescribeChangeSet",
                        "cloudformation:DeleteChangeSet",
                    ],
                    resources=[
                        self.format_arn(
                            service="cloudformation",
                            resource="stack",
                            resource_name=f"{stack_name}/*",
                        )
                        for stack_name in (construct_id, "BackendLambdaStack")
                    ],
                )
            )

        CfnOutput(self, "SiteBucket", value=site_bucket.bucket_name)
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)
        CfnOutput(self, "DistributionDomain", value=distribution.domain_name)
        CfnOutput(self, "UiAuthUserPoolId", value=ui_auth_pool.user_pool_id)
        CfnOutput(self, "UiAuthUserPoolClientId", value=ui_auth_client.user_pool_client_id)
        CfnOutput(self, "SmokeTestUserPoolClientId", value=smoke_test_client.user_pool_client_id)
        CfnOutput(self, "UiAuthDomain", value=ui_auth_domain)
