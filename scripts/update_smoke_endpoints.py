#!/usr/bin/env python3
"""Regenerate ``frontend-backend-smoke.ts`` from backend route metadata."""

import datetime as _dt
import enum
import json
import pathlib
import sys
from typing import Any, get_args, get_origin

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from backend.app import create_app
from fastapi.routing import APIRoute
from pydantic import BaseModel


def _example_for_type(typ: Any) -> Any:
    """Return a representative example value for ``typ``."""

    origin = get_origin(typ)
    if origin is list:
        (arg,) = get_args(typ) or (Any,)
        return [_example_for_type(arg)]
    if origin is dict:
        return {}
    if origin is tuple:
        args = get_args(typ)
        if args:
            return [_example_for_type(args[0])]
        return []
    if origin is set:
        (arg,) = get_args(typ) or (Any,)
        return [_example_for_type(arg)]
    if origin is not None:
        # Union, Annotated, etc. - choose first argument
        for arg in get_args(typ):
            if arg is not type(None):
                return _example_for_type(arg)
        return _example_for_type(Any)

    if isinstance(typ, type):
        if issubclass(typ, BaseModel):
            data = {}
            for name, field in typ.model_fields.items():
                if field.is_required():
                    data[name] = _example_for_type(field.annotation)
            return data
        if issubclass(typ, enum.Enum):
            return next(iter(typ)).value
        if issubclass(typ, str):
            return "test"
        if issubclass(typ, (int, float)):
            return 0
        if issubclass(typ, bool):
            return True
        if issubclass(typ, _dt.datetime):
            return "1970-01-01T00:00:00"
        if issubclass(typ, _dt.date):
            return "1970-01-01"
    return {}


MANUAL_BODIES: dict[tuple[str, str], Any] = {
    ("POST", "/accounts/{owner}/approval-requests"): {"ticker": "PFE"},
    ("POST", "/accounts/{owner}/approvals"): {
        "ticker": "PFE",
        "approved_on": "1970-01-01",
    },
    ("DELETE", "/accounts/{owner}/approvals"): {"ticker": "PFE"},
    ("POST", "/compliance/validate"): {"owner": "demo"},
    ("POST", "/user-config/{owner}"): {},
    (
        "POST",
        "/transactions/import",
    ): {"__form__": {"provider": "test", "file": "__file__"}},
    (
        "POST",
        "/holdings/import",
    ): {
        "__form__": {
            "owner": "demo",
            "account": "isa",
            "provider": "test",
            "file": "__file__",
        }
    },
}

MANUAL_QUERIES: dict[tuple[str, str], dict[str, str]] = {}

SAMPLE_QUERY_VALUES: dict[str, str] = {
    "owner": "demo",
    "account": "isa",
    "user": "user@example.com",
    "email": "user@example.com",
    "exchange": "NASDAQ",
    "ticker": "PFE",
    "tickers": "PFE",
    "id": "1",
    "vp_id": "1",
    "quest_id": "check-in",
    "slug": "demo-slug",
    "name": "demo",
}


def _example_for_query_param(name: str, ann: Any) -> str:
    """Return a representative example value for a query parameter.

    A curated value map similar to ``fillPath`` is used so that generated
    smoke requests reference existing data rather than placeholders like
    ``ticker=test`` which can trigger 404 errors.
    """

    k = name.lower()
    if k in SAMPLE_QUERY_VALUES:
        return SAMPLE_QUERY_VALUES[k]
    if "email" in k:
        return "user@example.com"
    if "id" in k:
        return "1"
    if "user" in k:
        return "user@example.com"
    if "date" in k:
        return "1970-01-01"
    if "ticker" in k:
        return "PFE"
    return str(_example_for_type(ann))


