import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


@dataclass
class DocumentCreate:
    filename: str
    content_type: str
    raw_text: str
    file_size: int


class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, obj_in: DocumentCreate) -> Document:
        db_document = Document(
            filename=obj_in.filename,
            content_type=obj_in.content_type,
            raw_text=obj_in.raw_text,
            file_size=obj_in.file_size,
        )
        self._db.add(db_document)
        await self._db.flush()
        await self._db.refresh(db_document)
        return db_document

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        """
        SELECT a single document by primary key. Returns None if not found.

        WHY scalar_one_or_none() instead of .first()?
        - .first() silently ignores duplicate rows — masks data integrity bugs.
        - scalar_one_or_none() raises MultipleResultsFound if > 1 row matches.
        - For a PK lookup there should NEVER be > 1 result; if there is, we
          want to know immediately (not silently return the wrong row).
        """

        result = await self._db.execute(select(Document).where(Document.id == document_id))

        return result.scalar_one_or_none()

    async def list_documents(self, skip: int = 0, limit: int = 20) -> tuple[list[Document], int]:
        count_result = await self._db.execute(select(func.count()).select_from(Document))

        total = count_result.scalar_one()

        result = await self._db.execute(
            select(Document).order_by(Document.created_at.desc()).offset(skip).limit(limit)
        )

        documents = list(result.scalar().all())

        return documents, total
    
    async def update_status(
        
    ):
