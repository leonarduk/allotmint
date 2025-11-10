from __future__ import annotations

import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import pandas as pd

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ModuleNotFoundError:  # pragma: no cover - exercised in tests when missing
    letter = None
    canvas = None

from backend.common import portfolio_utils
from backend.config import config

logger = logging.getLogger(__name__)


_TEMPLATE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_SECTION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


@dataclass(slots=True)
class ReportColumnSchema:
    key: str
    label: str
    type: str = "string"

    def to_dict(self) -> Dict[str, str]:
        return {"key": self.key, "label": self.label, "type": self.type}


@dataclass(slots=True)
class ReportSectionSchema:
    id: str
    title: str
    source: str
    description: str | None = None
    columns: Sequence[ReportColumnSchema] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "columns": [column.to_dict() for column in self.columns],
        }


@dataclass(slots=True)
class ReportTemplate:
    template_id: str
    name: str
    description: str
    sections: Sequence[ReportSectionSchema]
    builtin: bool = True

    def to_metadata(self) -> Dict[str, object]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "builtin": self.builtin,
            "sections": [section.to_dict() for section in self.sections],
        }


PERFORMANCE_SUMMARY_TEMPLATE = ReportTemplate(
    template_id="performance-summary",
    name="Performance summary",
    description="Portfolio performance metrics and history for a single owner",
    sections=(
        ReportSectionSchema(
            id="metrics",
            title="Performance metrics",
            source="performance.metrics",
            description="Key return and cashflow metrics for the selected period",
            columns=(
                ReportColumnSchema("metric", "Metric"),
                ReportColumnSchema("value", "Value"),
                ReportColumnSchema("units", "Units"),
            ),
        ),
        ReportSectionSchema(
            id="performance-history",
            title="Performance history",
            source="performance.history",
            description="Daily performance observations used for the summary",
            columns=(
                ReportColumnSchema("date", "Date", type="date"),
                ReportColumnSchema("value", "Value", type="number"),
                ReportColumnSchema("daily_return", "Daily return", type="number"),
                ReportColumnSchema("weekly_return", "Weekly return", type="number"),
                ReportColumnSchema(
                    "cumulative_return", "Cumulative return", type="number"
                ),
                ReportColumnSchema("drawdown", "Drawdown", type="number"),
            ),
        ),
    ),
)


TRANSACTIONS_TEMPLATE = ReportTemplate(
    template_id="transactions",
    name="Transactions list",
    description="Chronological list of transactions recorded for the owner",
    sections=(
        ReportSectionSchema(
            id="transactions",
            title="Transactions",
            source="transactions",
            description="Raw transactions filtered by the provided window",
            columns=(
                ReportColumnSchema("date", "Date", type="date"),
                ReportColumnSchema("type", "Type"),
                ReportColumnSchema("description", "Description"),
                ReportColumnSchema("amount_gbp", "Amount (GBP)", type="number"),
                ReportColumnSchema("currency", "Currency"),
            ),
        ),
    ),
)


ALLOCATION_BREAKDOWN_TEMPLATE = ReportTemplate(
    template_id="allocation-breakdown",
    name="Allocation breakdown",
    description="Snapshot of holdings and current valuation for the latest trading day",
    sections=(
        ReportSectionSchema(
            id="allocation",
            title="Allocation breakdown",
            source="allocation",
            description="Instrument-level allocation snapshot at the reporting date",
            columns=(
                ReportColumnSchema("ticker", "Ticker"),
                ReportColumnSchema("exchange", "Exchange"),
                ReportColumnSchema("units", "Units", type="number"),
                ReportColumnSchema("price", "Price", type="number"),
                ReportColumnSchema("value", "Value", type="number"),
            ),
        ),
    ),
)


BUILTIN_TEMPLATES: Dict[str, ReportTemplate] = {
    template.template_id: template
    for template in (
        PERFORMANCE_SUMMARY_TEMPLATE,
        TRANSACTIONS_TEMPLATE,
        ALLOCATION_BREAKDOWN_TEMPLATE,
    )
}


