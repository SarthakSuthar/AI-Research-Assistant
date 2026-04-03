from fastapi import APIRouter

from app.api.v1 import documents, health, queries

router = APIRouter()
router.include_router(health.router)
router.include_router(documents.router)
router.include_router(queries.router)
