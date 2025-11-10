from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.reports import (
    DEFAULT_TEMPLATE_ID,
    build_report_document,
    create_user_template,
    delete_user_template,
    get_template,
    list_template_metadata,
    report_to_csv,
    report_to_pdf,
    update_user_template,
    _parse_date,
)

router = APIRouter(tags=["reports"])


class TemplateColumnPayload(BaseModel):
    key: str = Field(..., description="Column key used in the report output")
    label: str = Field(..., description="Human readable column label")
    type: str = Field("string", description="Column type metadata")


class TemplateSectionPayload(BaseModel):
    id: str
    title: str
    source: str
    description: Optional[str] = None
    columns: List[TemplateColumnPayload]


class TemplateCreatePayload(BaseModel):
    template_id: str
    name: str
    description: Optional[str] = None
    sections: List[TemplateSectionPayload]


class TemplateUpdatePayload(BaseModel):
    name: str
    description: Optional[str] = None
    sections: List[TemplateSectionPayload]


@router.get("/reports/templates")
async def list_templates() -> List[dict]:
    return list_template_metadata()


@router.get("/reports/templates/{template_id}")
async def get_template_definition(template_id: str) -> dict:
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template.to_metadata()


@router.post("/reports/templates", status_code=status.HTTP_201_CREATED)
async def create_template(payload: TemplateCreatePayload) -> dict:
    try:
        template = create_user_template(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return template.to_metadata()


@router.put("/reports/templates/{template_id}")
async def update_template(
    template_id: str, payload: TemplateUpdatePayload
) -> dict:
    try:
        template = update_user_template(template_id, payload.model_dump())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return template.to_metadata()


@router.delete("/reports/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(template_id: str) -> Response:
    try:
        delete_user_template(template_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reports/{owner}")
async def owner_report(
    owner: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    format: str = "json",
):
    """Return summary report for ``owner``."""

    start_d = _parse_date(start)
    end_d = _parse_date(end)

    try:
        document = build_report_document(
            DEFAULT_TEMPLATE_ID, owner, start=start_d, end=end_d
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if format.lower() == "csv":
        content = report_to_csv(document)
        return Response(
            content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={owner}_report.csv"},
        )
    if format.lower() == "pdf":
        content = report_to_pdf(document)
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={owner}_report.pdf"},
        )
    return document.to_dict()


@router.get("/reports/{owner}/{template_id}")
async def owner_template_report(
    owner: str,
    template_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    format: str = "json",
):
    start_d = _parse_date(start)
    end_d = _parse_date(end)

    try:
        document = build_report_document(
            template_id, owner, start=start_d, end=end_d
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if format.lower() == "csv":
        content = report_to_csv(document)
        return Response(
            content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={owner}_{template_id}.csv"
            },
        )
    if format.lower() == "pdf":
        content = report_to_pdf(document)
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={owner}_{template_id}.pdf"
            },
        )
    return document.to_dict()