def main() -> None:
    app = create_app()
    endpoints = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods):
                ep: dict[str, Any] = {"method": method, "path": route.path}
                override = MANUAL_BODIES.get((method, route.path))
                if override is not None:
                    ep["body"] = override
                else:
                    body_field = getattr(route, "body_field", None)
                    if body_field and body_field.required:
                        ep["body"] = _example_for_type(body_field.type_)
                query_override = MANUAL_QUERIES.get((method, route.path))
                if query_override is not None:
                    ep["query"] = query_override
                else:
                    params: dict[str, str] = {}
                    for param in route.dependant.query_params:
                        if param.required:
                            ann = getattr(param, "annotation", None) or getattr(
                                param, "outer_type_", None
                            ) or param.type_
                            params[param.name] = _example_for_query_param(
                                param.name, ann
                            )
                    if params:
                        ep["query"] = params
                endpoints.append(ep)
    endpoints.sort(key=lambda ep: (ep["path"], ep["method"]))

    smoke_ts = pathlib.Path(__file__).resolve().parent / "frontend-backend-smoke.ts"
    content = "// Auto-generated via backend route metadata\n"
    content += (
        "export interface SmokeEndpoint { method: string; path: string; query?: Record<string, string>; body?: any }\n"
    )
    content += (
        "export const smokeEndpoints: SmokeEndpoint[] = "
        + json.dumps(endpoints, indent=2)
        + " as const;\n"
    )
    content += (
        "\n// Provide sample values for path parameters so requests avoid 422/400 errors.\n"
        "// Values are chosen based on common parameter names. Unknown names default to\n"
        "// `1` which parses as an integer or string.\n"
        "const SAMPLE_PATH_VALUES: Record<string, string> = {\n"
        "  owner: 'demo',\n"
        "  account: 'isa',\n"
        "  user: 'demo',\n"
        "  email: 'user@example.com',\n"
        "  id: '1',\n"
        "  vp_id: '1',\n"
        "  quest_id: 'check-in',\n"
        "  slug: 'demo-slug',\n"
        "  name: 'demo',\n"
        "  exchange: 'NASDAQ',\n"
        "  ticker: 'PFE',\n"
        "};\n"
        "\nexport function fillPath(path: string): string {\n"
        "  return path.replace(/\\{([^}]+)\\}/g, (_, key: string) => {\n"
        "    const k = key.toLowerCase();\n"
        "    if (SAMPLE_PATH_VALUES[k]) return SAMPLE_PATH_VALUES[k];\n"
        "    if (k.includes('email')) return 'user@example.com';\n"
        "    if (k.includes('id')) return '1';\n"
        "    if (k.includes('user')) return 'user@example.com';\n"
        "    if (k.includes('date')) return '1970-01-01';\n"
        "    return '1';\n"
        "  });\n"
        "}\n"
        "\nexport async function runSmoke(base: string) {\n"
        "  const normalizedBase = base.replace(/\\/+$/, '');\n"
        "  const healthUrl = `${normalizedBase}/health`;\n"
        "\n  try {\n"
        "    await fetch(healthUrl, { method: 'GET' });\n"
        "  } catch (error) {\n"
        "    const reason = error instanceof Error ? error.message : String(error);\n"
        "    throw new Error(\n"
        "      `Preflight check failed: could not reach ${healthUrl} (${reason}). Start the backend (make run-backend) or provide SMOKE_URL pointing to a running instance.`,\n"
        "    );\n"
        "  }\n"
        "\n  for (const ep of smokeEndpoints) {\n"
        "    let url = normalizedBase + fillPath(ep.path);\n"
        "    if (ep.query) url += '?' + new URLSearchParams(ep.query).toString();\n"
        "    let body: any = undefined;\n"
        "    let headers: any = undefined;\n"
        "    if (ep.body !== undefined) {\n"
        "      if ((ep.body as any).__form__) {\n"
        "        const fd = new FormData();\n"
        "        for (const [k, v] of Object.entries((ep.body as any).__form__)) {\n"
        "          fd.set(k, v === '__file__' ? new Blob(['test']) : (v as any));\n"
        "        }\n"
        "        body = fd;\n"
        "      } else if (ep.body instanceof FormData) {\n"
        "        body = ep.body;\n"
        "      } else {\n"
        "        body = JSON.stringify(ep.body);\n"
        "        headers = { 'Content-Type': 'application/json' };\n"
        "      }\n"
        "    }\n"
        "    let res: Awaited<ReturnType<typeof fetch>>;\n"
        "    try {\n"
        "      res = await fetch(url, { method: ep.method, body, headers });\n"
        "    } catch (error) {\n"
        "      const reason = error instanceof Error ? error.message : String(error);\n"
        "      throw new Error(`Network error while calling ${ep.method} ${ep.path}: ${reason}`);\n"
        "    }\n"
        "    if (res.status >= 500) {\n"
        "      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);\n"
        "    }\n"
        "\n    // Allow 401/403 for endpoints that require roles; they still prove the route exists\n"
        "    if (res.status >= 400 && res.status !== 401 && res.status !== 403) {\n"
        "      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);\n"
        "    }\n"
        "    const tag = res.ok ? \"✓\" : (res.status === 401 || res.status === 403) ? \"○\" : \"•\";\n"
        "    console.log(`${tag} ${ep.method} ${ep.path} (${res.status})`);\n"
        "\n  }\n"
        "}\n"
        "\nif (require.main === module) {\n"
        "  const base = process.argv[2] || process.env.SMOKE_URL || 'http://localhost:8000';\n"
        "  runSmoke(base).catch(err => {\n"
        "    if (err instanceof Error) {\n"
        "      console.error(err.message);\n"
        "    } else {\n"
        "      console.error(err);\n"
        "    }\n"
        "    process.exit(1);\n"
        "  });\n"
        "}\n"
    )
    smoke_ts.write_text(content)


if __name__ == "__main__":
    main()
