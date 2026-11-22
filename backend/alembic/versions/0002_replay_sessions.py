"""Add persistent replay sessions/results and lossless body-presence metadata.

Existing Phase 1 recordings remain unchanged; null bodies have unknown presence.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_replay_sessions"
down_revision = "0001_initial"
branch_labels = depends_on = None
json_type = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def upgrade():
    op.add_column(
        "recordings", sa.Column("request_body_present", sa.Boolean(), nullable=True)
    )
    op.execute(
        "UPDATE recordings SET request_body_present = true WHERE request_body IS NOT NULL"
    )
    op.create_table(
        "replay_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("target_base_url", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("total_requests", sa.Integer(), nullable=False),
        sa.Column("completed_requests", sa.Integer(), nullable=False),
        sa.Column("failed_requests", sa.Integer(), nullable=False),
        sa.Column("error_requests", sa.Integer(), nullable=False),
        sa.Column("http_responses", sa.Integer(), nullable=False),
        sa.Column("skipped_requests", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','completed','completed_with_errors','timed_out','interrupted')",
            name="ck_replay_session_status",
        ),
        sa.CheckConstraint(
            "total_requests > 0 AND completed_requests >= 0 AND completed_requests <= total_requests",
            name="ck_replay_session_completed",
        ),
        sa.CheckConstraint(
            "failed_requests >= 0 AND failed_requests <= error_requests AND error_requests <= completed_requests",
            name="ck_replay_session_failures",
        ),
        sa.CheckConstraint(
            "http_responses >= 0 AND http_responses <= completed_requests AND skipped_requests >= 0 AND skipped_requests <= error_requests",
            name="ck_replay_session_counts",
        ),
    )
    op.create_index(
        "ix_replay_sessions_project_started",
        "replay_sessions",
        ["project_id", "started_at"],
    )
    op.create_table(
        "replay_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "replay_session_id",
            sa.Uuid(),
            sa.ForeignKey("replay_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "original_recording_id",
            sa.Uuid(),
            sa.ForeignKey("recordings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("request_method", sa.String(10), nullable=False),
        sa.Column("endpoint_path", sa.String(2048), nullable=False),
        sa.Column("replay_url", sa.String(4096), nullable=False),
        sa.Column("request_metadata", json_type, nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", json_type, nullable=False),
        sa.Column("response_body", json_type, nullable=True),
        sa.Column("response_body_kind", sa.String(10), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("execution_error", json_type, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "replay_session_id", "ordinal", name="uq_replay_result_order"
        ),
        sa.UniqueConstraint(
            "replay_session_id", "original_recording_id", name="uq_replay_result_source"
        ),
        sa.CheckConstraint(
            "outcome IN ('pending','running','http_response','transport_error','capture_error','blocked','skipped','interrupted')",
            name="ck_replay_result_outcome",
        ),
        sa.CheckConstraint(
            "ordinal >= 0 AND duration_ms >= 0", name="ck_replay_result_metrics"
        ),
    )
    op.create_index(
        "ix_replay_results_original", "replay_results", ["original_recording_id"]
    )


def downgrade():
    op.drop_table("replay_results")
    op.drop_table("replay_sessions")
    op.drop_column("recordings", "request_body_present")
