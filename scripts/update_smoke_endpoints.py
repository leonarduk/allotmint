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
from backend.config import smoke_identity as get_smoke_identity
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


SMOKE_IDENTITY = get_smoke_identity()
SMOKE_QUERY_SLUG = f"{SMOKE_IDENTITY}-slug"
SMOKE_GROUP_SLUG = "all"


MANUAL_BODIES: dict[tuple[str, str], Any] = {
    ("POST", "/accounts/{owner}/approval-requests"): {"ticker": "PFE"},
    ("POST", "/accounts/{owner}/approvals"): {
        "ticker": "PFE",
        "approved_on": "1970-01-01",
    },
    ("DELETE", "/accounts/{owner}/approvals"): {"ticker": "PFE"},
    ("POST", "/analytics/events"): {"source": "trail", "event": "view"},
    ("POST", "/compliance/validate"): {"owner": SMOKE_IDENTITY},
    ("POST", "/instrument/admin/groups"): {"name": SMOKE_IDENTITY},
    ("POST", "/instrument/admin/{exchange}/{ticker}/group"): {
        "group": SMOKE_IDENTITY,
    },
    ("POST", "/transactions"): {
        "owner": SMOKE_IDENTITY,
        "account": "isa",
        "ticker": "PFE",
        "date": "1970-01-01",
        "price_gbp": 1,
        "units": 1,
        "reason": "smoke test",
    },
    ("PUT", "/transactions/{tx_id}"): {
        "owner": SMOKE_IDENTITY,
        "account": "isa",
        "ticker": "PFE",
        "date": "1970-01-01",
        "price_gbp": 1,
        "units": 1,
        "reason": "smoke test",
    },
    ("POST", "/virtual-portfolios"): {
        "id": "smoke-vp-created",
        "name": "test",
    },
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
            "owner": SMOKE_IDENTITY,
            "account": "isa",
            "provider": "test",
            "file": "__file__",
        }
    },
}

MANUAL_QUERIES: dict[tuple[str, str], dict[str, str]] = {}

