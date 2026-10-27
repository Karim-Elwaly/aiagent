"""Persist proposals, challenge decisions, governance rooms, and daemon jobs."""

from alembic import op
import sqlalchemy as sa

revision = "0002_control_plane_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("missions", sa.Column("proposal", sa.JSON(), nullable=True))
    op.add_column("missions", sa.Column("competitive_benchmarking", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("missions", sa.Column("clarification_answers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("fleet_agents", sa.Column("applied_specification", sa.JSON(), nullable=True))
    op.add_column("workflow_runs", sa.Column("usage_usd", sa.Float(), nullable=False, server_default="0"))
    op.create_table(
        "decision_rooms",
        sa.Column("room_id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.mission_id"), nullable=True),
        sa.Column("fleet_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("fleet_agents.agent_id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("epistemic_basis", sa.String(24), nullable=False),
        sa.Column("assurance_verdict", sa.String(24), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_by", sa.String(240)),
        sa.Column("decision_note", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_decision_rooms_mission_id", "decision_rooms", ["mission_id"])
    op.create_index("ix_decision_rooms_fleet_id", "decision_rooms", ["fleet_id"])
    op.create_index("ix_decision_rooms_agent_id", "decision_rooms", ["agent_id"])
    op.create_index("ix_decision_rooms_status", "decision_rooms", ["status"])
    op.create_table(
        "challenge_gates",
        sa.Column("gate_id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.mission_id"), nullable=False),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("challenge_snapshot", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(24)),
        sa.Column("feedback", sa.Text()),
        sa.Column("actor_id", sa.String(240)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_challenge_gates_mission_id", "challenge_gates", ["mission_id"])
    op.create_index("ix_challenge_gates_state", "challenge_gates", ["state"])
    op.create_table(
        "daemon_jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(48), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("claimed_by", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )
    op.create_index("ix_daemon_jobs_job_type", "daemon_jobs", ["job_type"])
    op.create_index("ix_daemon_jobs_status", "daemon_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("daemon_jobs")
    op.drop_table("challenge_gates")
    op.drop_table("decision_rooms")
    op.drop_column("workflow_runs", "usage_usd")
    op.drop_column("fleet_agents", "applied_specification")
    op.drop_column("missions", "proposal")
    op.drop_column("missions", "competitive_benchmarking")
    op.drop_column("missions", "clarification_answers")