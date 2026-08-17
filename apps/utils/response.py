from typing import Any

from fastapi.responses import JSONResponse

from apps.schemas.response import APIResponse


def success_response(status_code: int, message: str, data: Any = None, meta: dict[str, Any] | None = None):
    content = APIResponse(message=message, success=True, data=data, meta=meta).model_dump()
    return JSONResponse(content=content, status_code=status_code)


def error_response(status_code: int, message: str, error: dict[str, Any] | None = None, meta: dict[str, Any] | None = None):
    content = APIResponse(message=message, success=False, error=error, meta=meta).model_dump()
    return JSONResponse(content=content, status_code=status_code)
