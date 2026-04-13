from __future__ import annotations

import asyncio
import io
import uuid
from dataclasses import dataclass
from typing import Final

import structlog
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentCreate, DocumentRepository
from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DocumentNotFoundError,
    EmbeddingServiceError,
    UnsupportedFileTypeError,
)
from app.models.document import DocumentStatus
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.services.chunking_service import ChunkData, ChunkingService
from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger(__name__)

MAX_FILE_SIZE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB

ALLOWED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/plain; charset=utf-8",
    }
)

PDF_MAGIC_BYTES: Final[bytes] = b"%PDF"
ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({"pdf", "txt"})


@dataclass(frozen=True)
class _ValidatedFile:
    filename: str
    content_type: str  # Resolved from magic bytes, not the HTTP header
    contents: bytes
    file_size: int


class DocumentService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        embedding_service: EmbeddingService,
        chunking_service: ChunkingService,
    ) -> None:
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.embedding_service = embedding_service
        self.chunking_service = chunking_service

    async def upload_document(
        self,
        file: UploadFile,
        db: AsyncSession,
    ) -> DocumentUploadResponse:

        log = logger.bind(filename=file.filename, content_type=file.content_type)
        log.info("document_upload_started")

        validated = await self._validate_file(file)
        raw_text = await self._extract_text(validated)

        if not raw_text.strip():
            raise UnsupportedFileTypeError(
                "Document contains no extractable text. Scanned image PDFs are not supported yet."
            )

        document = await self.document_repo.create(
            db,
            DocumentCreate(
                filename=validated.filename,
                content_type=validated.content_type,
                raw_text=raw_text,
                file_size=validated.file_size,
            ),
        )

        chunks: list[ChunkData] = self.chunking_service.split_text(raw_text)
        chunk_count = len(chunks)

        await self.document_repo.update_status(
            db,
            document.id,
            DocumentStatus.PROCESSING,
            chunk_count=chunk_count,
        )

        document.status = DocumentStatus.PROCESSING
        document.chunk_count = chunk_count

        try:
            vectors = await self.embedding_service.embed_chunks(chunks)
        except EmbeddingServiceError as exc:
            await self.document_repo.update_status(db, document.id, DocumentStatus.FAILED)
            document.status = DocumentStatus.FAILED
            log.error(
                "document_embedding_failed",
                document_id=str(document.id),
                error=str(exc),
            )
            raise

        await self.chunk_repo.bulk_create(db, document.id, chunks, vectors)
        await self.document_repo.update_status(db, document.id, DocumentStatus.COMPLETED)
        document.status = DocumentStatus.COMPLETED

        log.info(
            "document_upload_completed",
            document_id=str(document.id),
            file_size=validated.file_size,
            text_length=len(raw_text),
            chunk_count=chunk_count,
            avg_token_count=(sum(c.token_count for c in chunks) // max(chunk_count, 1)),
        )

        return DocumentUploadResponse(
            document=DocumentResponse.model_validate(document),
            message=(
                f"Document uploaded and split into {chunk_count} chunks. Embedding in progress."
            ),
        )

    async def get_document(self, document_id: uuid.UUID, db: AsyncSession) -> DocumentResponse:

        document = await self.document_repo.get_by_id(db, document_id)
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} not found.")
        return DocumentResponse.model_validate(document)

    async def list_documents(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
    ) -> DocumentListResponse:

        limit = min(limit, 100)

        documents, total = await self.document_repo.list_documents(db, skip=skip, limit=limit)
        return DocumentListResponse(
            items=[DocumentResponse.model_validate(doc) for doc in documents],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def _validate_file(self, file: UploadFile) -> _ValidatedFile:

        if not file.filename:
            raise UnsupportedFileTypeError("Filename is required.")

        filename = file.filename.strip()
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if extension not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"Unsupported file extension '.{extension}'. "
                f"Allowed: {', '.join(f'.{e}' for e in ALLOWED_EXTENSIONS)}"
            )

        contents = await file.read(MAX_FILE_SIZE_BYTES + 1)
        file_size = len(contents)

        if file_size == 0:
            raise UnsupportedFileTypeError("Uploaded file is empty.")

        if file_size > MAX_FILE_SIZE_BYTES:
            raise UnsupportedFileTypeError(
                f"File too large. Maximum allowed size is "
                f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            )

        resolved_content_type = self._resolve_content_type(contents, extension)

        return _ValidatedFile(
            filename=filename,
            content_type=resolved_content_type,
            contents=contents,
            file_size=file_size,
        )

    @staticmethod
    def _resolve_content_type(contents: bytes, extension: str) -> str:

        if contents[:4] == PDF_MAGIC_BYTES:
            return "application/pdf"

        if extension == "pdf":
            raise UnsupportedFileTypeError(
                "File has .pdf extension but is not a valid PDF. "
                "The file may be corrupted or mislabeled."
            )

        try:
            contents.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError as exc:
            raise UnsupportedFileTypeError(
                "Text file contains non-UTF-8 characters. Please ensure the file is UTF-8 encoded."
            ) from exc

    async def _extract_text(self, validated: _ValidatedFile) -> str:

        if validated.content_type == "application/pdf":
            return await asyncio.to_thread(self._extract_pdf_text_sync, validated.contents)
        return self._extract_plain_text(validated.contents)

    @staticmethod
    def _extract_pdf_text_sync(contents: bytes) -> str:

        try:
            reader = PdfReader(io.BytesIO(contents))
            pages: list[str] = []

            for page in reader.pages:  # ← Fixed: was enumerate(reader.pages)
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append(text)

            return "\n\n".join(pages)

        except PdfReadError as exc:
            raise UnsupportedFileTypeError(
                f"Could not parse PDF: {exc}. "
                "The file may be encrypted, password-protected, or corrupted."
            ) from exc

    @staticmethod
    def _extract_plain_text(contents: bytes) -> str:

        return contents.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
