import asyncio
import io
import struct
import uuid
from dataclasses import dataclass

import structlog
from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.exceptions import UnsupportedFileTypeError
from app.models.document import Document
from app.repos.document_repository import DocumentCreate, DocumentRepository
from app.schemas.document import DocumentListResponse, DocumentResponse

logger = structlog.get_logger(__name__)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/plain; charset=utf-8",  # Some clients send charset suffix
    }
)

PDF_MAGIC_BYTES = b"%PDF"


@dataclass(frozen=True)
class _ValidatedFile:
    filename: str
    content_type: str  # Resolved from magic bytes, not the HTTP header
    contents: bytes
    file_size: int


class DocumentService:
    def __init__(self, repository: DocumentRepository) -> None:
        self._repo = repository

    async def upload_document(self, file: UploadFile) -> Document:
        log = logger.bind(filename=file.filename, content_type=file.content_type)
        log.info("document_upload_started")

        validated = await self._validate_file(file)
        raw_text = await self._extract_text(validated)

        if not raw_text.strip():
            raise UnsupportedFileTypeError(
                "Document contains no extractable text. Scanned image PDFs are not supported yet."
            )

        document = await self._repo.create(
            DocumentCreate(
                filename=validated.filename,
                content_type=validated.content_type,
                raw_text=raw_text,
                file_size=validated.file_size,
            )
        )

        log.info(
            "document_upload_completed",
            document_id=str(document.id),
            file_size=validated.file_size,
            text_length=len(raw_text),
        )

        return document

    async def get_document(self, document_id: uuid.UUID) -> Document:
        import uuid

        from app.core.exceptions import DocumentNotFoundError

        try:
            uid = uuid.UUID(document_id)
        except ValueError:
            raise DocumentNotFoundError(f"Invalid document ID format: {document_id}")

        document = await self._repo.get_by_id(uid)
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        return document

    async def list_documents(self, skip: int = 0, limit: int = 20) -> DocumentListResponse:
        limit = min(limit, 100)  # Hard cap — clients can't request more than 100
        documents, total = await self._repo.list_documents(skip=skip, limit=limit)
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

        if extension not in ("pdf", "txt"):
            raise UnsupportedFileTypeError(
                f"Unsupported file extension '.{extension}'. Allowed types: .pdf, .txt"
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

        if extension == "pdf" and contents[:4] != PDF_MAGIC_BYTES:
            raise UnsupportedFileTypeError(
                "File has .pdf extension but is not a valid PDF. "
                "The file may be corrupted or mislabeled."
            )

        # For .txt files: verify the content is valid UTF-8 text
        try:
            contents.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            raise UnsupportedFileTypeError(
                "Text file contains non-UTF-8 characters. Please ensure the file is UTF-8 encoded."
            )

    async def _extract_text(self, validated: _ValidatedFile) -> str:
        if validated.content_type == "application/pdf":
            return await asyncio.to_thread(self._extract_pdf_text_sync, validated.contents)
        return self._extract_plain_text(validated.contents)

    @staticmethod
    def _extract_pdf_text_sync(contents: bytes) -> str:

        try:
            reader = PdfReader(io.BytesIO(contents))
            pages: list[str] = []
            for page in enumerate(reader.pages):
                text = page.extract_text() or ""
                cleaned = text.strip()
                if cleaned:
                    pages.append(cleaned)

            if not pages:
                return ""

            full_text = "\n\n".join(pages)
            return full_text

        except PdfReadError as e:
            raise UnsupportedFileTypeError(
                f"Could not parse PDF: {e}. "
                "The file may be encrypted, password-protected, or corrupted."
            )

    @staticmethod
    def _extract_plain_text(contents: bytes) -> str:
        return contents.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
