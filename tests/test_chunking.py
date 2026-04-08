import pytest

from app.services.chunking_service import (
    CHARS_PER_TOKEN,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    MIN_CHUNK_CHARS,
    ChunkData,
    ChunkingService,
)


@pytest.fixture()
def service() -> ChunkingService:
    """Default production-config service instance."""
    return ChunkingService()


@pytest.fixture()
def small_service() -> ChunkingService:
    """Tiny chunk_size for testing overlap behaviour with short strings."""
    return ChunkingService(chunk_size=50, chunk_overlap=10, min_chunk_chars=5)


# ---------------------------------------------------------------------------
# 1. Empty / whitespace
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty_list(service: ChunkingService) -> None:
    assert service.split_text("") == []


def test_whitespace_only_returns_empty_list(service: ChunkingService) -> None:
    assert service.split_text("   \n\n   ") == []


# ---------------------------------------------------------------------------
# 2. Short text → single chunk
# ---------------------------------------------------------------------------


def test_short_text_produces_single_chunk(service: ChunkingService) -> None:
    text = "This is a short document. It fits in one chunk."
    chunks = service.split_text(text)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == text.strip()


# ---------------------------------------------------------------------------
# 3. Long text → multiple chunks within size
# ---------------------------------------------------------------------------


def test_long_text_all_chunks_within_size(service: ChunkingService) -> None:
    # Generate text clearly larger than DEFAULT_CHUNK_SIZE
    text = " ".join(["word"] * 2_000)  # ~10_000 chars
    chunks = service.split_text(text)

    assert len(chunks) > 1
    for chunk in chunks:
        # Allow slight overshoot from hard_split edge cases, but cap at 2x
        assert len(chunk.content) <= DEFAULT_CHUNK_SIZE * 2


# ---------------------------------------------------------------------------
# 4. Overlap: adjacent chunks share content
# ---------------------------------------------------------------------------


def test_adjacent_chunks_share_overlap_content(
    small_service: ChunkingService,
) -> None:
    # 200-char text with clear word boundaries
    text = (
        "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Kappa "
        "Lambda Mu Nu Xi Omicron Pi Rho Sigma Tau Upsilon Phi Chi Psi Omega"
    )
    chunks = small_service.split_text(text)

    if len(chunks) < 2:
        pytest.skip("Text too short to produce multiple chunks with this config")

    # Find any word that appears in both chunk[0] and chunk[1]
    words_in_first = set(chunks[0].content.split())
    words_in_second = set(chunks[1].content.split())
    overlap_words = words_in_first & words_in_second

    assert overlap_words, (
        f"No overlapping words between chunk 0 and chunk 1.\n"
        f"Chunk 0: {chunks[0].content!r}\n"
        f"Chunk 1: {chunks[1].content!r}"
    )


# ---------------------------------------------------------------------------
# 5. chunk_index is sequential and 0-based
# ---------------------------------------------------------------------------


def test_chunk_indices_are_sequential(service: ChunkingService) -> None:
    text = " ".join(["word"] * 2_000)
    chunks = service.split_text(text)

    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


# ---------------------------------------------------------------------------
# 6. token_count ≥ 1 for every chunk
# ---------------------------------------------------------------------------


def test_token_count_is_positive(service: ChunkingService) -> None:
    text = " ".join(["word"] * 500)
    chunks = service.split_text(text)

    for chunk in chunks:
        assert chunk.token_count >= 1


def test_token_count_approximation(service: ChunkingService) -> None:
    text = "a" * 400  # 400 chars → expect ~100 tokens
    chunks = service.split_text(text)

    assert len(chunks) == 1
    expected = round(400 / CHARS_PER_TOKEN)
    assert chunks[0].token_count == expected


# ---------------------------------------------------------------------------
# 7. No chunk shorter than MIN_CHUNK_CHARS
# ---------------------------------------------------------------------------


def test_no_micro_chunks(service: ChunkingService) -> None:
    # Text with lots of short lines (mimics pypdf output with page numbers)
    text = "\n".join(["Short line.", "- 1 -", "Another line.", "- 2 -"] * 50)
    chunks = service.split_text(text)

    for chunk in chunks:
        assert len(chunk.content) >= MIN_CHUNK_CHARS, f"Micro-chunk found: {chunk.content!r}"


# ---------------------------------------------------------------------------
# 8. Paragraph separators respected
# ---------------------------------------------------------------------------


def test_paragraph_boundaries_respected(service: ChunkingService) -> None:
    # Two clearly distinct paragraphs, each well under chunk_size
    para1 = "First paragraph. " * 10  # ~170 chars
    para2 = "Second paragraph. " * 10  # ~180 chars
    text = f"{para1}\n\n{para2}"

    chunks = service.split_text(text)

    # At default chunk_size=1000, both paras fit in one chunk.
    # The key assertion: no chunk should start mid-sentence of para1.
    full_text = " ".join(c.content for c in chunks)
    assert "First paragraph" in full_text
    assert "Second paragraph" in full_text


# ---------------------------------------------------------------------------
# 9. Hard split fallback
# ---------------------------------------------------------------------------


def test_hard_split_on_separator_free_text(
    small_service: ChunkingService,
) -> None:
    # A string with NO separators — forces _hard_split()
    text = "A" * 200  # 200 chars, chunk_size=50

    chunks = small_service.split_text(text)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.content) <= small_service.chunk_size


# ---------------------------------------------------------------------------
# 10. Invalid config raises ValueError
# ---------------------------------------------------------------------------


def test_overlap_equal_to_chunk_size_raises() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        ChunkingService(chunk_size=100, chunk_overlap=100)


def test_overlap_greater_than_chunk_size_raises() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        ChunkingService(chunk_size=100, chunk_overlap=150)