SAMPLE_QUERY_VALUES: dict[str, str] = {
    "owner": SMOKE_IDENTITY,
    "account": "isa",
    "user": "user@example.com",
    "email": "user@example.com",
    "exchange": "NASDAQ",
    "ticker": "PFE",
    "tickers": "PFE",
    "id": "1",
    "vp_id": "1",
    "quest_id": "check-in",
    "slug": SMOKE_QUERY_SLUG,
    "name": SMOKE_IDENTITY,
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

    header = f"""import fs from 'node:fs';
import path from 'node:path';
import {{ createRequire }} from 'node:module';

type YamlModule = {{ parse?: (input: string) => unknown }};

let yamlModule: YamlModule | null = null;

try {{
  const require = createRequire(import.meta.url);
  const candidate = require('yaml') as YamlModule;
  if (candidate && typeof candidate.parse === 'function') {{
    yamlModule = candidate;
  }} else {{
    console.warn('Installed yaml module does not expose a parse function; config.yaml parsing will be skipped.');
  }}
}} catch (error) {{
  const message = error instanceof Error ? error.message : String(error);
  console.warn(`YAML parser not available; config.yaml parsing will be skipped: ${{message}}`);
}}

const DEFAULT_DEATH_AGE = '90';

function statePensionAgeUk(dob: string): number {{
  const birth = new Date(`${{dob}}T00:00:00Z`);
  if (Number.isNaN(birth.getTime())) {{
    throw new Error('Invalid dob');
  }}

  if (birth < new Date('1954-10-06T00:00:00Z')) return 65;
  if (birth < new Date('1960-04-06T00:00:00Z')) return 66;
  if (birth < new Date('1977-04-06T00:00:00Z')) return 67;
  return 68;
}}

function resolveSmokeIdentity(): string {{
  const envValue = process.env.SMOKE_IDENTITY?.trim();
  if (envValue) {{
    return envValue;
  }}

  const configPath = path.resolve(__dirname, '../config.yaml');

  try {{
    const raw = fs.readFileSync(configPath, 'utf8');
    const parsed = (() => {{
      if (!yamlModule || typeof yamlModule.parse !== 'function') {{
        return {{}} as Record<string, unknown>;
      }}
      try {{
        const result = yamlModule.parse(raw);
        return (result && typeof result === 'object' ? result : {{}}) as Record<string, unknown>;
      }} catch (parseError) {{
        const message = parseError instanceof Error ? parseError.message : String(parseError);
        console.warn(`Unable to parse config.yaml; falling back to defaults: ${{message}}`);
        return {{}} as Record<string, unknown>;
      }}
    }})();
    const authSection =
      parsed && typeof parsed.auth === 'object' && parsed.auth !== null
        ? (parsed.auth as Record<string, unknown>)
        : {{}};
    const smokeFromConfig =
      typeof authSection.smoke_identity === 'string' ? authSection.smoke_identity.trim() : '';
    const demoFromConfig =
      typeof authSection.demo_identity === 'string' ? authSection.demo_identity.trim() : '';
    if (smokeFromConfig) {{
      return smokeFromConfig;
    }}
    if (demoFromConfig) {{
      return demoFromConfig;
    }}
  }} catch (error) {{
    const message = error instanceof Error ? error.message : String(error);
    console.warn(`Falling back to configured smoke identity due to error reading config.yaml: ${{message}}`);
  }}

  return '{SMOKE_IDENTITY}';
}}

export const smokeIdentity = resolveSmokeIdentity();

function computeSmokeDeathAge(identity: string): string {{
  const accountsRoot = process.env.ACCOUNTS_ROOT ?? path.resolve(__dirname, '../data/accounts');
  const candidates = Array.from(new Set([identity, `${{identity}}-owner`]));
  for (const slug of candidates) {{
    const personPath = path.join(accountsRoot, slug, 'person.json');

    try {{
      const meta = JSON.parse(fs.readFileSync(personPath, 'utf8')) as {{ dob?: unknown }};
      const dob = typeof meta.dob === 'string' ? meta.dob : null;
      if (!dob) {{
        continue;
      }}
      const retirementAge = statePensionAgeUk(dob);
      return String(retirementAge + 20);
    }} catch (error) {{
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`Unable to derive smoke pension death age from ${{personPath}}: ${{message}}`);
    }}
  }}

  return DEFAULT_DEATH_AGE;
}}

const demoPensionDeathAge = computeSmokeDeathAge(smokeIdentity);

"""

    content = header
    content += "// Auto-generated via backend route metadata\n"
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
        "type SmokeFixtures = {\n"
        "  owner: string;\n"
        "  user: string;\n"
        "  groupSlug: string;\n"
        "  querySlug: string;\n"
        "  questId: string;\n"
        "  taskId: string;\n"
        "  transactionId: string;\n"
        "  virtualPortfolioId: string;\n"
        "  virtualPortfolioDeleteId: string;\n"
        "};\n"
        "\nconst sampleQuerySlug = `${smokeIdentity}-slug`;\n"
        f"const sampleGroupSlug = '{SMOKE_GROUP_SLUG}';\n"
        "const sampleVirtualPortfolioCreateId = 'smoke-vp-created';\n"
        "\nconst SAMPLE_PATH_VALUES: Record<string, string> = {\n"
        "  owner: smokeIdentity,\n"
        "  account: 'isa',\n"
        "  user: smokeIdentity,\n"
        "  email: 'user@example.com',\n"
        "  source: 'trail',\n"
        "  id: '1',\n"
        "  tx_id: '1',\n"
        "  vp_id: '1',\n"
        "  quest_id: 'check-in',\n"
        "  slug: sampleQuerySlug,\n"
        "  name: 'test',\n"
        "  exchange: 'NASDAQ',\n"
        "  ticker: 'PFE',\n"
        "};\n"
        "\nfunction chooseFixtureOwner(payload: unknown): string | null {\n"
        "  if (!Array.isArray(payload)) {\n"
        "    return null;\n"
        "  }\n"
        "\n  for (const entry of payload) {\n"
        "    if (!entry || typeof entry !== 'object') {\n"
        "      continue;\n"
        "    }\n"
        "    const owner = typeof (entry as { owner?: unknown }).owner === 'string' ? (entry as { owner: string }).owner.trim() : '';\n"
        "    if (owner && owner.toLowerCase() !== 'demo') {\n"
        "      return owner;\n"
        "    }\n"
        "  }\n"
        "\n  for (const entry of payload) {\n"
        "    if (!entry || typeof entry !== 'object') {\n"
        "      continue;\n"
        "    }\n"
        "    const owner = typeof (entry as { owner?: unknown }).owner === 'string' ? (entry as { owner: string }).owner.trim() : '';\n"
        "    if (owner) {\n"
        "      return owner;\n"
        "    }\n"
        "  }\n"
        "\n  return null;\n"
        "}\n"
        "\nfunction chooseFixtureGroup(payload: unknown): string | null {\n"
        "  if (!Array.isArray(payload)) {\n"
        "    return null;\n"
        "  }\n"
        "\n  for (const entry of payload) {\n"
        "    if (!entry || typeof entry !== 'object') {\n"
        "      continue;\n"
        "    }\n"
        "    const slug = typeof (entry as { slug?: unknown }).slug === 'string' ? (entry as { slug: string }).slug.trim() : '';\n"
        "    if (slug) {\n"
        "      return slug;\n"
        "    }\n"
        "  }\n"
        "\n  return null;\n"
        "}\n"
        "\nfunction chooseFixtureId(payload: unknown, key: 'quests' | 'tasks'): string | null {\n"
        "  if (!payload || typeof payload !== 'object') {\n"
        "    return null;\n"
        "  }\n"
        "\n  const entries = (payload as Record<string, unknown>)[key];\n"
        "  if (!Array.isArray(entries)) {\n"
        "    return null;\n"
        "  }\n"
        "\n  for (const entry of entries) {\n"
        "    if (!entry || typeof entry !== 'object') {\n"
        "      continue;\n"
        "    }\n"
        "    const id = typeof (entry as { id?: unknown }).id === 'string' ? (entry as { id: string }).id.trim() : '';\n"
        "    if (id) {\n"
        "      return id;\n"
        "    }\n"
        "  }\n"
        "\n  return null;\n"
        "}\n"
        "\nasync function resolveFixtures(base: string): Promise<SmokeFixtures> {\n"
        "  const fixtures: SmokeFixtures = {\n"
        "    owner: smokeIdentity,\n"
        "    user: smokeIdentity,\n"
        "    groupSlug: sampleGroupSlug,\n"
        "    querySlug: sampleQuerySlug,\n"
        "    questId: 'check_in',\n"
        "    taskId: 'log_in',\n"
        "    transactionId: '1',\n"
        "    virtualPortfolioId: '1',\n"
        "    virtualPortfolioDeleteId: '1',\n"
        "  };\n"
        "\n  try {\n"
        "    const ownersRes = await fetch(`${base}/owners`, { method: 'GET' });\n"
        "    if (ownersRes.ok) {\n"
        "      fixtures.owner = chooseFixtureOwner(await ownersRes.json()) ?? fixtures.owner;\n"
        "      fixtures.user = fixtures.owner;\n"
        "    }\n"
        "  } catch {\n"
        "    // Fall back to the configured identity when owner discovery is unavailable.\n"
        "  }\n"
        "\n  try {\n"
        "    const groupsRes = await fetch(`${base}/groups`, { method: 'GET' });\n"
        "    if (groupsRes.ok) {\n"
        "      fixtures.groupSlug = chooseFixtureGroup(await groupsRes.json()) ?? fixtures.groupSlug;\n"
        "    }\n"
        "  } catch {\n"
        "    // Fall back to the default group slug when group discovery is unavailable.\n"
        "  }\n"
        "\n  try {\n"
        "    const questsRes = await fetch(`${base}/quests/today`, { method: 'GET' });\n"
        "    if (questsRes.ok) {\n"
        "      fixtures.questId = chooseFixtureId(await questsRes.json(), 'quests') ?? fixtures.questId;\n"
        "    }\n"
        "  } catch {\n"
        "    // Fall back to the default quest id when quest discovery is unavailable.\n"
        "  }\n"
        "\n  try {\n"
        "    const trailRes = await fetch(`${base}/trail`, { method: 'GET' });\n"
        "    if (trailRes.ok) {\n"
        "      fixtures.taskId = chooseFixtureId(await trailRes.json(), 'tasks') ?? fixtures.taskId;\n"
        "    }\n"
        "  } catch {\n"
        "    // Fall back to the default task id when trail discovery is unavailable.\n"
        "  }\n"
        "\n  try {\n"
        "    const txRes = await fetch(`${base}/transactions`, { method: 'GET' });\n"
        "    if (txRes.ok) {\n"
        "      const payload = await txRes.json();\n"
        "      if (Array.isArray(payload)) {\n"
        "        for (const entry of payload) {\n"
        "          if (!entry || typeof entry !== 'object') {\n"
        "            continue;\n"
        "          }\n"
        "          const id = typeof (entry as { id?: unknown }).id === 'string' ? (entry as { id: string }).id.trim() : '';\n"
        "          if (id) {\n"
        "            fixtures.transactionId = id;\n"
        "            break;\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  } catch {\n"
        "    // Fall back to the default transaction id when discovery is unavailable.\n"
        "  }\n"
        "\n  try {\n"
        "    const vpRes = await fetch(`${base}/virtual-portfolios`, { method: 'GET' });\n"
        "    if (vpRes.ok) {\n"
        "      const payload = await vpRes.json();\n"
        "      if (Array.isArray(payload)) {\n"
        "        let fallbackId: string | null = null;\n"
        "        for (const entry of payload) {\n"
        "          if (!entry || typeof entry !== 'object') {\n"
        "            continue;\n"
        "          }\n"
        "          const id = String((entry as { id?: unknown }).id ?? '').trim();\n"
        "          if (id) {\n"
        "            fallbackId ??= id;\n"
        "            if (id !== sampleVirtualPortfolioCreateId) {\n"
        "              fixtures.virtualPortfolioDeleteId = id;\n"
        "              break;\n"
        "            }\n"
        "          }\n"
        "        }\n"
        "        if (fixtures.virtualPortfolioDeleteId === '1' && fallbackId) {\n"
        "          fixtures.virtualPortfolioDeleteId = fallbackId;\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  } catch {\n"
        "    // Fall back to the default virtual portfolio id when discovery is unavailable.\n"
        "  }\n"
        "\n  return fixtures;\n"
        "}\n"
        "\nasync function ensureVirtualPortfolio(base: string, id: string): Promise<void> {\n"
        "  if (!id || id === '1') {\n"
        "    return;\n"
        "  }\n"
        "\n  try {\n"
        "    await fetch(`${base}/virtual-portfolios`, {\n"
        "      method: 'POST',\n"
        "      headers: { 'Content-Type': 'application/json' },\n"
        "      body: JSON.stringify({ id, name: id }),\n"
        "    });\n"
        "  } catch {\n"
        "    // Best-effort seeding only; route validation will still happen during the sweep.\n"
        "  }\n"
        "}\n"
        "\nfunction materializeValue(value: unknown, key: string, path: string, fixtures: SmokeFixtures): unknown {\n"
        "  if (typeof value === 'string') {\n"
        "    const lowerKey = key.toLowerCase();\n"
        "    if (lowerKey === 'owner' || lowerKey === 'user') {\n"
        "      return fixtures.owner;\n"
        "    }\n"
        "    if (lowerKey === 'slug') {\n"
        "      if (path.startsWith('/performance-group/') || path.startsWith('/portfolio-group/')) {\n"
        "        return fixtures.groupSlug;\n"
        "      }\n"
        "      return fixtures.querySlug;\n"
        "    }\n"
        "    if (value === smokeIdentity) {\n"
        "      return fixtures.owner;\n"
        "    }\n"
        "    if (value === sampleQuerySlug) {\n"
        "      return fixtures.querySlug;\n"
        "    }\n"
        "    return value;\n"
        "  }\n"
        "\n  if (Array.isArray(value)) {\n"
        "    return value.map((entry) => materializeValue(entry, key, path, fixtures));\n"
        "  }\n"
        "\n  if (value && typeof value === 'object') {\n"
        "    return Object.fromEntries(\n"
        "      Object.entries(value).map(([nestedKey, nestedValue]) => [\n"
        "        nestedKey,\n"
        "        materializeValue(nestedValue, nestedKey, path, fixtures),\n"
        "      ]),\n"
        "    );\n"
        "  }\n"
        "\n  return value;\n"
        "}\n"
        "\nfunction materializeQuery(\n"
        "  query: Record<string, string> | undefined,\n"
        "  path: string,\n"
        "  fixtures: SmokeFixtures,\n"
        "): Record<string, string> | undefined {\n"
        "  if (!query) {\n"
        "    return undefined;\n"
        "  }\n"
        "  return Object.fromEntries(\n"
        "    Object.entries(query).map(([key, value]) => [key, String(materializeValue(value, key, path, fixtures))]),\n"
        "  );\n"
        "}\n"
        "\nfunction materializeBody(body: any, path: string, fixtures: SmokeFixtures): any {\n"
        "  if (body === undefined) {\n"
        "    return undefined;\n"
        "  }\n"
        "  return materializeValue(body, '', path, fixtures);\n"
        "}\n"
        "\nexport function fillPath(path: string, fixtures: SmokeFixtures, method?: string): string {\n"
        "  return path.replace(/\\{([^}]+)\\}/g, (_, key: string) => {\n"
        "    const k = key.toLowerCase();\n"
        "    if (k === 'slug') {\n"
        "      if (path.startsWith('/performance-group/') || path.startsWith('/portfolio-group/')) return fixtures.groupSlug;\n"
        "      return fixtures.querySlug;\n"
        "    }\n"
        "    if (k === 'owner') return fixtures.owner;\n"
        "    if (k === 'user') return fixtures.user;\n"
        "    if (k === 'quest_id') return fixtures.questId;\n"
        "    if (k === 'task_id') return fixtures.taskId;\n"
        "    if (k === 'tx_id') return fixtures.transactionId;\n"
        "    if (k === 'vp_id') {\n"
        "      return method === 'DELETE' ? fixtures.virtualPortfolioDeleteId : fixtures.virtualPortfolioId;\n"
        "    }\n"
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
        "\n  const fixtures = await resolveFixtures(normalizedBase);\n"
        "  if (fixtures.virtualPortfolioDeleteId === fixtures.virtualPortfolioId) {\n"
        "    fixtures.virtualPortfolioDeleteId = 'smoke-vp-delete';\n"
        "  }\n"
        "  await ensureVirtualPortfolio(normalizedBase, fixtures.virtualPortfolioDeleteId);\n"
        "\n  for (const ep of smokeEndpoints) {\n"
        "    let url = normalizedBase + fillPath(ep.path, fixtures, ep.method);\n"
        "    const query = materializeQuery(ep.query, ep.path, fixtures);\n"
        "    if (query) url += '?' + new URLSearchParams(query).toString();\n"
        "    let body: any = undefined;\n"
        "    let headers: any = undefined;\n"
        "    const requestBody = materializeBody(ep.body, ep.path, fixtures);\n"
        "    if (requestBody !== undefined) {\n"
        "      if ((requestBody as any).__form__) {\n"
        "        const fd = new FormData();\n"
        "        for (const [k, v] of Object.entries((requestBody as any).__form__)) {\n"
        "          fd.set(k, v === '__file__' ? new Blob(['test']) : (v as any));\n"
        "        }\n"
        "        body = fd;\n"
        "      } else if (requestBody instanceof FormData) {\n"
        "        body = requestBody;\n"
        "      } else {\n"
        "        body = JSON.stringify(requestBody);\n"
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
        "    // Allow 409 for endpoints where we try to create data that may already exist.\n"
        "    if (\n"
        "      res.status >= 400 &&\n"
        "      res.status !== 401 &&\n"
        "      res.status !== 403 &&\n"
        "      res.status !== 409\n"
        "    ) {\n"
        "      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);\n"
        "    }\n"
        "    const tag =\n"
        "      res.ok\n"
        "        ? \"✓\"\n"
        "        : res.status === 401 || res.status === 403\n"
          "? \"○\"\n"
        "          : res.status === 409\n"
        "            ? \"△\"\n"
        "            : \"•\";\n"
        "    console.log(`${tag} ${ep.method} ${ep.path} (${res.status})`);\n"
        "\n    if (ep.method === 'POST' && ep.path === '/virtual-portfolios' && res.ok) {\n"
        "      try {\n"
        "        const created = await res.clone().json() as { id?: unknown };\n"
        "        const id = String(created.id ?? '').trim();\n"
        "        if (id) {\n"
        "          fixtures.virtualPortfolioId = id;\n"
        "        }\n"
        "      } catch {\n"
        "        // Ignore response parsing failures; the pre-resolved id remains available.\n"
        "      }\n"
        "    }\n"
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
    content = content.replace(f'"{SMOKE_IDENTITY}"', "smokeIdentity")
    content = content.replace(f'"{SMOKE_QUERY_SLUG}"', "sampleQuerySlug")
    smoke_ts.write_text(content)


if __name__ == "__main__":
    main()
