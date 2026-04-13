from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository

from app.core.exceptions import EmbeddingServiceError, UnsupportedFileTypeError
from app.models.chunk import EMBEDDING_DIMENSIONS
from app.models.document import Document, DocumentStatus
from app.services.chunking_service import ChunkingService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_fake_vector() -> list[float]:
    return [0.01] * EMBEDDING_DIMENSIONS


def make_fake_document(status: DocumentStatus = DocumentStatus.PENDING) -> Document:
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.filename = "test.txt"
    doc.content_type = "text/plain"
    doc.file_size = 100
    doc.raw_text = "Sample text for testing the document upload pipeline."
    doc.status = status
    doc.chunk_count = 0
    doc.created_at = MagicMock()
    doc.updated_at = MagicMock()
    return doc


def make_upload_file(
    content: bytes = b"Sample text for testing.",
    filename: str = "test.txt",
    content_type: str = "text/plain",
) -> MagicMock:
    """Creates a mock UploadFile that behaves like FastAPI's UploadFile."""
    upload_file = MagicMock()
    upload_file.filename = filename
    upload_file.content_type = content_type
    upload_file.read = AsyncMock(return_value=content)
    return upload_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture()
def mock_document_repo(make_fake_document) -> DocumentRepository:
    repo = MagicMock(spec=DocumentRepository)
    repo.create = AsyncMock(return_value=make_fake_document())
    repo.get_by_id = AsyncMock(return_value=make_fake_document())
    repo.update_status = AsyncMock(return_value=None)
    repo.list_documents = AsyncMock(return_value=([], 0))
    return repo


@pytest.fixture()
def fake_doc() -> Document:
    return make_fake_document()


@pytest.fixture()
def mock_document_repo(fake_doc) -> MagicMock:
    repo = MagicMock(spec=DocumentRepository)
    repo.create = AsyncMock(return_value=fake_doc)
    repo.update_status = AsyncMock(return_value=None)
    repo.list_documents = AsyncMock(return_value=([], 0))
    return repo


@pytest.fixture()
def mock_chunk_repo() -> MagicMock:
    repo = MagicMock(spec=ChunkRepository)
    repo.bulk_create = AsyncMock(return_value=5)
    return repo


@pytest.fixture()
def mock_embedding_service() -> MagicMock:
    svc = MagicMock(spec=EmbeddingService)
    # embed_chunks returns one vector per chunk — we'll calibrate
    # the side_effect per-test for accuracy, but default to 5 vectors
    svc.embed_chunks = AsyncMock(side_effect=lambda chunks: [make_fake_vector() for _ in chunks])
    return svc


@pytest.fixture()
def service(mock_document_repo, mock_chunk_repo, mock_embedding_service) -> DocumentService:
    return DocumentService(
        document_repo=mock_document_repo,
        chunk_repo=mock_chunk_repo,
        chunking_service=ChunkingService(),  # REAL chunker
        embedding_service=mock_embedding_service,
    )


# ---------------------------------------------------------------------------
# 1. Successful upload — COMPLETED, chunk_count > 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_upload_returns_completed_status(
    service: DocumentService, mock_db, fake_doc
) -> None:
    file = make_upload_file(
        content=b"This is a test document with enough content to be chunked properly.",
        filename="test.txt",
    )

    response = await service.upload_document(file=file, db=mock_db)

    assert response.document.status == DocumentStatus.COMPLETED
    assert response.document.chunk_count > 0


@pytest.mark.asyncio
async def test_successful_upload_calls_embed_and_store(
    service: DocumentService,
    mock_db,
    mock_embedding_service,
    mock_chunk_repo,
) -> None:
    file = make_upload_file(
        content=b"Document content that will be chunked and embedded.",
        filename="doc.txt",
    )

    await service.upload_document(file=file, db=mock_db)

    mock_embedding_service.embed_chunks.assert_called_once()
    mock_chunk_repo.bulk_create.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Empty PDF text guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_text_raises_unsupported_file_type_error(
    service: DocumentService, mock_db
) -> None:
    # Whitespace-only text — no extractable content
    file = make_upload_file(content=b"   \n\n   ", filename="empty.txt")

    with pytest.raises(UnsupportedFileTypeError, match="no extractable text"):
        await service.upload_document(file=file, db=mock_db)


# ---------------------------------------------------------------------------
# 3. Embedding failure → EmbeddingServiceError, status = FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embedding_failure_sets_status_to_failed(
    service: DocumentService,
    mock_db,
    mock_embedding_service,
    mock_document_repo,
    fake_doc,
) -> None:
    mock_embedding_service.embed_chunks = AsyncMock(
        side_effect=EmbeddingServiceError("Gemini rate limit exceeded")
    )

    file = make_upload_file(
        content=b"Document content that will fail at embedding stage.",
        filename="fail.txt",
    )

    with pytest.raises(EmbeddingServiceError):
        await service.upload_document(file=file, db=mock_db)

    # Verify update_status was called with FAILED
    calls = mock_document_repo.update_status.call_args_list
    statuses_used = [call.args[2] for call in calls if len(call.args) >= 3]
    assert DocumentStatus.FAILED in statuses_used


@pytest.mark.asyncio
async def test_embedding_failure_does_not_call_bulk_create(
    service: DocumentService,
    mock_db,
    mock_embedding_service,
    mock_chunk_repo,
) -> None:
    mock_embedding_service.embed_chunks = AsyncMock(
        side_effect=EmbeddingServiceError("Gemini API error")
    )
    file = make_upload_file(content=b"Some content.", filename="test.txt")

    with pytest.raises(EmbeddingServiceError):
        await service.upload_document(file=file, db=mock_db)

    # Chunks must NOT be stored if embedding failed
    mock_chunk_repo.bulk_create.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Unsupported file extension
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_extension_raises_error(service: DocumentService, mock_db) -> None:
    file = make_upload_file(
        content=b"some content",
        filename="document.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    with pytest.raises(UnsupportedFileTypeError, match="docx"):
        await service.upload_document(file=file, db=mock_db)


# ---------------------------------------------------------------------------
# 5. File too large
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_too_large_raises_error(service: DocumentService, mock_db) -> None:
    # 11 MB — exceeds 10 MB limit
    oversized = b"x" * (11 * 1024 * 1024)
    file = make_upload_file(content=oversized, filename="big.txt")

    with pytest.raises(UnsupportedFileTypeError, match="too large"):
        await service.upload_document(file=file, db=mock_db)


# ---------------------------------------------------------------------------
# 6. Empty file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_file_raises_error(service: DocumentService, mock_db) -> None:
    file = make_upload_file(content=b"", filename="empty.txt")

    with pytest.raises(UnsupportedFileTypeError, match="empty"):
        await service.upload_document(file=file, db=mock_db)


# ---------------------------------------------------------------------------
# 7. update_status called in correct sequence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_transitions_are_correct(
    service: DocumentService,
    mock_db,
    mock_document_repo,
) -> None:
    file = make_upload_file(
        content=b"A document that completes successfully.",
        filename="success.txt",
    )

    await service.upload_document(file=file, db=mock_db)

    calls = mock_document_repo.update_status.call_args_list
    # Extract positional arg[2] (status) from each call
    statuses = [c.args[2] for c in calls if len(c.args) >= 3]

    # Must see PROCESSING before COMPLETED — never FAILED on success
    assert DocumentStatus.PROCESSING in statuses
    assert DocumentStatus.COMPLETED in statuses
    assert DocumentStatus.FAILED not in statuses
    assert statuses.index(DocumentStatus.PROCESSING) < statuses.index(DocumentStatus.COMPLETED)
