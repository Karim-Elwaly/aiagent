"""Persist per-step workflow execution telemetry."""

from alembic import op
import sqlalchemy as sa

revision = "0003_workflow_steps"
down_revision = "0002_control_plane_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_steps",
        sa.Column("step_run_id", sa.String(36), primary_key=True),
        sa.Column("workflow_cycle_id", sa.String(36), sa.ForeignKey("workflow_runs.workflow_cycle_id"), nullable=False),
        sa.Column("step_id", sa.String(36), nullable=False),
        sa.Column("capability_id", sa.String(240), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("usage_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_workflow_steps_workflow_cycle_id", "workflow_steps", ["workflow_cycle_id"])
    op.create_index("ix_workflow_steps_step_id", "workflow_steps", ["step_id"])
    op.create_index("ix_workflow_steps_capability_id", "workflow_steps", ["capability_id"])
    op.create_index("ix_workflow_steps_status", "workflow_steps", ["status"])


def downgrade() -> None:
    op.drop_table("workflow_steps")