def iter_builtin_templates() -> Iterable[ReportTemplate]:
    return BUILTIN_TEMPLATES.values()


def get_builtin_template(template_id: str) -> ReportTemplate | None:
    return BUILTIN_TEMPLATES.get(template_id)


DEFAULT_TEMPLATE_ID = PERFORMANCE_SUMMARY_TEMPLATE.template_id


@dataclass
class ReportData:
    owner: str
    start: Optional[date]
    end: Optional[date]
    realized_gains_gbp: float
    income_gbp: float
    cumulative_return: Optional[float]
    max_drawdown: Optional[float]
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        data = {
            "owner": self.owner,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "realized_gains_gbp": round(self.realized_gains_gbp, 2),
            "income_gbp": round(self.income_gbp, 2),
            "cumulative_return": self.cumulative_return,
            "max_drawdown": self.max_drawdown,
        }
        if self.history:
            data["history"] = self.history
        return data


@dataclass(slots=True)
class ReportSectionData:
    schema: ReportSectionSchema
    rows: Sequence[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.schema.id,
            "title": self.schema.title,
            "description": self.schema.description,
            "source": self.schema.source,
            "columns": [column.to_dict() for column in self.schema.columns],
            "rows": [dict(row) for row in self.rows],
        }


@dataclass(slots=True)
class ReportDocument:
    template: ReportTemplate
    owner: str
    generated_at: datetime
    parameters: Dict[str, Any]
    sections: Sequence[ReportSectionData]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template": self.template.to_metadata(),
            "owner": self.owner,
            "generated_at": self.generated_at.astimezone(UTC).isoformat(),
            "parameters": self.parameters,
            "sections": [section.to_dict() for section in self.sections],
        }


