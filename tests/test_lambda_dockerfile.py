"""Regression tests for Lambda Dockerfile and requirements dependency hygiene (issue #2810)."""

from pathlib import Path
import unittest

DOCKERFILE = Path(__file__).resolve().parents[1] / "backend" / "Dockerfile.lambda"
REQUIREMENTS = Path(__file__).resolve().parents[1] / "backend" / "requirements.txt"


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

    def test_boto3_version_not_tightly_pinned(self) -> None:
        """boto3 must not be pinned to a minor-version ceiling in requirements.txt.

        A tight ~= 1.37.x pin conflicts with packages that pull in a newer
        botocore. Use >= with only a lower bound.
        """
        content = REQUIREMENTS.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("boto3"):
                self.assertNotIn(
                    "~=",
                    stripped,
                    f"boto3 must not use ~= pin in requirements.txt (found: {stripped!r}). "
                    "Use '>=' with only a lower bound to allow pip to resolve compatible "
                    "botocore/s3transfer versions (see issue #2810).",
                )
                break
