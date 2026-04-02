from fastapi import HTTPException, status


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: str = "Application error",
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)


class DocumentNotFoundError(AppException):
    def __init__(self, doc_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )


class EmbeddingServiceError(AppException):
    def __init__(self, reason: str = "Embedding generation failed") -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=reason,
        )


class UnsupportedFileTypeError(AppException):
    def __init__(self, mime_type: str) -> None:
        super().__init__(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{mime_type}' is not supported. Use PDF or plain text.",
        )
