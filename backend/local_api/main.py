"""
Local / Docker / ECS entry-point.
Run with:  uvicorn backend.local_api.main:app --reload
"""

from backend.app import create_app

app = create_app()
