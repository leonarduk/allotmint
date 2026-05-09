from pathlib import Path

from aws_cdk import Aws, CfnOutput, CfnParameter, Duration, Fn, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
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
        # (Ref / Fn::GetAtt / Fn::Select) — Fn::ImportValue is explicitly rejected
        # by CDK's renderData validator. A CfnParameter produces a Ref token and
        # therefore works. The real URL is supplied at deploy time via
        # `--parameters StaticSiteStack:BackendApiUrl=<url>`.
        # Pass api_base_url here to use it as the default (useful in tests).
        backend_url_param = CfnParameter(
            self,
            "BackendApiUrl",
            type="String",
            default=api_base_url or "",
            description=(
                "Backend API base URL — override at deploy time with the "
                "BackendLambdaStack BackendApiUrl output."
            ),
        )

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
                # Allow Google Identity Services script and iframe, and Cognito
                # hosted UI token exchange (amazoncognito.com != amazonaws.com).
                content_security_policy=cloudfront.ResponseHeadersContentSecurityPolicy(
                    content_security_policy=(
                        "default-src 'self'; "
                        "script-src 'self' https://accounts.google.com/gsi/client; "
                        f"connect-src 'self' {backend_url_param.value_as_string} "
                        "https://*.amazoncognito.com; "
                        "frame-src 'self' https://accounts.google.com/gsi/; "
                        "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
                    ),
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
        # then to legacy S3Origin — each path grants CloudFront bucket read.
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
        )

        ui_auth_pool, ui_auth_client, ui_auth_domain = self._create_ui_auth(
            distribution=distribution,
            removal_policy=ui_auth_removal_policy,
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

        CfnOutput(self, "SiteBucket", value=site_bucket.bucket_name)
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)
        CfnOutput(self, "DistributionDomain", value=distribution.domain_name)
        CfnOutput(self, "UiAuthUserPoolId", value=ui_auth_pool.user_pool_id)
        CfnOutput(self, "UiAuthUserPoolClientId", value=ui_auth_client.user_pool_client_id)
        CfnOutput(self, "UiAuthDomain", value=ui_auth_domain)

    def _create_ui_auth(
        self,
        *,
        distribution: cloudfront.Distribution,
        removal_policy: RemovalPolicy,
    ) -> tuple[cognito.UserPool, cognito.UserPoolClient, str]:
        ui_auth_pool = cognito.UserPool(
            self,
            "UiAuthUserPool",
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=removal_policy,
        )
        ui_auth_callback_url = Fn.join("", ["https://", distribution.domain_name, "/"])
        ui_auth_client = ui_auth_pool.add_client(
            "UiAuthClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
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
        return ui_auth_pool, ui_auth_client, ui_auth_domain
