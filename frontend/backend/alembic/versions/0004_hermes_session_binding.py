"""Bind live Hermes sessions to workflow cycles for runtime tool policy."""

from alembic import op
import sqlalchemy as sa

revision = "0004_hermes_session_binding"
down_revision = "0003_workflow_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("hermes_session_id", sa.String(120), nullable=True))
    op.create_index("ix_workflow_runs_hermes_session_id", "workflow_runs", ["hermes_session_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_hermes_session_id", table_name="workflow_runs")
    op.drop_column("workflow_runs", "hermes_session_id")