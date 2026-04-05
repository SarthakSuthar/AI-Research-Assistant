import structlog
from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SettingsDep
from app.db.session import AsyncSessionFactory
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])
logger = structlog.get_logger()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns service status. Used by load balancers and monitoring tools.",
)
async def health_check(settings: SettingsDep) -> HealthResponse:

    db_status = "ok"

    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        await logger.awarning("database health check failed", error=str(e))
        db_status = "unreachable"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        service=settings.app_name,
        environment=settings.app_env,
        database=db_status,
    )
