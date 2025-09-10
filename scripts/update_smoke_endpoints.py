#!/usr/bin/env python3
"""Regenerate frontend-backend-smoke.ts from backend route metadata."""
import json
import pathlib
from backend.app import create_app
from fastapi.routing import APIRoute


def main() -> None:
    app = create_app()
    endpoints = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods):
                endpoints.append({"method": method, "path": route.path})
    endpoints.sort(key=lambda ep: (ep["path"], ep["method"]))
    smoke_ts = pathlib.Path(__file__).resolve().parent / "frontend-backend-smoke.ts"
    content = "// Auto-generated via backend route metadata\n"
    content += "export interface SmokeEndpoint { method: string; path: string; body?: any }\n"
    content += "export const smokeEndpoints: SmokeEndpoint[] = " + json.dumps(endpoints, indent=2) + " as const;\n"
    content += (
        "\nexport function fillPath(path: string): string {\n"
        "  return path.replace(/\\{[^}]+\\}/g, 'test');\n"
        "}\n\nexport async function runSmoke(base: string) {\n"
        "  for (const ep of smokeEndpoints) {\n"
        "    const url = base + fillPath(ep.path);\n"
        "    const res = await fetch(url, { method: ep.method, body: ep.body ? JSON.stringify(ep.body) : undefined, headers: ep.body ? { 'Content-Type': 'application/json' } : undefined });\n"
        "    if (res.status >= 500) {\n"
        "      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);\n"
        "    }\n"
        "  }\n"
        "}\n\nif (require.main === module) {\n"
        "  runSmoke(process.argv[2] || process.env.SMOKE_URL || 'http://localhost:8000').catch(err => { console.error(err); process.exit(1); });\n"
        "}\n"
    )
    smoke_ts.write_text(content)


if __name__ == "__main__":
    main()
