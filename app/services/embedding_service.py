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
    pass
