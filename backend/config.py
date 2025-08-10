from __future__ import annotations

import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field


class Config(BaseModel):
    env: str = "test"
    skip_snapshot_warm: bool = False
    cors_allow_origins: List[str] = Field(default_factory=lambda: ["*"])
    docs_url: str | None = "/docs"


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from YAML file and environment variables."""
    config_path = Path(path) if path else Path(__file__).resolve().parent.parent / "config.yaml"
    data: dict = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}

    env = os.getenv("ALLOTMINT_ENV")
    if env is not None:
        data["env"] = env

    skip = os.getenv("ALLOTMINT_SKIP_SNAPSHOT_WARM")
    if skip is not None:
        data["skip_snapshot_warm"] = skip.lower() in {"1", "true", "yes"}

    cors = os.getenv("ALLOTMINT_CORS_ALLOW_ORIGINS")
    if cors is not None:
        data["cors_allow_origins"] = [c.strip() for c in cors.split(",") if c.strip()]

    docs = os.getenv("ALLOTMINT_DOCS_URL")
    if docs is not None:
        data["docs_url"] = docs

    return Config(**data)


# Convenience config object reused by modules that don't need dynamic reload
config = load_config()
