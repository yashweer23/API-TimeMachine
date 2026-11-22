import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from app.models.entities import JSON_VALUE, Project, Recording, utcnow


class ReplaySession(Base):
    __tablename__ = "replay_sessions"
    __table_args__ = (
        Index("ix_replay_sessions_project_started", "project_id", "started_at"),
        CheckConstraint(
            "status IN ('running','completed','completed_with_errors','timed_out','interrupted')",
            name="ck_replay_session_status",
        ),
        CheckConstraint(
            "total_requests > 0 AND completed_requests >= 0 AND completed_requests <= total_requests",
            name="ck_replay_session_completed",
        ),
        CheckConstraint(
            "failed_requests >= 0 AND failed_requests <= error_requests AND error_requests <= completed_requests",
            name="ck_replay_session_failures",
        ),
        CheckConstraint(
            "http_responses >= 0 AND http_responses <= completed_requests AND skipped_requests >= 0 AND skipped_requests <= error_requests",
            name="ck_replay_session_counts",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(160))
    target_base_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(30), default="running")
    total_requests: Mapped[int] = mapped_column(Integer)
    completed_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    error_requests: Mapped[int] = mapped_column(Integer, default=0)
    http_responses: Mapped[int] = mapped_column(Integer, default=0)
    skipped_requests: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    project: Mapped[Project] = relationship()
    results: Mapped[list["ReplayResult"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ReplayResult.ordinal",
    )


class ReplayResult(Base):
    __tablename__ = "replay_results"
    __table_args__ = (
        UniqueConstraint("replay_session_id", "ordinal", name="uq_replay_result_order"),
        UniqueConstraint(
            "replay_session_id", "original_recording_id", name="uq_replay_result_source"
        ),
        Index("ix_replay_results_original", "original_recording_id"),
        CheckConstraint(
            "outcome IN ('pending','running','http_response','transport_error','capture_error','blocked','skipped','interrupted')",
            name="ck_replay_result_outcome",
        ),
        CheckConstraint(
            "ordinal >= 0 AND duration_ms >= 0", name="ck_replay_result_metrics"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    replay_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("replay_sessions.id", ondelete="CASCADE")
    )
    original_recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    request_method: Mapped[str] = mapped_column(String(10))
    endpoint_path: Mapped[str] = mapped_column(String(2048))
    replay_url: Mapped[str] = mapped_column(String(4096))
    request_metadata: Mapped[dict] = mapped_column(JSON_VALUE)
    outcome: Mapped[str] = mapped_column(String(30), default="pending")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict] = mapped_column(JSON_VALUE, default=dict)
    response_body: Mapped[Any | None] = mapped_column(JSON_VALUE, nullable=True)
    response_body_kind: Mapped[str] = mapped_column(String(10), default="empty")
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    execution_error: Mapped[dict | None] = mapped_column(JSON_VALUE, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    session: Mapped[ReplaySession] = relationship(back_populates="results")
    original_recording: Mapped[Recording] = relationship()
