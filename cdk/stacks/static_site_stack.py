from pathlib import Path

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
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

        security_headers = cloudfront.ResponseHeadersPolicy(
            self,
            "SecurityHeaders",
            comment="Security headers for static site",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                content_security_policy=cloudfront.ResponseSecurityHeadersContentSecurityPolicy(
                    content_security_policy="default-src 'self'; script-src 'self' https://accounts.google.com; frame-src 'self' https://accounts.google.com; frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
                    override=True,
                ),
                strict_transport_security=cloudfront.ResponseSecurityHeadersStrictTransportSecurity(
                    max_age=Duration.seconds(63072000),
                    include_subdomains=True,
                    preload=True,
                    override=True,
                ),
                content_type_options=cloudfront.ResponseSecurityHeadersContentTypeOptions(
                    override=True
                ),
                referrer_policy=cloudfront.ResponseSecurityHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=True,
                ),
            ),
        )

        distribution = cloudfront.Distribution(
            self,
            "StaticSiteDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_identity(
                    site_bucket, origin_access_identity=oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                response_headers_policy=security_headers,
            ),
            additional_behaviors={
                "assets/*": cloudfront.BehaviorOptions(
                    origin=origins.S3BucketOrigin.with_origin_access_identity(
                        site_bucket, origin_access_identity=oai
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    response_headers_policy=security_headers,
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
