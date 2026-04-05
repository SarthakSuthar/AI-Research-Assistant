from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await logger.ainfo("Database engine created", pool_size=engine.pool.size())
    yield
    await engine.dispose()
    await logger.ainfo("Database engine disposed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_production else None,
        redoc_url="/redoc" if settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],  # Allow GET, POST, PUT, DELETE, OPTIONS
        allow_headers=["*"],  # Allow Authorization, Content-Type, etc.
    )

    app.include_router(router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
