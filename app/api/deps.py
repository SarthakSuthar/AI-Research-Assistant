from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repos.document_repository import DocumentRepository
from app.services.chunking_service import ChunkingService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService

# -----------------------------------------------------------------------
# Primitive deps
# -----------------------------------------------------------------------
SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


# -----------------------------------------------------------------------
# Repository deps
# -----------------------------------------------------------------------
def get_document_repo(db: DbSession) -> DocumentRepository:
    return DocumentRepository(db)


DocumentRepoDep = Annotated[DocumentRepository, Depends(get_document_repo)]


# -----------------------------------------------------------------------
# Service deps
# -----------------------------------------------------------------------
def get_chunking_service() -> ChunkingService:
    return ChunkingService()


ChunkingServiceDep = Annotated[ChunkingService, Depends(get_chunking_service)]


def get_document_service(repo: DocumentRepository, service: ChunkingServiceDep) -> DocumentService:
    return DocumentService(repo)


DocumentServiceDep = Annotated[DocumentService, Depends(DocumentRepoDep)]


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(settings=get_settings())


EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]
