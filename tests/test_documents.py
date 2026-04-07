# tests/test_documents.py
import io

import pytest
from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_text_file(content: str = "Hello world. This is a test document.") -> tuple:
    return ("file", ("test.txt", io.BytesIO(content.encode("utf-8")), "text/plain"))


def _make_pdf_file() -> tuple:
    """Minimal valid PDF binary for testing."""
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td "
        b"(Hello PDF) Tj ET\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f\n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
    )
    return ("file", ("test.pdf", io.BytesIO(minimal_pdf), "application/pdf"))


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDocumentUpload:
    def test_upload_txt_success(self, client: TestClient) -> None:
        response = client.post("/api/v1/documents/upload", files=[_make_text_file()])
        assert response.status_code == 201
        data = response.json()
        assert "document" in data
        assert data["document"]["status"] == "pending"
        assert data["document"]["content_type"] == "text/plain"
        assert data["document"]["filename"] == "test.txt"

    def test_upload_returns_uuid(self, client: TestClient) -> None:
        response = client.post("/api/v1/documents/upload", files=[_make_text_file()])
        assert response.status_code == 201
        doc_id = response.json()["document"]["id"]
        # Must be a valid UUID string
        import uuid

        uuid.UUID(doc_id)  # raises ValueError if invalid

    def test_upload_unsupported_extension(self, client: TestClient) -> None:
        bad_file = ("file", ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream"))
        response = client.post("/api/v1/documents/upload", files=[bad_file])
        assert response.status_code == 422
        assert "extension" in response.json()["detail"].lower()

    def test_upload_empty_file(self, client: TestClient) -> None:
        empty = ("file", ("empty.txt", io.BytesIO(b""), "text/plain"))
        response = client.post("/api/v1/documents/upload", files=[empty])
        assert response.status_code == 422

    def test_get_document_after_upload(self, client: TestClient) -> None:
        upload = client.post("/api/v1/documents/upload", files=[_make_text_file()])
        doc_id = upload.json()["document"]["id"]

        response = client.get(f"/api/v1/documents/{doc_id}")
        assert response.status_code == 200
        assert response.json()["id"] == doc_id

    def test_get_document_not_found(self, client: TestClient) -> None:
        import uuid

        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/documents/{fake_id}")
        assert response.status_code == 404

    def test_list_documents(self, client: TestClient) -> None:
        # Upload two documents first
        client.post("/api/v1/documents/upload", files=[_make_text_file("Doc 1 content")])
        client.post("/api/v1/documents/upload", files=[_make_text_file("Doc 2 content")])

        response = client.get("/api/v1/documents?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 2

    def test_list_documents_invalid_limit(self, client: TestClient) -> None:
        response = client.get("/api/v1/documents?limit=0")
        assert response.status_code == 422  # FastAPI Query validation
