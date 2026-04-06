import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.chunk import Chunk
from app.models.mixins import TimeStampMixin, UUIDPrimaryKeyMixin


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(UUIDPrimaryKeyMixin, TimeStampMixin, Base):
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
        nullable=False,
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        # - "all" → propagates save/merge/expunge/delete from Document to Chunks
        # - "delete-orphan" → deleting a Document automatically deletes its Chunks
        # This means: DELETE FROM documents WHERE id=X also DELETEs all chunks.
        # The DB-level FK ondelete="CASCADE" in Chunk is a safety net for raw SQL.
        cascade=("all, delete-orphan",),
        # lazy="noload" is MANDATORY in async SQLAlchemy.
        # The default lazy="select" triggers a synchronous SELECT when you access
        # document.chunks — this deadlocks in async context (no greenlet).
        # "noload" means: never auto-load. You must explicitly use
        # selectinload() or joinedload() in your repository queries.
        # This prevents accidental N+1 queries and async deadlocks.
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"
