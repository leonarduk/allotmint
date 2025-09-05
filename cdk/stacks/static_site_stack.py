from pathlib import Path

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3_deployment,
)
from constructs import Construct


class StaticSiteStack(Stack):
    """CDK stack that provisions S3 + CloudFront for the frontend."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        site_bucket = s3.Bucket(
            self,
            "StaticSiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Allow CloudFront to read the bucket without making it public
        oai = cloudfront.OriginAccessIdentity(self, "StaticSiteOAI")
        site_bucket.grant_read(oai)

        s3_origin = origins.S3BucketOrigin.with_origin_access_identity(
            site_bucket, origin_access_identity=oai
        )

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

        asset_headers = cloudfront.ResponseHeadersPolicy(
            self,
            "AssetsResponseHeaders",
            custom_headers_behavior=cloudfront.ResponseCustomHeadersBehavior(
                custom_headers=[
                    cloudfront.ResponseCustomHeader(
                        header="Cache-Control",
                        value="public, max-age=31536000, immutable",
                        override=True,
                    )
                ]
            ),
        )

        html_headers = cloudfront.ResponseHeadersPolicy(
            self,
            "HtmlResponseHeaders",
            custom_headers_behavior=cloudfront.ResponseCustomHeadersBehavior(
                custom_headers=[
                    cloudfront.ResponseCustomHeader(
                        header="Cache-Control",
                        value="public, max-age=300",
                        override=True,
                    )
                ]
        redirect_fn = cloudfront.Function(
            self,
            "ViewerRequestFn",
            code=cloudfront.FunctionCode.from_file(
                file_path=str(
                    Path(__file__).resolve().parents[1]
                    / "functions"
                    / "viewer-request.js"
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
                response_headers_policy=html_headers,
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
                    response_headers_policy=asset_headers,
                    compress=True,
                )
            },
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )

        frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        s3_deployment.BucketDeployment(
            self,
            "DeployStaticSite",
            sources=[s3_deployment.Source.asset(str(frontend_dir))],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )
