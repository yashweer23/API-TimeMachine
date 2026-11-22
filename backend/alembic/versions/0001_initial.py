"""Projects and immutable request/response snapshots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = depends_on = None
json_type = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "recordings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("endpoint_path", sa.String(2048), nullable=False),
        sa.Column("query_parameters", json_type, nullable=False),
        sa.Column("request_headers", json_type, nullable=False),
        sa.Column("request_body", json_type, nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", json_type, nullable=False),
        sa.Column("response_body", json_type, nullable=True),
        sa.Column("response_body_kind", sa.String(10), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("environment_label", sa.String(80), nullable=True),
        sa.Column("is_baseline", sa.Boolean(), nullable=False),
        sa.Column("execution_error", json_type, nullable=True),
    )
    op.create_index(
        "ix_recordings_project_captured", "recordings", ["project_id", "captured_at"]
    )
    op.create_index(
        "ix_recordings_project_baseline", "recordings", ["project_id", "is_baseline"]
    )


def downgrade():
    op.drop_table("recordings")
    op.drop_table("projects")
