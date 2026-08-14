"""
Local / Docker / ECS entry-point.
Run with:  uvicorn backend.local_api.main:app --reload
"""

from backend.app import create_app

app = create_app()

# If you want to run in PyCharm and debug
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="debug")
