from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ChunkSearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    content: str
    chunk_index: int
    token_count: int
    similarity_score: float = Field(
        ge=-1.0,
        le=1.0,
        description="Cosine similarity score. 1.0 = identical, 0.0 = orthogonal.",
    )


class VectorSearchResponse(BaseModel):
    query: str
    results: list[ChunkSearchResult]
    total_found: int
