import uuid
from datetime import datetime
from sqlalchemy import (
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
from app.models.comparison import Comparison

VERDICT_CHECK = "verdict IN ('compatible_under_configured_policy','potential_compatibility_issues','incompatible_with_configured_contract','insufficient_evidence')"


class ProjectCompatibilityPolicies(Base):
    __tablename__ = "project_compatibility_policies"
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    policies: Mapped[dict] = mapped_column(JSON_VALUE)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CompatibilityAnalysis(Base):
    __tablename__ = "compatibility_analyses"
    __table_args__ = (
        UniqueConstraint(
            "comparison_id",
            "engine_version",
            "policy_hash",
            name="uq_compatibility_analysis",
        ),
        Index(
            "ix_compatibility_analysis_session_date", "replay_session_id", "analyzed_at"
        ),
        CheckConstraint(VERDICT_CHECK, name="ck_compatibility_analysis_verdict"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    replay_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("replay_sessions.id", ondelete="CASCADE")
    )
    request_method: Mapped[str] = mapped_column(String(10))
    endpoint_path: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(String(40))
    policy_hash: Mapped[str] = mapped_column(String(64))
    effective_policy: Mapped[dict | None] = mapped_column(JSON_VALUE, nullable=True)
    effective_comparison_rules: Mapped[dict] = mapped_column(JSON_VALUE)
    comparison_algorithm_version: Mapped[str] = mapped_column(String(40))
    verdict: Mapped[str] = mapped_column(String(50))
    counts: Mapped[dict] = mapped_column(JSON_VALUE)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    comparison: Mapped[Comparison] = relationship()
    findings: Mapped[list["CompatibilityFinding"]] = relationship(
        cascade="all, delete-orphan", order_by="CompatibilityFinding.ordinal"
    )


class CompatibilityFinding(Base):
    __tablename__ = "compatibility_findings"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id", "ordinal", name="uq_compatibility_finding_order"
        ),
        Index(
            "ix_compatibility_finding_filter",
            "analysis_id",
            "classification",
            "severity",
        ),
        CheckConstraint(
            "classification IN ('confirmed_breaking','potentially_breaking','informational','unassessed')",
            name="ck_compatibility_finding_class",
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ('critical','high','medium','low')",
            name="ck_compatibility_finding_severity",
        ),
        CheckConstraint(
            "confidence IN ('high','medium','low')",
            name="ck_compatibility_finding_confidence",
        ),
        CheckConstraint(
            "ordinal >= 0 AND ordinal < 600", name="ck_compatibility_finding_ordinal"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compatibility_analyses.id", ondelete="CASCADE")
    )
    difference_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comparison_differences.id", ondelete="SET NULL"), nullable=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(30))
    classification: Mapped[str] = mapped_column(String(25))
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    rule_id: Mapped[str] = mapped_column(String(100))
    evidence: Mapped[dict] = mapped_column(JSON_VALUE)


class CompatibilityRun(Base):
    __tablename__ = "compatibility_runs"
    __table_args__ = (
        UniqueConstraint(
            "replay_session_id",
            "engine_version",
            "fingerprint",
            name="uq_compatibility_run",
        ),
        Index("ix_compatibility_run_project_date", "project_id", "analyzed_at"),
        CheckConstraint(VERDICT_CHECK, name="ck_compatibility_run_verdict"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    replay_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("replay_sessions.id", ondelete="CASCADE")
    )
    engine_version: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(50))
    summary: Mapped[dict] = mapped_column(JSON_VALUE)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON_VALUE)
    missing_result_ids: Mapped[list] = mapped_column(JSON_VALUE)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    items: Mapped[list["CompatibilityRunItem"]] = relationship(
        cascade="all, delete-orphan", order_by="CompatibilityRunItem.ordinal"
    )


class CompatibilityRunItem(Base):
    __tablename__ = "compatibility_run_items"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_compatibility_run_order"),
        CheckConstraint("ordinal >= 0", name="ck_compatibility_run_ordinal"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compatibility_runs.id", ondelete="CASCADE"), primary_key=True
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compatibility_analyses.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    analysis: Mapped[CompatibilityAnalysis] = relationship()
