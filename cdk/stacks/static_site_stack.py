from pathlib import Path

from aws_cdk import (
    Stack,
    RemovalPolicy,
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

        distribution = cloudfront.Distribution(
            self,
            "StaticSiteDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_identity(
                    site_bucket, origin_access_identity=oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )

        frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"

        # Deploy hashed assets first. These files include a content hash in the
        # filename so existing versions can remain cached indefinitely. They do
        # not require CloudFront invalidation.
        s3_deployment.BucketDeployment(
            self,
            "DeployStaticAssets",
            sources=[
                s3_deployment.Source.asset(
                    str(frontend_dir),
                    exclude=["*.html"],
                )
            ],
            destination_bucket=site_bucket,
            prune=False,
        )

        # Upload HTML (and any other route files) after assets so the new HTML
        # references are never served before the assets exist. Only the HTML
        # files are invalidated on CloudFront which keeps the cache warm for all
        # hashed assets.
        s3_deployment.BucketDeployment(
            self,
            "DeployStaticHtml",
            sources=[
                s3_deployment.Source.asset(
                    str(frontend_dir),
                    exclude=["*", "!*.html"],
                )
            ],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*.html"],
            prune=False,
        )
