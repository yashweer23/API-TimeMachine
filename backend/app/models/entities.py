import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


JSON_VALUE = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True), "postgresql"
)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    recordings: Mapped[list["Recording"]] = relationship(
        back_populates="project", passive_deletes=True
    )


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        Index("ix_recordings_project_captured", "project_id", "captured_at"),
        Index("ix_recordings_project_baseline", "project_id", "is_baseline"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(160))
    method: Mapped[str] = mapped_column(String(10))
    base_url: Mapped[str] = mapped_column(String(2048))
    endpoint_path: Mapped[str] = mapped_column(String(2048))
    query_parameters: Mapped[dict] = mapped_column(JSON_VALUE)
    request_headers: Mapped[dict] = mapped_column(JSON_VALUE)
    request_body: Mapped[Any | None] = mapped_column(JSON_VALUE, nullable=True)
    request_body_present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict] = mapped_column(JSON_VALUE, default=dict)
    response_body: Mapped[Any | None] = mapped_column(JSON_VALUE, nullable=True)
    response_body_kind: Mapped[str] = mapped_column(String(10), default="empty")
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    environment_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_error: Mapped[dict | None] = mapped_column(JSON_VALUE, nullable=True)
    project: Mapped[Project] = relationship(back_populates="recordings")
