from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.document import Document
from app.models.mixins import TimeStampMixin, UUIDPrimaryKeyMixin

EMBEDDING_DIMENSIONS = 1536


class Chunk(UUIDPrimaryKeyMixin, TimeStampMixin, Base):
    __tablename__ = "chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = ((mapped_column(Text, nullable=False),),)
    chunk_index: Mapped[int] = (mapped_column(Integer, nullable=False),)
    token_count: Mapped[int | None] = (
        (mapped_column(Integer, nullable=False, server_default="0"),),
    )
    embedding: Mapped[Vector | None] = (mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True),)

    documnet: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
        lazy="noload",  # Never auto-load; always explicit joins or subqueries
    )

    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_document_chunk_order", "document_id", "chunk_index"),
    )

    def __repr__(self) -> str:
        has_embadding = self.embedding is not None
        return (
            f"<Chunk id= {self.id} doc={self.document_id} "
            f"index={self.chunk_index} embedded={has_embadding}>"
        )
