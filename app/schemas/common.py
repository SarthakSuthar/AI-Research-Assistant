from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    message: str
    code: int


class SuccessResponse(BaseModel):
    success: bool
    message: str
    code: int
