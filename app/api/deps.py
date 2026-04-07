from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repos.document_repository import DocumentRepository
from app.services.document_service import DocumentService

SettingsDep = Annotated[Settings, Depends(get_settings)]

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_document_repo(db: DbSession) -> DocumentRepository:
    return DocumentRepository(db)


DocumentRepoDep = Annotated[DocumentRepository, Depends(get_document_repo)]


def get_document_service(repo: DocumentRepository) -> DocumentService:
    return DocumentService(repo)


DocumentServiceDep = Annotated[DocumentService, Depends(DocumentRepoDep)]