class TemplateStore:
    """Abstract interface for user-defined template storage."""

    def list_templates(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_template(self, template_id: str) -> Dict[str, Any] | None:
        raise NotImplementedError

    def create_template(self, definition: Dict[str, Any]) -> None:
        raise NotImplementedError

    def update_template(self, definition: Dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_template(self, template_id: str) -> None:
        raise NotImplementedError


class FileTemplateStore(TemplateStore):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, template_id: str) -> Path:
        safe_id = _validate_template_id(template_id)
        return self.root / f"{safe_id}.json"

    def list_templates(self) -> List[Dict[str, Any]]:
        templates: List[Dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("failed to load report template %s: %s", path, exc)
                continue
            payload.setdefault("template_id", path.stem)
            try:
                templates.append(_validate_template_payload(payload))
            except ValueError as exc:
                logger.warning("invalid template definition in %s: %s", path, exc)
        return templates

    def get_template(self, template_id: str) -> Dict[str, Any] | None:
        path = self._path_for(template_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("failed to load report template %s: %s", path, exc)
            return None
        payload.setdefault("template_id", template_id)
        try:
            return _validate_template_payload(payload)
        except ValueError as exc:
            logger.warning("invalid template definition in %s: %s", path, exc)
            return None

    def create_template(self, definition: Dict[str, Any]) -> None:
        path = self._path_for(definition["template_id"])
        if path.exists():
            raise FileExistsError(f"Template {definition['template_id']} already exists")
        path.write_text(json.dumps(definition, indent=2, sort_keys=True), "utf-8")

    def update_template(self, definition: Dict[str, Any]) -> None:
        path = self._path_for(definition["template_id"])
        if not path.exists():
            raise FileNotFoundError(f"Template {definition['template_id']} not found")
        path.write_text(json.dumps(definition, indent=2, sort_keys=True), "utf-8")

    def delete_template(self, template_id: str) -> None:
        path = self._path_for(template_id)
        if not path.exists():
            raise FileNotFoundError(f"Template {template_id} not found")
        path.unlink()


class DynamoTemplateStore(TemplateStore):
    def __init__(self, table_name: str):
        try:
            import boto3  # type: ignore
            from botocore.exceptions import ClientError  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime
            raise RuntimeError("boto3 is required for Dynamo template storage") from exc

        self._table = boto3.resource("dynamodb").Table(table_name)
        self._client_error = ClientError

    def list_templates(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        params: Dict[str, Any] = {}
        while True:
            response = self._table.scan(**params)
            items.extend(response.get("Items", []))
            token = response.get("LastEvaluatedKey")
            if not token:
                break
            params["ExclusiveStartKey"] = token
        templates: List[Dict[str, Any]] = []
        for item in items:
            raw = item.get("definition")
            try:
                payload = json.loads(raw) if isinstance(raw, str) else dict(item)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON payload stored in Dynamo for template")
                continue
            try:
                templates.append(_validate_template_payload(payload))
            except ValueError as exc:
                logger.warning("invalid template definition in Dynamo: %s", exc)
        return templates

    def get_template(self, template_id: str) -> Dict[str, Any] | None:
        response = self._table.get_item(Key={"template_id": template_id})
        item = response.get("Item")
        if not item:
            return None
        raw = item.get("definition")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else dict(item)
        except json.JSONDecodeError:
            logger.warning("invalid JSON payload for template %s", template_id)
            return None
        try:
            return _validate_template_payload(payload)
        except ValueError as exc:
            logger.warning("invalid template definition for %s: %s", template_id, exc)
            return None

    def create_template(self, definition: Dict[str, Any]) -> None:
        try:
            self._table.put_item(
                Item={
                    "template_id": definition["template_id"],
                    "definition": json.dumps(definition),
                },
                ConditionExpression="attribute_not_exists(template_id)",
            )
        except self._client_error as exc:  # pragma: no cover - requires AWS
            raise RuntimeError(f"Failed to create template {definition['template_id']}: {exc}")

    def update_template(self, definition: Dict[str, Any]) -> None:
        try:
            self._table.put_item(
                Item={
                    "template_id": definition["template_id"],
                    "definition": json.dumps(definition),
                },
                ConditionExpression="attribute_exists(template_id)",
            )
        except self._client_error as exc:  # pragma: no cover - requires AWS
            raise RuntimeError(f"Failed to update template {definition['template_id']}: {exc}")

    def delete_template(self, template_id: str) -> None:
        try:
            self._table.delete_item(
                Key={"template_id": template_id},
                ConditionExpression="attribute_exists(template_id)",
            )
        except self._client_error as exc:  # pragma: no cover - requires AWS
            raise RuntimeError(f"Failed to delete template {template_id}: {exc}")


@lru_cache(maxsize=1)
def get_template_store() -> TemplateStore:
    if config.app_env == "aws":
        table_name = os.getenv("REPORT_TEMPLATES_TABLE")
        if not table_name:
            raise RuntimeError(
                "REPORT_TEMPLATES_TABLE environment variable is required in AWS"
            )
        return DynamoTemplateStore(table_name)
    root = config.data_root / "reports"
    return FileTemplateStore(root)


def _validate_template_id(template_id: str) -> str:
    if not isinstance(template_id, str):
        raise ValueError("template_id must be a string")
    candidate = template_id.strip()
    if not candidate:
        raise ValueError("template_id is required")
    if not _TEMPLATE_ID_RE.fullmatch(candidate):
        raise ValueError(
            "template_id must contain only letters, numbers, dashes or underscores (max 64 chars)"
        )
    return candidate


def _validate_section_id(section_id: str) -> str:
    if not isinstance(section_id, str):
        raise ValueError("section id must be a string")
    candidate = section_id.strip()
    if not candidate:
        raise ValueError("section id is required")
    if not _SECTION_ID_RE.fullmatch(candidate):
        raise ValueError(
            "section id must contain only letters, numbers, dashes or underscores (max 64 chars)"
        )
    return candidate


@dataclass(slots=True)
class ReportContext:
    owner: str
    start: Optional[date]
    end: Optional[date]
    _summary: ReportData | None = None
    _performance: Dict[str, Any] | None = None
    _transactions: List[Dict[str, Any]] | None = None
    _allocation: List[Dict[str, Any]] | None = None

    def summary(self) -> ReportData:
        if self._summary is None:
            summary, perf = _compile_summary(self.owner, self.start, self.end)
            self._summary = summary
            self._performance = perf
        return self._summary

    def performance(self) -> Dict[str, Any]:
        if self._performance is None:
            self.summary()
        return self._performance or {}

    def transactions(self) -> List[Dict[str, Any]]:
        if self._transactions is None:
            raw = _load_transactions(self.owner)
            filtered: List[Dict[str, Any]] = []
            for item in raw:
                record = _normalise_transaction(item, self.start, self.end)
                if record is not None:
                    filtered.append(record)
            filtered.sort(key=lambda row: (row.get("date") or "", row.get("type") or ""))
            self._transactions = filtered
        return list(self._transactions)

    def allocation(self) -> List[Dict[str, Any]]:
        if self._allocation is None:
            perf = self.performance()
            if self.end:
                target = self.end.isoformat()
            else:
                target = perf.get("reporting_date")
            if not target:
                target = date.today().isoformat()
            try:
                rows = portfolio_utils.portfolio_value_breakdown(self.owner, target)
            except (FileNotFoundError, ValueError):
                rows = []
            normalised: List[Dict[str, Any]] = []
            for row in rows:
                normalised.append(
                    {
                        "ticker": row.get("ticker"),
                        "exchange": row.get("exchange"),
                        "units": _round_if_number(row.get("units"), 4),
                        "price": _round_if_number(row.get("price"), 4),
                        "value": _round_if_number(row.get("value"), 2),
                    }
                )
            normalised.sort(key=lambda item: (item.get("value") or 0.0), reverse=True)
            self._allocation = normalised
        return list(self._allocation)


def _round_if_number(value: Any, digits: int) -> Optional[float]:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits)


def _normalise_transaction(
    item: Dict[str, Any], start: Optional[date], end: Optional[date]
) -> Dict[str, Any] | None:
    date_str = item.get("date")
    tx_date: Optional[date]
    tx_date = None
    if isinstance(date_str, str):
        try:
            tx_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            tx_date = None
    if start and tx_date and tx_date < start:
        return None
    if end and tx_date and tx_date > end:
        return None
    amount_minor = item.get("amount_minor")
    try:
        amount = float(amount_minor) / 100.0
    except (TypeError, ValueError):
        amount = 0.0
    currency_raw = item.get("currency")
    currency = currency_raw.upper() if isinstance(currency_raw, str) else "GBP"
    description = ""
    for key in ("description", "narrative", "note", "symbol", "security"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            description = value.strip()
            break
    tx_type = (item.get("type") or "").upper()
    return {
        "date": tx_date.isoformat() if tx_date else (date_str if isinstance(date_str, str) else None),
        "type": tx_type,
        "description": description,
        "amount_gbp": round(amount, 2),
        "currency": currency,
    }


SectionBuilder = Callable[[ReportContext, ReportSectionSchema], Sequence[Dict[str, Any]]]


def _build_metrics_section(
    context: ReportContext, section: ReportSectionSchema
) -> Sequence[Dict[str, Any]]:
    summary = context.summary()
    rows = [
        {"metric": "Owner", "value": summary.owner, "units": ""},
        {
            "metric": "Period start",
            "value": summary.start.isoformat() if summary.start else None,
            "units": "",
        },
        {
            "metric": "Period end",
            "value": summary.end.isoformat() if summary.end else None,
            "units": "",
        },
        {
            "metric": "Realized gains",
            "value": round(summary.realized_gains_gbp, 2),
            "units": "GBP",
        },
        {
            "metric": "Income",
            "value": round(summary.income_gbp, 2),
            "units": "GBP",
        },
        {
            "metric": "Cumulative return",
            "value": _round_if_number(summary.cumulative_return, 4),
            "units": "ratio",
        },
        {
            "metric": "Max drawdown",
            "value": _round_if_number(summary.max_drawdown, 4),
            "units": "ratio",
        },
        {
            "metric": "Transactions",
            "value": len(context.transactions()),
            "units": "count",
        },
    ]
    return rows


def _build_history_section(
    context: ReportContext, section: ReportSectionSchema
) -> Sequence[Dict[str, Any]]:
    history_rows: List[Dict[str, Any]] = []
    for row in context.summary().history:
        history_rows.append(
            {
                "date": row.get("date"),
                "value": _round_if_number(row.get("value"), 2),
                "daily_return": _round_if_number(row.get("daily_return"), 4),
                "weekly_return": _round_if_number(row.get("weekly_return"), 4),
                "cumulative_return": _round_if_number(row.get("cumulative_return"), 4),
                "drawdown": _round_if_number(row.get("drawdown"), 4),
            }
        )
    return history_rows


def _build_transactions_section(
    context: ReportContext, section: ReportSectionSchema
) -> Sequence[Dict[str, Any]]:
    return context.transactions()


def _build_allocation_section(
    context: ReportContext, section: ReportSectionSchema
) -> Sequence[Dict[str, Any]]:
    return context.allocation()


SECTION_BUILDERS: Dict[str, SectionBuilder] = {
    "performance.metrics": _build_metrics_section,
    "performance.history": _build_history_section,
    "transactions": _build_transactions_section,
    "allocation": _build_allocation_section,
}


def _validate_template_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Template definition must be a JSON object")

    template_id_raw = payload.get("template_id")
    template_id = _validate_template_id(template_id_raw or "")

    name_raw = payload.get("name")
    name = str(name_raw).strip() if name_raw is not None else ""
    if not name:
        raise ValueError("Template name is required")

    description_raw = payload.get("description")
    description = (
        str(description_raw).strip()
        if description_raw is not None
        else ""
    )

    sections_raw = payload.get("sections")
    if not isinstance(sections_raw, list) or not sections_raw:
        raise ValueError("Template must define at least one section")

    sections: List[Dict[str, Any]] = []
    seen_section_ids: set[str] = set()
    for section_raw in sections_raw:
        if not isinstance(section_raw, dict):
            raise ValueError("Each section must be a JSON object")
        section_id = _validate_section_id(section_raw.get("id") or "")
        if section_id in seen_section_ids:
            raise ValueError(f"Duplicate section id '{section_id}'")
        seen_section_ids.add(section_id)

        title_raw = section_raw.get("title")
        title = str(title_raw).strip() if title_raw is not None else ""
        if not title:
            raise ValueError(f"Section '{section_id}' requires a title")

        source_raw = section_raw.get("source")
        source = str(source_raw).strip() if source_raw is not None else ""
        if source not in SECTION_BUILDERS:
            raise ValueError(f"Unsupported section source '{source}'")

        section_description_raw = section_raw.get("description")
        if section_description_raw is None:
            section_description = None
        else:
            section_description = str(section_description_raw).strip() or None

        columns_raw = section_raw.get("columns")
        if not isinstance(columns_raw, list) or not columns_raw:
            raise ValueError(f"Section '{section_id}' must define at least one column")

        columns: List[Dict[str, str]] = []
        seen_columns: set[str] = set()
        for column_raw in columns_raw:
            if not isinstance(column_raw, dict):
                raise ValueError(f"Section '{section_id}' columns must be objects")
            key_raw = column_raw.get("key")
            key = str(key_raw).strip() if key_raw is not None else ""
            if not key:
                raise ValueError(f"Section '{section_id}' column missing key")
            if key in seen_columns:
                raise ValueError(f"Section '{section_id}' has duplicate column '{key}'")
            seen_columns.add(key)
            label_raw = column_raw.get("label")
            label = str(label_raw).strip() if label_raw is not None else ""
            if not label:
                label = key
            type_raw = column_raw.get("type")
            col_type = str(type_raw).strip() if type_raw is not None else "string"
            if not col_type:
                col_type = "string"
            columns.append({"key": key, "label": label, "type": col_type})

        sections.append(
            {
                "id": section_id,
                "title": title,
                "description": section_description,
                "source": source,
                "columns": columns,
            }
        )

    return {
        "template_id": template_id,
        "name": name,
        "description": description,
        "sections": sections,
    }


def _materialise_template(definition: Dict[str, Any], *, builtin: bool) -> ReportTemplate:
    sections: List[ReportSectionSchema] = []
    for section in definition.get("sections", []):
        columns = tuple(
            ReportColumnSchema(
                key=column["key"],
                label=column.get("label", column["key"]),
                type=column.get("type", "string"),
            )
            for column in section.get("columns", [])
        )
        sections.append(
            ReportSectionSchema(
                id=section["id"],
                title=section["title"],
                description=section.get("description"),
                source=section["source"],
                columns=columns,
            )
        )
    return ReportTemplate(
        template_id=definition["template_id"],
        name=definition["name"],
        description=definition.get("description", ""),
        sections=tuple(sections),
        builtin=builtin,
    )


def list_templates(store: TemplateStore | None = None) -> List[ReportTemplate]:
    templates: Dict[str, ReportTemplate] = {
        template.template_id: template for template in iter_builtin_templates()
    }
    store = store or get_template_store()
    try:
        for definition in store.list_templates():
            template_id = definition["template_id"]
            if template_id in templates:
                logger.warning(
                    "Ignoring user-defined template %s because it clashes with a built-in",
                    template_id,
                )
                continue
            templates[template_id] = _materialise_template(definition, builtin=False)
    except Exception as exc:
        logger.warning("Failed to list user templates: %s", exc)
    return sorted(templates.values(), key=lambda template: template.template_id)


def list_template_metadata(store: TemplateStore | None = None) -> List[Dict[str, Any]]:
    return [template.to_metadata() for template in list_templates(store=store)]


def get_template(template_id: str, store: TemplateStore | None = None) -> ReportTemplate | None:
    builtin = get_builtin_template(template_id)
    if builtin:
        return builtin
    store = store or get_template_store()
    definition = store.get_template(template_id)
    if not definition:
        return None
    return _materialise_template(definition, builtin=False)


def create_user_template(
    definition: Dict[str, Any], store: TemplateStore | None = None
) -> ReportTemplate:
    payload = _validate_template_payload(definition)
    if get_builtin_template(payload["template_id"]):
        raise ValueError("Cannot overwrite built-in template")
    store = store or get_template_store()
    if store.get_template(payload["template_id"]):
        raise ValueError(f"Template {payload['template_id']} already exists")
    store.create_template(payload)
    return _materialise_template(payload, builtin=False)


def update_user_template(
    template_id: str, definition: Dict[str, Any], store: TemplateStore | None = None
) -> ReportTemplate:
    payload = _validate_template_payload({**definition, "template_id": template_id})
    if get_builtin_template(template_id):
        raise ValueError("Cannot update built-in template")
    store = store or get_template_store()
    if not store.get_template(template_id):
        raise FileNotFoundError(f"Template {template_id} not found")
    store.update_template(payload)
    return _materialise_template(payload, builtin=False)


def delete_user_template(template_id: str, store: TemplateStore | None = None) -> None:
    if get_builtin_template(template_id):
        raise ValueError("Cannot delete built-in template")
    store = store or get_template_store()
    if not store.get_template(template_id):
        raise FileNotFoundError(f"Template {template_id} not found")
    store.delete_template(template_id)


def build_report_document(
    template_id: str,
    owner: str,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    store: TemplateStore | None = None,
) -> ReportDocument:
    template = get_template(template_id, store=store)
    if template is None:
        raise ValueError(f"Unknown report template '{template_id}'")

    context = ReportContext(owner=owner, start=start, end=end)
    sections: List[ReportSectionData] = []
    for schema in template.sections:
        builder = SECTION_BUILDERS.get(schema.source)
        if builder is None:
            logger.warning("No builder registered for section source %s", schema.source)
            rows: Sequence[Dict[str, Any]] = []
        else:
            rows = builder(context, schema)
        sections.append(ReportSectionData(schema=schema, rows=tuple(rows)))

    params: Dict[str, Any] = {}
    if start:
        params["start"] = start.isoformat()
    if end:
        params["end"] = end.isoformat()

    return ReportDocument(
        template=template,
        owner=owner,
        generated_at=datetime.now(tz=UTC),
        parameters=params,
        sections=tuple(sections),
    )


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _transaction_roots() -> Iterable[str]:
    if config.app_env == "aws":
        yield Path("transactions").as_posix()
        return

    roots: List[str] = []
    if config.transactions_output_root:
        roots.append(Path(config.transactions_output_root).as_posix())
    if config.accounts_root:
        roots.append(Path(config.accounts_root).as_posix())
    roots.append((config.data_root / "transactions").as_posix())

    seen: set[str] = set()
    for r in roots:
        path = Path(r)
        posix = path.as_posix()
        if posix not in seen and path.exists():
            seen.add(posix)
            yield posix


def _load_transactions(owner: str) -> List[dict]:
    records: List[dict] = []
    if config.app_env == "aws":
        bucket = os.getenv("DATA_BUCKET")
        if not bucket:
            raise RuntimeError("DATA_BUCKET environment variable is required in AWS")
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime
            raise RuntimeError("boto3 is required for loading transactions from S3") from exc
        s3 = boto3.client("s3")
        for root in _transaction_roots():
            prefix = f"{root.rstrip('/')}/{owner}/"
            paginator = s3.get_paginator("list_objects_v2")
            try:
                pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
            except (BotoCoreError, ClientError) as exc:
                logger.warning("failed to paginate S3 objects for prefix %s: %s", prefix, exc)
                continue
            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj.get("Key", "")
                    if not key.endswith("_transactions.json"):
                        continue
                    try:
                        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                        data = json.loads(body)
                    except (BotoCoreError, ClientError, json.JSONDecodeError) as exc:
                        logger.warning("failed to load %s from bucket %s: %s", key, bucket, exc)
                        continue
                    txs = data.get("transactions") if isinstance(data, dict) else None
                    if isinstance(txs, list):
                        records.extend(txs)
        return records
    for root in _transaction_roots():
        owner_dir = Path(root) / owner
        if not owner_dir.exists():
            continue
        for path in owner_dir.glob("*_transactions.json"):
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("failed to read %s: %s", path, exc)
                continue
            txs = data.get("transactions") if isinstance(data, dict) else None
            if isinstance(txs, list):
                records.extend(txs)
    return records


def _compile_summary(owner: str, start: Optional[date] = None, end: Optional[date] = None) -> tuple[ReportData, Dict[str, Any]]:
    txs = _load_transactions(owner)
    realized = 0.0
    income = 0.0
    for t in txs:
        try:
            d = datetime.fromisoformat(t.get("date")) if t.get("date") else None
        except Exception:
            d = None
        if start and d and d.date() < start:
            continue
        if end and d and d.date() > end:
            continue
        amount = float(t.get("amount_minor") or 0.0) / 100.0
        typ = (t.get("type") or "").upper()
        if typ == "SELL":
            realized += amount
        elif typ in {"DIVIDEND", "INTEREST"}:
            income += amount

    perf = portfolio_utils.compute_owner_performance(owner)
    hist = perf.get("history", [])
    if start or end:
        filtered: List[dict] = []
        for row in hist:
            try:
                d = datetime.fromisoformat(row["date"]).date()
            except Exception:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            filtered.append(row)
        hist = filtered
    cumulative = hist[-1]["cumulative_return"] if hist else None
    data = ReportData(
        owner=owner,
        start=start,
        end=end,
        realized_gains_gbp=realized,
        income_gbp=income,
        cumulative_return=cumulative,
        max_drawdown=perf.get("max_drawdown"),
        history=hist,
    )
    return data, perf


def compile_report(owner: str, start: Optional[date] = None, end: Optional[date] = None) -> ReportData:
    data, _perf = _compile_summary(owner, start=start, end=end)
    return data


def _section_to_dataframe(section: ReportSectionData) -> pd.DataFrame:
    rows = [dict(row) for row in section.rows]
    df = pd.DataFrame(rows)
    if not df.empty:
        column_order = [column.key for column in section.schema.columns]
        for col in column_order:
            if col not in df.columns:
                df[col] = None
        df = df[column_order]
        rename_map = {column.key: column.label for column in section.schema.columns}
        df = df.rename(columns=rename_map)
    else:
        df = pd.DataFrame(
            columns=[column.label for column in section.schema.columns]
        )
    return df


def report_to_csv(document: ReportDocument) -> bytes:
    buf = io.StringIO()
    buf.write(f"# Template: {document.template.name}\n")
    buf.write(f"# Owner: {document.owner}\n")
    if document.parameters:
        for key, value in sorted(document.parameters.items()):
            buf.write(f"# {key}: {value}\n")
    for idx, section in enumerate(document.sections):
        if idx == 0:
            buf.write("\n")
        else:
            buf.write("\n\n")
        buf.write(f"# Section: {section.schema.title}\n")
        df = _section_to_dataframe(section)
        df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def report_to_pdf(document: ReportDocument) -> bytes:
    if canvas is None:
        raise RuntimeError("reportlab is required for PDF output")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    def _write_header() -> None:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, height - 50, document.template.name)
        c.setFont("Helvetica", 10)
        c.drawString(40, height - 70, f"Owner: {document.owner}")
        if document.parameters:
            y = height - 85
            for key, value in sorted(document.parameters.items()):
                c.drawString(40, y, f"{key}: {value}")
                y -= 12

    def _write_section(section: ReportSectionData, start_y: float) -> float:
        y = start_y
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, section.schema.title)
        y -= 18
        if section.schema.description:
            c.setFont("Helvetica", 9)
            c.drawString(40, y, section.schema.description)
            y -= 14
        if y < 80:
            c.showPage()
            _write_header()
            y = height - 120
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, y, section.schema.title)
            y -= 18
        columns = [column.label for column in section.schema.columns]
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, y, " | ".join(columns))
        y -= 14
        c.setFont("Helvetica", 9)
        for row in section.rows:
            values: List[str] = []
            for column in section.schema.columns:
                value = row.get(column.key)
                if isinstance(value, float):
                    values.append(f"{value:.4f}")
                elif value is None:
                    values.append("")
                else:
                    values.append(str(value))
            line = " | ".join(values)
            if y < 60:
                c.showPage()
                _write_header()
                y = height - 120
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, section.schema.title)
                y -= 18
                c.setFont("Helvetica", 9)
            c.drawString(40, y, line)
            y -= 12
        return y - 10

    _write_header()
    y_cursor = height - 110
    for section in document.sections:
        if y_cursor < 120:
            c.showPage()
            _write_header()
            y_cursor = height - 110
        y_cursor = _write_section(section, y_cursor)
    c.showPage()
    c.save()
    return buf.getvalue()

