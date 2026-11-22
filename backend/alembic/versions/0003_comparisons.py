"""Persist reproducible comparisons and bounded difference records; preserve captures."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_comparisons"
down_revision = "0002_replay_sessions"
branch_labels = depends_on = None
json_type = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def upgrade():
    op.create_table(
        "project_comparison_settings",
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("rules", json_type, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "comparisons",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "replay_result_id",
            sa.Uuid(),
            sa.ForeignKey("replay_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("comparison_status", sa.String(20), nullable=False),
        sa.Column("original_status_code", sa.Integer(), nullable=True),
        sa.Column("replay_status_code", sa.Integer(), nullable=True),
        sa.Column("total_differences", sa.Integer(), nullable=False),
        sa.Column("counts", json_type, nullable=False),
        sa.Column("effective_rules", json_type, nullable=False),
        sa.Column("rules_hash", sa.String(64), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("compared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", json_type, nullable=False),
        sa.UniqueConstraint(
            "replay_result_id",
            "algorithm_version",
            "rules_hash",
            name="uq_comparison_configuration",
        ),
        sa.CheckConstraint(
            "comparison_status IN ('identical','different','partial','unavailable','limited')",
            name="ck_comparison_status",
        ),
        sa.CheckConstraint(
            "total_differences >= 0 AND total_differences <= 500",
            name="ck_comparison_count",
        ),
    )
    op.create_index(
        "ix_comparisons_result_compared",
        "comparisons",
        ["replay_result_id", "compared_at"],
    )
    op.create_table(
        "comparison_differences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "comparison_id",
            sa.Uuid(),
            sa.ForeignKey("comparisons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("old_type", sa.String(20), nullable=False),
        sa.Column("new_type", sa.String(20), nullable=False),
        sa.Column("old_present", sa.Boolean(), nullable=False),
        sa.Column("new_present", sa.Boolean(), nullable=False),
        sa.Column("old_value", json_type, nullable=True),
        sa.Column("new_value", json_type, nullable=True),
        sa.Column("old_preview", sa.Text(), nullable=False),
        sa.Column("new_preview", sa.Text(), nullable=False),
        sa.Column("old_value_truncated", sa.Boolean(), nullable=False),
        sa.Column("new_value_truncated", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("comparison_id", "ordinal", name="uq_difference_order"),
        sa.CheckConstraint(
            "scope IN ('body','headers','status')", name="ck_difference_scope"
        ),
        sa.CheckConstraint(
            "change_type IN ('field_added','field_removed','value_changed','type_changed','array_changed','status_changed','header_added','header_removed','header_changed','text_changed')",
            name="ck_difference_type",
        ),
        sa.CheckConstraint(
            "ordinal >= 0 AND (old_present OR new_present)",
            name="ck_difference_presence",
        ),
    )


def downgrade():
    op.drop_table("comparison_differences")
    op.drop_index("ix_comparisons_result_compared", table_name="comparisons")
    op.drop_table("comparisons")
    op.drop_table("project_comparison_settings")
