from __future__ import annotations

import logging
from functools import lru_cache

import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai.types import EmbedContentConfig
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import Settings
from app.core.exceptions import EmbeddingServiceError
from app.models.chunk import EMBEDDING_DIMENSIONS
from app.services.chunking_service import ChunkData

logger = structlog.get_logger(__name__)

TASK_RETRIVAL_DOCUMENT: str = "RETRIEVAL_DOCUMENT"
TASK_RETRIEVAL_QUERY: str = "RETRIEVAL_QUERY"


def _is_retryable_error(exc: BaseException) -> bool:
    if not isinstance(exc, genai_errors.APIError):
        return False

    code = getattr(exc, "code", None)

    if code is not None:
        return code in {429, 500, 502, 503, 504}

    error_text = str(exc).upper()
    return any(
        marker in error_text
        for marker in ("429", "RESOURCE_EXHAUSTED", "500", "503", "SERVICE_UNAVAILABLE")
    )


def _before_sleep(retry_state: object) -> None:
    exc = getattr(getattr(retry_state, "outcome", None), "exception", lambda: None)()
    logger.warning(
        "embedding_api_retry",
        attempt=getattr(retry_state, "attempt_number", None),
        error=str(exc) if exc else None,
    )


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_embedding_model
        self._dimensions = EMBEDDING_DIMENSIONS
        self._batch_size = settings.embedding_batch_size
        self._max_retries = 4

    async def embed_chunks(self, chunks: list[ChunkData]) -> list[list[float]]:
        if not chunks:
            return []

        texts = [chunk.content for chunk in chunks]

        logger.info(
            "embedding_chunks_started",
            chunk_count=len(chunks),
            batch_count=(len(chunks) + self._batch_size - 1) // self._batch_size,
            model=self._model,
        )

        vectors = await self._embed_texts(texts, TASK_RETRIVAL_DOCUMENT)

        logger.info(
            "embedding_chunks_completed",
            chunk_count=len(chunks),
            vector_dimensions=self._dimensions,
        )

        return vectors

    async def embed_query(self, query: str) -> list[float]:
        if not query.strip():
            raise EmbeddingServiceError("Query cannot be empty.")

        vectors = await self._embed_texts([query.strip()], TASK_RETRIEVAL_QUERY)
        return vectors[0]

    async def _embed_texts(self, texts: list[str], task_type: str) -> list[list[float]]:
        all_vectors: list[list[float]] = []

        for batch_idx, start in enumerate(range(0, len(texts), self._batch_size)):
            batch = texts[start : start + self._batch_size]

            try:
                batch_vectors = await self._embed_batch_with_retry(batch, task_type, batch_idx)

            except genai_errors.APIError as e:
                raise EmbeddingServiceError(
                    f"Embedding failed on batch {batch_idx} "
                    f"({len(batch)} texts, task={task_type}): {e}"
                ) from e

            all_vectors.extend(batch_vectors)

            for vector in all_vectors:
                if len(vector) != self._dimensions:
                    raise EmbeddingServiceError(
                        f"Dimension mismatch: expected {self._dimensions}, "
                        f"got {len(vector)}. "
                        f"Check output_dimensionality and EMBEDDING_DIMENSIONS constant."
                    )

        return all_vectors

    async def _embed_batch_with_retry(
        self,
        texts: list[str],
        task_type: str,
        batch_idx: int,
    ) -> list[list[float]]:
        last_response = None

        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_retryable_error),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential_jitter(initial=1, max=60),
            before_sleep=_before_sleep,
            reraise=True,
        ):
            with attempt:
                last_response = (
                    await self._client.aio.models.embed_content(
                        model=self._model,
                        contents=texts,
                        config=EmbedContentConfig(
                            task_type=task_type,
                            output_dimensionality=self._dimensions,
                        ),
                    ),
                )

            assert last_response is not None, "Unreachable: tenacity raises on failure"

            for i, emb in enumerate(last_response.embeddings):
                if emb.statistics and emb.statistics.truncated:
                    logger.warning(
                        "embedding_input_truncated",
                        batch_idx=batch_idx,
                        text_idx=i,
                        task_type=task_type,
                        hint="Chunk may exceed 2048 token limit. Consider reducing chunk_size.",
                    )

            return [emb.values for emb in last_response.embeddings]
