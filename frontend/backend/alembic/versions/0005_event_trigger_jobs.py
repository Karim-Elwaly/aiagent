"""Persist workflow trigger context and event-job idempotency."""

from alembic import op
import sqlalchemy as sa

revision = "0005_event_trigger_jobs"
down_revision = "0004_hermes_session_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("trigger_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("daemon_jobs", sa.Column("idempotency_key", sa.String(240), nullable=True))
    op.create_index("ix_daemon_jobs_idempotency_key", "daemon_jobs", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_daemon_jobs_idempotency_key", table_name="daemon_jobs")
    op.drop_column("daemon_jobs", "idempotency_key")
    op.drop_column("workflow_runs", "trigger_context")