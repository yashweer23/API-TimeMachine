import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from app.models.entities import JSON_VALUE, utcnow
from app.models.replay import ReplayResult


class ProjectComparisonSettings(Base):
    __tablename__ = "project_comparison_settings"
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    rules: Mapped[dict] = mapped_column(JSON_VALUE)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Comparison(Base):
    __tablename__ = "comparisons"
    __table_args__ = (
        UniqueConstraint(
            "replay_result_id",
            "algorithm_version",
            "rules_hash",
            name="uq_comparison_configuration",
        ),
        Index("ix_comparisons_result_compared", "replay_result_id", "compared_at"),
        CheckConstraint(
            "comparison_status IN ('identical','different','partial','unavailable','limited')",
            name="ck_comparison_status",
        ),
        CheckConstraint(
            "total_differences >= 0 AND total_differences <= 500",
            name="ck_comparison_count",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    replay_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("replay_results.id", ondelete="CASCADE")
    )
    comparison_status: Mapped[str] = mapped_column(String(20))
    original_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replay_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_differences: Mapped[int] = mapped_column(Integer)
    counts: Mapped[dict] = mapped_column(JSON_VALUE)
    effective_rules: Mapped[dict] = mapped_column(JSON_VALUE)
    rules_hash: Mapped[str] = mapped_column(String(64))
    algorithm_version: Mapped[str] = mapped_column(String(40))
    compared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    notes: Mapped[list] = mapped_column(JSON_VALUE)
    replay_result: Mapped[ReplayResult] = relationship()
    differences: Mapped[list["Difference"]] = relationship(
        back_populates="comparison",
        cascade="all, delete-orphan",
        order_by="Difference.ordinal",
    )


class Difference(Base):
    __tablename__ = "comparison_differences"
    __table_args__ = (
        UniqueConstraint("comparison_id", "ordinal", name="uq_difference_order"),
        CheckConstraint(
            "scope IN ('body','headers','status')", name="ck_difference_scope"
        ),
        CheckConstraint(
            "change_type IN ('field_added','field_removed','value_changed','type_changed','array_changed','status_changed','header_added','header_removed','header_changed','text_changed')",
            name="ck_difference_type",
        ),
        CheckConstraint(
            "ordinal >= 0 AND (old_present OR new_present)",
            name="ck_difference_presence",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(30))
    old_type: Mapped[str] = mapped_column(String(20))
    new_type: Mapped[str] = mapped_column(String(20))
    old_present: Mapped[bool] = mapped_column(Boolean)
    new_present: Mapped[bool] = mapped_column(Boolean)
    old_value: Mapped[Any | None] = mapped_column(JSON_VALUE, nullable=True)
    new_value: Mapped[Any | None] = mapped_column(JSON_VALUE, nullable=True)
    old_preview: Mapped[str] = mapped_column(Text)
    new_preview: Mapped[str] = mapped_column(Text)
    old_value_truncated: Mapped[bool] = mapped_column(Boolean)
    new_value_truncated: Mapped[bool] = mapped_column(Boolean)
    comparison: Mapped[Comparison] = relationship(back_populates="differences")
