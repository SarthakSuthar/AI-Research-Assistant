from fastapi import HTTPException, status


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: str = "Application error",
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)


class DocumentNotFoundError(Exception):
    """Raised when a requested document ID does not exist in the database."""


class UnsupportedFileTypeError(Exception):
    """Raised when an uploaded file fails type, size, or content validation."""


class EmbeddingServiceError(Exception):
    """Raised when the Gemini embedding API fails"""
