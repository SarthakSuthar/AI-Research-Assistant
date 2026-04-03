from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: bool
    message: str
    code: int


class SuccessResponse(BaseModel):
    success: bool
    message: str
    code: int
