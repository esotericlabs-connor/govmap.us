from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UpstreamBudget(Base):
    __tablename__ = "upstream_budgets"

    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    initialized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('congress', 'fec', 'govinfo')", name="ck_upstream_budgets_source"
        ),
    )


class UpstreamRequest(Base):
    """A committed reservation, never refunded after failure or cancellation."""

    __tablename__ = "upstream_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String(16), ForeignKey("upstream_budgets.source", ondelete="CASCADE")
    )
    scope: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "scope IN ('shared', 'api', 'worker')", name="ck_upstream_requests_scope"
        ),
        Index("ix_upstream_requests_source_started_at", "source", "started_at"),
    )
