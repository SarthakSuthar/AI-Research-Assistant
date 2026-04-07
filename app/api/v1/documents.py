import uuid

import structlog
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.api.deps import DocumentServiceDep
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
    service: DocumentServiceDep,
    file: UploadFile = File(
        ..., description="PDF (.pdf) or plain text (.txt) file. Maximum size: 10 MB."
    ),
) -> DocumentUploadResponse:
    try:
        document = await service.upload_document(file)
        return DocumentUploadResponse(document=DocumentResponse.model_validate(document))
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document by ID",
    description="Returns document metadata and current processing status.",
)
async def get_document(service: DocumentServiceDep, document_id: uuid.UUID) -> DocumentResponse:
    try:
        document = await service.get_document(document_id)
        return DocumentResponse.model_validate(document)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Returns a list of documents with pagination.",
)
async def list_documents(
    service: DocumentServiceDep,
    skip: int = Query(default=0, ge=0, description="Number of documents to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return (max 100)"),
) -> DocumentListResponse:
    return await service.list_documents(skip=skip, limit=limit)
