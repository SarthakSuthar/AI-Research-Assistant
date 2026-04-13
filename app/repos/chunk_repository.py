from __future__ import annotations

import uuid

import structlog
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.services.chunking_service import ChunkData

logger = structlog.get_logger(__name__)


class ChunkRepository:
    async def bulk_create(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        chunks: list[ChunkData],
        vectors: list[list[float]],
    ) -> int:
        if not chunks:
            logger.warning("bulk_create_called_with_empty_chunks", document_id=str(document_id))
            return 0

        if len(chunks) != len(vectors):
            raise ValueError(
                f"Chunk/vector count mismatch: {len(chunks)} chunks "
                f"vs {len(vectors)} vectors for document {document_id}. "
                "This is a programming error — embed_chunks() must return "
                "one vector per chunk."
            )

        rows = [
            {
                "document_id": document_id,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        await db.execute(insert(Chunk), rows)
        await db.flush()

        logger.debug(
            "chunks_bulk_inserted",
            document_id=str(document_id),
            count=len(rows),
        )

        return len(rows)

    async def get_by_document_id(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> list[Chunk]:
        result = await db.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index.asc())
        )

        return list(result.scalars().all())

    async def get_chunk_count(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> int:
        from sqlalchemy import func

        result = await db.execute(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
        )
        return result.scalar_one()
