"""The deploy workflow bakes the allotmint-pro release pinned in pyproject.toml (#11004)."""

from pathlib import Path

import pytest
import yaml

from scripts.pro_pin import pinned_tag

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-lambda.yml"


def test_pinned_tag_reads_the_pro_extra() -> None:
    assert pinned_tag() == "v0.14.0"


def test_pinned_tag_rejects_an_unpinned_extra(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project.optional-dependencies]\npro = ["allotmint-pro @ git+ssh://git@github.com/leonarduk/allotmint-pro.git@main"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not pinned"):
        pinned_tag(pyproject)


def _deploy_steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["deploy"]["steps"]


def test_deploy_builds_the_pro_wheel_before_cdk_deploy() -> None:
    steps = _deploy_steps()
    names = [step.get("name", "") for step in steps]

    checkout = steps[names.index("Checkout allotmint-pro at the pinned tag")]
    assert checkout["with"]["repository"] == "leonarduk/allotmint-pro"
    assert checkout["with"]["ref"] == "${{ steps.pro_pin.outputs.tag }}"
    assert checkout["with"]["path"] == ".pro-src"

    build = names.index("Build allotmint-pro wheel for the Lambda image")
    assert "--wheel-dir pro_wheels" in steps[build]["run"]
    assert build < names.index("Deploy StaticSiteStack auth resources")
    assert build < names.index("Deploy BackendLambdaStack")
