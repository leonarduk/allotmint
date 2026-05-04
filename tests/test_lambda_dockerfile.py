"""Regression tests for Lambda Dockerfile dependency hygiene (issue #2810)."""

from pathlib import Path

DOCKERFILE = Path(__file__).parents[1] / "backend" / "Dockerfile.lambda"
REQUIREMENTS = Path(__file__).parents[1] / "backend" / "requirements.txt"


def test_awscli_not_installed_in_lambda_dockerfile():
    """awscli must not be installed in the Lambda image.

    awscli pulls newer botocore/s3transfer that conflict with boto3 pinned in
    requirements.txt.  Lambda functions use boto3 directly; awscli is not
    needed at runtime.
    """
    content = DOCKERFILE.read_text()
    assert "awscli" not in content, (
        "awscli must not be installed in Dockerfile.lambda — it causes "
        "botocore/s3transfer version conflicts with boto3 (see issue #2810)"
    )


def test_boto3_version_not_tightly_pinned():
    """boto3 must not be pinned to a minor-version ceiling in requirements.txt.

    A tight ~= 1.37.x pin would conflict with awscli or other packages that
    pull in a newer botocore.  Use >= with only a lower bound.
    """
    content = REQUIREMENTS.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("boto3"):
            assert "~=" not in stripped, (
                f"boto3 must not use ~= pin in requirements.txt (found: {stripped!r}). "
                "Use '>=' with only a lower bound to allow pip to resolve compatible "
                "botocore/s3transfer versions (see issue #2810)."
            )
            break
