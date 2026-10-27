"""Create Fleet Studio mission and workflow tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("mission_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "blueprints",
        sa.Column("blueprint_id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.mission_id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("specification", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_blueprints_mission_id", "blueprints", ["mission_id"])
    op.create_table(
        "fleet_agents",
        sa.Column("agent_id", sa.String(36), primary_key=True),
        sa.Column("blueprint_id", sa.String(36), sa.ForeignKey("blueprints.blueprint_id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("specification", sa.JSON(), nullable=False),
        sa.Column("managed_state", sa.String(24), nullable=False),
    )
    op.create_index("ix_fleet_agents_blueprint_id", "fleet_agents", ["blueprint_id"])
    op.create_table(
        "agent_workflows",
        sa.Column("workflow_id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("fleet_agents.agent_id"), nullable=False),
        sa.Column("trigger_policy", sa.String(24), nullable=False),
        sa.Column("workflow_specification", sa.JSON(), nullable=False),
    )
    op.create_index("ix_agent_workflows_agent_id", "agent_workflows", ["agent_id"])
    op.create_table(
        "workflow_runs",
        sa.Column("workflow_cycle_id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("fleet_agents.agent_id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_workflow_runs_agent_id", "workflow_runs", ["agent_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_table(
        "policies",
        sa.Column("policy_id", sa.String(36), primary_key=True),
        sa.Column("blueprint_id", sa.String(36), sa.ForeignKey("blueprints.blueprint_id"), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
    )
    op.create_index("ix_policies_blueprint_id", "policies", ["blueprint_id"])
    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("fleet_id", sa.String(36), nullable=False),
        sa.Column("workflow_cycle_id", sa.String(36), sa.ForeignKey("workflow_runs.workflow_cycle_id"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("fleet_agents.agent_id"), nullable=False),
        sa.Column("step_id", sa.String(36), nullable=False),
        sa.Column("epistemic_basis", sa.String(24), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("assurance_verdict", sa.String(24)),
    )
    op.create_index("ix_evidence_fleet_id", "evidence", ["fleet_id"])
    op.create_index("ix_evidence_workflow_cycle_id", "evidence", ["workflow_cycle_id"])
    op.create_index("ix_evidence_agent_id", "evidence", ["agent_id"])
    op.create_index("ix_evidence_step_id", "evidence", ["step_id"])


def downgrade() -> None:
    op.drop_table("evidence")
    op.drop_table("policies")
    op.drop_table("workflow_runs")
    op.drop_table("agent_workflows")
    op.drop_table("fleet_agents")
    op.drop_table("blueprints")
    op.drop_table("missions")