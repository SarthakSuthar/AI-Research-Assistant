import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, UploadFile, status

from app.api.deps import DbSession, DocumentServiceDep
from app.core.exceptions import DocumentNotFoundError, UnsupportedFileTypeError
from app.schemas.document import DocumentListResponse, DocumentResponse, DocumentUploadResponse

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = structlog.get_logger(__name__)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for processing",
    description=(
        "Upload a PDF or plain text file. The document will be stored and "
        "queued for text chunking and embedding generation. "
        "Poll GET /documents/{id} to track processing status."
    ),
)
async def upload_document(
    service: DocumentServiceDep, file: UploadFile, db: DbSession
) -> DocumentUploadResponse:
    try:
        return await service.upload_document(file=file, db=db)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document by ID",
    description="Returns document metadata and current processing status.",
)
async def get_document(
    service: DocumentServiceDep,
    document_id: uuid.UUID,
    db: DbSession,
) -> DocumentResponse:
    try:
        return await service.get_document(document_id=document_id, db=db)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Returns a list of documents with pagination.",
)
async def list_documents(
    db: DbSession,
    service: DocumentServiceDep,
    skip: int = Query(default=0, ge=0, description="Number of documents to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return (max 100)"),
) -> DocumentListResponse:
    return await service.list_documents(db=db, skip=skip, limit=limit)
