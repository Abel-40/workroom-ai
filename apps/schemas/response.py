from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")
class APIResponse(BaseModel,Generic[T]):
  message:str
  success:bool
  data:T | None = None
  error:dict[str, Any] | None = None
  meta:dict[str, Any] | None = None