from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

RUN_OUTCOMES = ("running", "ok", "partial", "error", "skipped", "abandoned")


class SourceRun(Base):
    """One refresh attempt of one source. pipeline_status keeps only the latest
    outcome per source; this keeps the history (pruned after 400 days), so a
    degraded, skipped, or abandoned run stays visible after the next one.
    Written by app.pipelines.runs."""

    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50))
    trigger: Mapped[str] = mapped_column(String(20))  # schedule | manual
    code_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_succeeded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # [{name, sha256, bytes, modified_at}] for each staging file the load read.
    # modified_at shows when a file was left over from an earlier pull.
    inputs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('running', 'ok', 'partial', 'error', 'skipped', 'abandoned')",
            name="ck_source_runs_outcome",
        ),
        Index("ix_source_runs_source_started_at", "source", "started_at"),
    )
