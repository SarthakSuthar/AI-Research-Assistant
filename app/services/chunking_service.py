from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

import structlog

logger = structlog.get_logger(__name__)

# ~250 tokens × 4 chars/token = 1000 chars.
DEFAULT_CHUNK_SIZE: Final[int] = 1_000

DEFAULT_CHUNK_OVERLAP: Final[int] = 200

MIN_CHUNK_CHARS: Final[int] = 50

CHARS_PER_TOKEN: Final[float] = 4.0

DEFAULT_SEPARATORS: Final[tuple[str, ...]] = (
    "\n\n",
    "\n",
    ". ",
    "! ",
    "? ",
    "; ",
    ", ",
    " ",
    "",
)


@dataclass
class ChunkData:
    content: str
    chunk_index: int
    token_count: int


class ChunkingService:
    """
    ALGORITHM (RecursiveCharacterTextSplitter):
        1. Try separators in priority order until one exists in the text.
        2. Split text on that separator → list of pieces.
        3. Pieces ≤ chunk_size: accumulate in `good_splits`.
        4. Pieces > chunk_size: recursively split with next separator.
        5. Merge `good_splits` into chunk_size buckets WITH overlap.
        6. Repeat until all text is consumed.
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        separators: tuple[str, ...] = DEFAULT_SEPARATORS,
        min_chunk_chars: int = MIN_CHUNK_CHARS,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be strictly less than "
                f"chunk_size ({chunk_size}). Got overlap={chunk_overlap}."
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators
        self.min_chunk_chars = min_chunk_chars

    def split_text(self, text: str) -> list[ChunkData]:
        if not text or not text.strip():
            logger.waening("split_text_called_with_empty_text")
            return []

        normalized = re.sub(r"\n{3,}", "\n\n", text.strip())

        raw_chunks = self._recrsive_split(text=normalized, separator=list(self.separators))

        chunks = [
            ChunkData(
                content=chunk_text, chunk_index=idx, token_count=self._estimate_token(chunk_text)
            )
            for idx, chunk_text in enumerate(raw_chunks)
        ]

        logger.info(
            "text_split_complete",
            total_chars=len(normalized),
            chunk_count=len(chunks),
            avg_chunk_chars=len(normalized) // max(len(chunks), 1),
            avg_token_count=(sum(c.token_count for c in chunks) // max(len(chunks), 1)),
        )

        return chunks

    def _recrsive_split(self, text: str, separator: list[str]) -> list[str]:
        final_chunk: list[str] = []

        chosen_sep = separator[-1]

        remaning_seps: list[str] = []

        for idx, sep in enumerate(separator):
            if sep == "":
                chosen_sep = sep
                break
            if sep in text:
                chosen_sep = sep
                remaning_seps = separator[idx + 1 :]
                break

        splits = [s for s in text.split(chosen_sep) if s.strip()]

        good_splits: list[str] = []

        for split in splits:
            if len(split) <= self.chunk_size:
                good_splits.append(split)
            else:
                if good_splits:
                    final_chunk.extend(self._merge_with_overlap(good_splits, chosen_sep))
                    good_splits = []
                if remaning_seps:
                    sub_chunks = self._recrsive_split(split, remaning_seps)
                    final_chunk.extend(sub_chunks)
                else:
                    final_chunk.extend(self._hard_split(split))

        if good_splits:
            final_chunk.extend(self._merge_with_overlap(good_splits, chosen_sep))

        return [c.strip() for c in final_chunk if len(c.strip()) >= self.min_chunk_chars]

    def _merge_with_overlap(self, splits: list[str], separator: str) -> list[str]:
        chunks: list[str] = []
        current_doc: list[str] = []
        current_len: int = 0
        sep_len = len(separator)

        for split in splits:
            split_len = len(split)
            join_cost = sep_len if current_doc else 0

            if current_len + join_cost + split_len > self.chunk_size and current_doc:
                chunk_text = separator.join(current_doc)

                if len(chunk_text.strip()) >= self.min_chunk_chars:
                    chunks.append(chunk_text)

                while current_doc and current_len > self.chunk_overlap:
                    removed = current_doc.pop(0)
                    current_len -= len(removed) + sep_len

                current_doc = [split]
                current_len += split_len + (sep_len if len(current_doc) > 1 else 0)

            if current_doc:
                chunk_text = separator.join(current_doc)
                if len(chunk_text.strip()) >= self.min_chunk_chars:
                    chunks.append(chunk_text)

            return chunks

    def _hard_split(self, text: str) -> list[str]:
        chunks: list[str] = []
        step = self.chunk_size - self.chunk_overlap
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end].strip()
            if len(chunk_text) >= self.min_chunk_chars:
                chunks.append(chunk_text)
            start += step

        return chunks

    def _estimate_token(self, text: str) -> int:
        return max(round(len(text) / CHARS_PER_TOKEN), 1)
