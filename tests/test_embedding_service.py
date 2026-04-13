from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.exceptions import EmbeddingServiceError
from app.models.chunk import EMBEDDING_DIMENSIONS
from app.services.chunking_service import ChunkData
from app.services.embedding_service import (
    TASK_RETRIEVAL_DOCUMENT,
    TASK_RETRIEVAL_QUERY,
    EmbeddingService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_settings(**overrides) -> Settings:
    defaults = {
        "database_url": "postgresql+asyncpg://test:test@localhost/test",
        "gemini_api_key": "test-api-key",
        "gemini_embedding_model": "gemini-embedding-001",
        "embedding_batch_size": 3,  # small for testing batching
    }
    return Settings(**{**defaults, **overrides})


def make_chunks(n: int) -> list[ChunkData]:
    return [
        ChunkData(content=f"chunk content {i}", chunk_index=i, token_count=10) for i in range(n)
    ]


def make_fake_vector(value: float = 0.1) -> list[float]:
    """Returns a valid EMBEDDING_DIMENSIONS-length vector."""
    return [value] * EMBEDDING_DIMENSIONS


def make_mock_embedding(value: float = 0.1) -> MagicMock:
    """Returns a mock ContentEmbedding object with .values and .statistics."""
    emb = MagicMock()
    emb.values = make_fake_vector(value)
    emb.statistics = MagicMock(truncated=False)
    return emb


def make_mock_response(n: int, value: float = 0.1) -> MagicMock:
    """Returns a mock embed_content response with n embeddings."""
    response = MagicMock()
    response.embeddings = [make_mock_embedding(value) for _ in range(n)]
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings() -> Settings:
    return make_settings()


@pytest.fixture()
def service(settings: Settings) -> EmbeddingService:
    with patch("app.services.embedding_service.genai.Client"):
        svc = EmbeddingService(settings=settings)
    return svc


# ---------------------------------------------------------------------------
# 1. Returns one vector per input chunk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_chunks_returns_one_vector_per_chunk(
    service: EmbeddingService,
) -> None:
    chunks = make_chunks(5)  # 5 chunks, batch_size=3 → 2 batches
    # Batch 1: 3 chunks → 3 embeddings; Batch 2: 2 chunks → 2 embeddings
    service._client.aio.models.embed_content = AsyncMock(
        side_effect=[
            make_mock_response(3, 0.1),
            make_mock_response(2, 0.2),
        ]
    )
    vectors = await service.embed_chunks(chunks)
    assert len(vectors) == 5


# ---------------------------------------------------------------------------
# 2. Order preserved: vectors[i] corresponds to chunks[i]
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_chunks_preserves_order(service: EmbeddingService) -> None:
    chunks = make_chunks(2)
    emb_a = make_mock_embedding(0.11)
    emb_b = make_mock_embedding(0.22)
    response = MagicMock()
    response.embeddings = [emb_a, emb_b]

    service._client.aio.models.embed_content = AsyncMock(return_value=response)

    vectors = await service.embed_chunks(chunks)
    assert vectors[0] == emb_a.values
    assert vectors[1] == emb_b.values


# ---------------------------------------------------------------------------
# 3. Empty input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_chunks_empty_input_returns_empty_list(
    service: EmbeddingService,
) -> None:
    vectors = await service.embed_chunks([])
    assert vectors == []
    service._client.aio.models.embed_content.assert_not_called()


# ---------------------------------------------------------------------------
# 4. embed_query uses RETRIEVAL_QUERY task type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_query_uses_retrieval_query_task_type(
    service: EmbeddingService,
) -> None:
    service._client.aio.models.embed_content = AsyncMock(return_value=make_mock_response(1))
    await service.embed_query("what is the capital of France?")

    call_kwargs = service._client.aio.models.embed_content.call_args.kwargs
    assert call_kwargs["config"].task_type == TASK_RETRIEVAL_QUERY


# ---------------------------------------------------------------------------
# 5. embed_query returns a flat single vector (not list of vectors)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_query_returns_single_flat_vector(
    service: EmbeddingService,
) -> None:
    service._client.aio.models.embed_content = AsyncMock(return_value=make_mock_response(1, 0.5))
    vector = await service.embed_query("test query")

    assert isinstance(vector, list)
    assert isinstance(vector[0], float)
    assert len(vector) == EMBEDDING_DIMENSIONS


# ---------------------------------------------------------------------------
# 6. Batching: large input calls API ceil(n / batch_size) times
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batching_makes_correct_number_of_api_calls(
    service: EmbeddingService,
) -> None:
    # batch_size=3 (from fixture), 7 chunks → ceil(7/3) = 3 API calls
    chunks = make_chunks(7)
    service._client.aio.models.embed_content = AsyncMock(
        side_effect=[
            make_mock_response(3),
            make_mock_response(3),
            make_mock_response(1),
        ]
    )
    await service.embed_chunks(chunks)
    assert service._client.aio.models.embed_content.call_count == 3


# ---------------------------------------------------------------------------
# 7. Dimension mismatch raises EmbeddingServiceError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dimension_mismatch_raises_embedding_service_error(
    service: EmbeddingService,
) -> None:
    wrong_dim_emb = MagicMock()
    wrong_dim_emb.values = [0.1] * 512  # wrong! expected 1536
    wrong_dim_emb.statistics = MagicMock(truncated=False)

    bad_response = MagicMock()
    bad_response.embeddings = [wrong_dim_emb]

    service._client.aio.models.embed_content = AsyncMock(return_value=bad_response)

    with pytest.raises(EmbeddingServiceError, match="Dimension mismatch"):
        await service.embed_chunks(make_chunks(1))


# ---------------------------------------------------------------------------
# 8. Non-retryable API error raises EmbeddingServiceError immediately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_retryable_error_raises_immediately(
    service: EmbeddingService,
) -> None:
    from google.genai import errors as genai_errors

    # 401 Unauthorized — not retryable; should fail on first attempt
    auth_error = genai_errors.APIError("Invalid API key")
    auth_error.code = 401

    service._client.aio.models.embed_content = AsyncMock(side_effect=auth_error)

    with pytest.raises(EmbeddingServiceError):
        await service.embed_chunks(make_chunks(1))

    # Should only have been called once — no retries on 401
    assert service._client.aio.models.embed_content.call_count == 1


# ---------------------------------------------------------------------------
# 9. Retryable error (429) is retried before raising
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_error_is_retried(service: EmbeddingService) -> None:
    from google.genai import errors as genai_errors

    rate_limit_error = genai_errors.APIError("RESOURCE_EXHAUSTED")
    rate_limit_error.code = 429

    # Always fail — ensures all retries are exhausted
    service._client.aio.models.embed_content = AsyncMock(side_effect=rate_limit_error)
    # Override max_retries to 2 so the test doesn't take 60+ seconds
    service._max_retries = 2

    with pytest.raises(EmbeddingServiceError):
        await service.embed_chunks(make_chunks(1))

    # Called max_retries times (not just once)
    assert service._client.aio.models.embed_content.call_count == 2


# ---------------------------------------------------------------------------
# 10. Empty query raises EmbeddingServiceError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_query_raises_embedding_service_error(
    service: EmbeddingService,
) -> None:
    with pytest.raises(EmbeddingServiceError, match="empty"):
        await service.embed_query("   ")
