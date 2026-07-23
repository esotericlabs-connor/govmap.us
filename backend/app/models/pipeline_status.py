from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PipelineStatusRow(Base):
    """Per-source pipeline health. Replaces the ephemeral pipeline_status.json so
    status survives container restarts and is queryable. One row per source,
    updated after every run via app.pipelines.status.record_run()."""

    __tablename__ = "pipeline_status"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ok | stale | error
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
