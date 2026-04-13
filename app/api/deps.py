from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repos.chunk_repository import ChunkRepository
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


def get_chunk_repository() -> ChunkRepository:
    return ChunkRepository()


ChunkRepoDep = Annotated[ChunkRepository, Depends(get_chunk_repository)]


# -----------------------------------------------------------------------
# Service deps
# -----------------------------------------------------------------------
def get_chunking_service() -> ChunkingService:
    return ChunkingService()


ChunkingServiceDep = Annotated[ChunkingService, Depends(get_chunking_service)]


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(settings=get_settings())


EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]


def get_document_service(
    document_repo: DocumentRepoDep,
    chunk_repo: ChunkRepoDep,
    chunking_service: ChunkingServiceDep,
    embedding_service: EmbeddingServiceDep,
) -> DocumentService:
    return DocumentService(
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        chunking_service=chunking_service,
        embedding_service=embedding_service,
    )


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
