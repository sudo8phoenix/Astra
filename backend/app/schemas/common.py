from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    success: bool = True
    message: str = "Request processed successfully"
    data: Any | None = None
    trace_id: str | None = None


class ApiErrorDetail(BaseModel):
    field: str | None = None
    reason: str


class ApiErrorResponse(BaseModel):
    success: bool = False
    error_code: str = Field(default="internal_error")
    message: str = Field(default="An unexpected error occurred")
    details: list[ApiErrorDetail] | None = None
    trace_id: str | None = None
