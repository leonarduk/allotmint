"""Routes for listing available AI models."""

from fastapi import APIRouter


# Static list of supported model identifiers. In a real deployment this could
# be sourced from configuration or an external registry.
MODEL_NAMES = ["gpt-4o-mini"]


router = APIRouter(prefix="/v1")


@router.get("/models")
def list_models() -> dict:
    """Return the available model identifiers."""
    return {
        "data": [{"id": name, "object": "model"} for name in MODEL_NAMES]
    }

