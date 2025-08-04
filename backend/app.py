"""
Single FastAPI application used by both local (uvicorn) and AWS Lambda.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.instrument import router as instrument_router
from backend.routes.portfolio import router as portfolio_router
from backend.common.portfolio_utils import refresh_snapshot_in_memory


def create_app() -> FastAPI:
    app = FastAPI(
        title="Allotmint API",
        version="1.0",
        docs_url="/docs",
    )

    # dev CORS – tighten in prod
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # shared routers
    app.include_router(portfolio_router)
    app.include_router(instrument_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.on_event("startup")
    async def _warm_snapshot():
        refresh_snapshot_in_memory()

    return app


# optional local test:  python -m backend.app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
"""
Single FastAPI application used by both local (uvicorn) and AWS Lambda.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.instrument import router as instrument_router
from backend.routes.portfolio import router as portfolio_router
from backend.common.portfolio_utils import refresh_snapshot_in_memory


def create_app() -> FastAPI:
    app = FastAPI(
        title="Allotmint API",
        version="1.0",
        docs_url="/docs",
    )

    # dev CORS – tighten in prod
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # shared routers
    app.include_router(portfolio_router)
    app.include_router(instrument_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.on_event("startup")
    async def _warm_snapshot():
        refresh_snapshot_in_memory()

    return app


# optional local test:  python -m backend.app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
