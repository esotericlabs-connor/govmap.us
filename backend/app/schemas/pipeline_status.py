from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PipelineSourceStatus(BaseModel):
    last_updated: datetime
    record_count: int
    status: Literal["ok", "stale", "error"]
    detail: str | None = None


class PipelineStatus(BaseModel):
    sources: dict[str, PipelineSourceStatus] = {}
