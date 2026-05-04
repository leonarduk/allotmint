from pathlib import Path
import unittest


DOCKERFILE = Path(__file__).resolve().parents[1] / "backend" / "Dockerfile.lambda"


class LambdaDockerfileTests(unittest.TestCase):
    def test_lambda_dockerfile_avoids_build_only_sync_tools(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")

        self.assertNotIn(
            "pip install awscli",
            text,
            "Lambda Dockerfile should not install awscli into the application "
            "Python environment because it can pull in incompatible botocore "
            "and s3transfer versions.",
        )
        self.assertNotIn(
            "dnf install -y git",
            text,
            "Lambda Dockerfile should not install git for build-time data sync "
            "because deployment pre-syncs data before the image build.",
        )
        self.assertIn(
            "COPY data/ /var/task/data/",
            text,
            "Lambda Dockerfile is expected to copy pre-synced data into the "
            "image rather than fetching it during the build.",
        )
