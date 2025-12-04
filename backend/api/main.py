"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Startup
    settings = get_settings()
    settings.ensure_directories()
    await init_db()
    yield
    # Shutdown
    pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Korean-English Document Translation Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict:
        return {"status": "healthy", "service": settings.app_name}

    # Import and include routers
    from backend.api.routes import auth, glossaries, jobs
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(jobs.router, prefix=settings.api_v1_prefix)
    app.include_router(glossaries.router, prefix=settings.api_v1_prefix)

    from backend.api.routes import chat
    app.include_router(chat.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()

