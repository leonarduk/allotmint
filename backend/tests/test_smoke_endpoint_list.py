import json
import re
from pathlib import Path

from backend.app import create_app
from fastapi.routing import APIRoute

SMOKE_FILE = Path(__file__).resolve().parents[2] / 'scripts' / 'frontend-backend-smoke.ts'


def load_smoke_endpoints():
    text = SMOKE_FILE.read_text()
    match = re.search(r"smokeEndpoints: SmokeEndpoint\[] = (\[.*?\]) as const;", text, re.DOTALL)
    assert match, 'smokeEndpoints array not found'
    data = json.loads(match.group(1))
    return {(item['method'], item['path']) for item in data}


def list_backend_routes():
    app = create_app()
    routes = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes.add((method, route.path))
    return routes


def test_smoke_endpoint_list_up_to_date():
    smoke = load_smoke_endpoints()
    backend = list_backend_routes()
    assert smoke == backend, 'Update scripts/frontend-backend-smoke.ts for new routes'
