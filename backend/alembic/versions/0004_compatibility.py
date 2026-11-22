"""Persist deterministic compatibility analyses and policy history"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_compatibility"
down_revision = "0003_comparisons"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_compatibility_policies",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column(
            "policies",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "compatibility_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("replay_session_id", sa.Uuid(), nullable=False),
        sa.Column("engine_version", sa.String(length=40), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=50), nullable=False),
        sa.Column(
            "summary",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "metadata_snapshot",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "missing_result_ids",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('compatible_under_configured_policy','potential_compatibility_issues','incompatible_with_configured_contract','insufficient_evidence')",
            name="ck_compatibility_run_verdict",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replay_session_id"], ["replay_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "replay_session_id",
            "engine_version",
            "fingerprint",
            name="uq_compatibility_run",
        ),
    )
    op.create_index(
        "ix_compatibility_run_project_date",
        "compatibility_runs",
        ["project_id", "analyzed_at"],
        unique=False,
    )
    op.create_table(
        "compatibility_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("replay_session_id", sa.Uuid(), nullable=False),
        sa.Column("request_method", sa.String(length=10), nullable=False),
        sa.Column("endpoint_path", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(length=40), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "effective_policy",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
        sa.Column(
            "effective_comparison_rules",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("comparison_algorithm_version", sa.String(length=40), nullable=False),
        sa.Column("verdict", sa.String(length=50), nullable=False),
        sa.Column(
            "counts",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('compatible_under_configured_policy','potential_compatibility_issues','incompatible_with_configured_contract','insufficient_evidence')",
            name="ck_compatibility_analysis_verdict",
        ),
        sa.ForeignKeyConstraint(
            ["comparison_id"], ["comparisons.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replay_session_id"], ["replay_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comparison_id",
            "engine_version",
            "policy_hash",
            name="uq_compatibility_analysis",
        ),
    )
    op.create_index(
        "ix_compatibility_analysis_session_date",
        "compatibility_analyses",
        ["replay_session_id", "analyzed_at"],
        unique=False,
    )
    op.create_table(
        "compatibility_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("difference_id", sa.Uuid(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column("classification", sa.String(length=25), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=True),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column(
            "evidence",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "classification IN ('confirmed_breaking','potentially_breaking','informational','unassessed')",
            name="ck_compatibility_finding_class",
        ),
        sa.CheckConstraint(
            "confidence IN ('high','medium','low')",
            name="ck_compatibility_finding_confidence",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('critical','high','medium','low')",
            name="ck_compatibility_finding_severity",
        ),
        sa.CheckConstraint(
            "ordinal >= 0 AND ordinal < 600", name="ck_compatibility_finding_ordinal"
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["compatibility_analyses.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["difference_id"], ["comparison_differences.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id", "ordinal", name="uq_compatibility_finding_order"
        ),
    )
    op.create_index(
        "ix_compatibility_finding_filter",
        "compatibility_findings",
        ["analysis_id", "classification", "severity"],
        unique=False,
    )
    op.create_table(
        "compatibility_run_items",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_compatibility_run_ordinal"),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["compatibility_analyses.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["compatibility_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id", "analysis_id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_compatibility_run_order"),
    )


def downgrade():
    op.drop_table("compatibility_run_items")
    op.drop_index(
        "ix_compatibility_finding_filter", table_name="compatibility_findings"
    )
    op.drop_table("compatibility_findings")
    op.drop_index(
        "ix_compatibility_analysis_session_date", table_name="compatibility_analyses"
    )
    op.drop_table("compatibility_analyses")
    op.drop_index("ix_compatibility_run_project_date", table_name="compatibility_runs")
    op.drop_table("compatibility_runs")
    op.drop_table("project_compatibility_policies")
