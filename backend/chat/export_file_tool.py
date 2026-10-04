"""``export_file``: a chat tool that saves a table as a CSV, Excel or Word file (#9039).

The model passes the table (column names and rows) it wants to hand over, for
example a stale-data audit, and the tool renders it in memory. Nothing is
written to disk: :class:`backend.chat.local_tools.LocalTools` collects the
files and ``POST /chat`` returns them with the reply, base64-encoded, for the
chat panel to offer as downloads. The admin config can switch the tool off like
any other (``mcp.mcp_tools``).

Excel and Word files are the modern ``.xlsx`` and ``.docx`` formats. The
``.docx`` is assembled from its XML parts here so no extra dependency is needed.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from mcp.types import Tool
from openpyxl import Workbook

TOOL_NAME = "export_file"

MAX_ROWS = 5000
MAX_COLUMNS = 50
# The files travel base64-encoded in the JSON reply, which must stay well under
# API Gateway/Lambda's 6 MB response limit; MAX_TURN_BYTES is what holds that.
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TURN_BYTES = 2 * 1024 * 1024
MAX_FILES_PER_TURN = 5

FORMATS = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

TOOL = Tool(
    name=TOOL_NAME,
    description=(
        "Save a table as a file the user can download: CSV (csv), Excel (xlsx) or Word (docx). "
        "Use this when the user asks to export, download or save a report or a result set, "
        "e.g. a data-quality audit. Pass the column names and the rows (one array of values "
        "per row, in column order) taken from your tool results; do not invent values. The "
        f"user gets a download link under your reply. At most {MAX_ROWS} rows and "
        f"{MAX_COLUMNS} columns."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "File name without extension, e.g. stale-data-audit.",
            },
            "format": {"type": "string", "enum": list(FORMATS), "description": "File format."},
            "title": {
                "type": "string",
                "description": "Optional heading, used as the Excel sheet name and the Word document title.",
            },
            "columns": {"type": "array", "items": {"type": "string"}, "description": "Column names."},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}},
                "description": "The rows, one array of cell values per row.",
            },
        },
        "required": ["filename", "format", "columns", "rows"],
    },
)


@dataclass(frozen=True)
class ExportedFile:
    filename: str
    media_type: str
    content: bytes


class ExportError(ValueError):
    """Bad tool arguments; the message is sent back to the model."""


Cell = Any
_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9 _.-]+")
# Characters XML 1.0 does not allow (all C0 controls except tab, LF and CR).
_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
# A spreadsheet treats text starting with one of these as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def call(arguments: Mapping[str, Any]) -> Tuple[str, bool, Optional[ExportedFile]]:
    """Render the file; return ``(text for the model, is_error, file or None)``."""

    try:
        exported = build_file(arguments)
    except ExportError as exc:
        return f"export_file: {exc}", True, None
    row_count = len(arguments["rows"])
    text = (
        f"Saved {exported.filename} ({row_count} rows). The user has a download link under your "
        "reply; tell them the file is ready rather than repeating its contents."
    )
    return text, False, exported


def build_file(arguments: Mapping[str, Any]) -> ExportedFile:
    fmt = arguments.get("format")
    if fmt not in FORMATS:
        raise ExportError(f"format must be one of {', '.join(FORMATS)}")
    columns, rows = _table(arguments)
    title = _clean_title(arguments.get("title"))
    renderers = {"csv": _render_csv, "xlsx": _render_xlsx, "docx": _render_docx}
    content = renderers[fmt](columns, rows, title)
    if len(content) > MAX_FILE_BYTES:
        raise ExportError(f"the file would be {len(content)} bytes; the limit is {MAX_FILE_BYTES}")
    return ExportedFile(f"{safe_filename(arguments.get('filename'))}.{fmt}", FORMATS[fmt], content)


def safe_filename(name: Any) -> str:
    """A plain file name stem: no path, no extension, nothing a browser would reject."""

    stem = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = re.sub(r"\.(csv|xlsx?|docx?)$", "", stem.strip(), flags=re.IGNORECASE)
    stem = _FILENAME_UNSAFE.sub("_", stem).strip(" ._")[:80]
    return stem or "export"


def _table(arguments: Mapping[str, Any]) -> Tuple[List[str], List[List[Cell]]]:
    columns = arguments.get("columns")
    rows = arguments.get("rows")
    if not isinstance(columns, list) or not columns:
        raise ExportError("columns must be a non-empty list of names")
    if len(columns) > MAX_COLUMNS:
        raise ExportError(f"at most {MAX_COLUMNS} columns")
    if not isinstance(rows, list):
        raise ExportError("rows must be a list of arrays")
    if len(rows) > MAX_ROWS:
        raise ExportError(f"at most {MAX_ROWS} rows")
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(columns):
            raise ExportError(f"row {index + 1} must be an array of {len(columns)} values, one per column")
        if any(isinstance(cell, (list, dict)) for cell in row):
            raise ExportError(f"row {index + 1} has a nested value; cells must be text, numbers or booleans")
    return [str(column) for column in columns], rows


def _clean_title(title: Any) -> Optional[str]:
    text = _XML_INVALID.sub("", str(title or "")).strip()
    return text[:200] or None


def _text(cell: Cell) -> str:
    return "" if cell is None else str(cell)


def _neutralise_formula(value: str) -> str:
    """Stop a spreadsheet running text such as ``=HYPERLINK(...)`` as a formula."""

    if not value.startswith(_FORMULA_PREFIXES) or _is_number(value):
        return value
    return "'" + value


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _render_csv(columns: Sequence[str], rows: Sequence[Sequence[Cell]], _title: Optional[str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([_neutralise_formula(column) for column in columns])
    for row in rows:
        writer.writerow([_neutralise_formula(cell) if isinstance(cell, str) else _text(cell) for cell in row])
    # BOM so Excel opens the UTF-8 file with the right encoding (e.g. £).
    return buffer.getvalue().encode("utf-8-sig")


def _render_xlsx(columns: Sequence[str], rows: Sequence[Sequence[Cell]], title: Optional[str]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    # Sheet names are at most 31 characters and cannot contain []:*?/\.
    sheet.title = re.sub(r"[\[\]:*?/\\]", " ", title or "Export")[:31].strip() or "Export"
    for row in [list(columns), *rows]:
        sheet.append([_XML_INVALID.sub("", cell) if isinstance(cell, str) else cell for cell in row])
    for row_cells in sheet.iter_rows():
        for cell in row_cells:
            # openpyxl stores text starting with "=" as a formula; keep it as text.
            if cell.data_type == "f":
                cell.data_type = "s"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


_DOCX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_DOCX_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)
_DOCX_BORDERS = "".join(
    f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
    for side in ("top", "left", "bottom", "right", "insideH", "insideV")
)


def _docx_run(text: str, bold: bool = False, size: Optional[int] = None) -> str:
    props = ("<w:b/>" if bold else "") + (f'<w:sz w:val="{size}"/>' if size else "")
    run_props = f"<w:rPr>{props}</w:rPr>" if props else ""
    clean = escape(_XML_INVALID.sub("", text))
    return f'<w:r>{run_props}<w:t xml:space="preserve">{clean}</w:t></w:r>'


def _docx_row(cells: Sequence[Cell], header: bool) -> str:
    cell_xml = "".join(f"<w:tc><w:p>{_docx_run(_text(cell), bold=header)}</w:p></w:tc>" for cell in cells)
    row_props = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
    return f"<w:tr>{row_props}{cell_xml}</w:tr>"


def _render_docx(columns: Sequence[str], rows: Sequence[Sequence[Cell]], title: Optional[str]) -> bytes:
    heading = f"<w:p>{_docx_run(title, bold=True, size=32)}</w:p>" if title else ""
    table = (
        f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>{_DOCX_BORDERS}</w:tblBorders></w:tblPr>'
        + _docx_row(columns, header=True)
        + "".join(_docx_row(row, header=False) for row in rows)
        + "</w:tbl>"
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{heading}{table}<w:p/></w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        package.writestr("_rels/.rels", _DOCX_RELS)
        package.writestr("word/document.xml", document)
    return buffer.getvalue()
