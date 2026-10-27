"""Persist Hermes stored session IDs for challenged-cycle continuation."""

from alembic import op
import sqlalchemy as sa

revision = "0007_hermes_stored_session"
down_revision = "0006_output_dispatch_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("hermes_stored_session_id", sa.String(120), nullable=True))
    op.create_index("ix_workflow_runs_hermes_stored_session_id", "workflow_runs", ["hermes_stored_session_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_hermes_stored_session_id", table_name="workflow_runs")
    op.drop_column("workflow_runs", "hermes_stored_session_id")