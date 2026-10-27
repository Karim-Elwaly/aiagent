"""Track idempotent email and structured-form output dispatch."""

from alembic import op
import sqlalchemy as sa

revision = "0006_output_dispatch_state"
down_revision = "0005_event_trigger_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decision_rooms", sa.Column("email_dispatch_status", sa.String(24), nullable=False, server_default="NOT_SENT"))
    op.add_column("decision_rooms", sa.Column("form_dispatch_status", sa.String(24), nullable=False, server_default="NOT_SENT"))
    op.create_index("ix_decision_rooms_email_dispatch_status", "decision_rooms", ["email_dispatch_status"])
    op.create_index("ix_decision_rooms_form_dispatch_status", "decision_rooms", ["form_dispatch_status"])


def downgrade() -> None:
    op.drop_index("ix_decision_rooms_form_dispatch_status", table_name="decision_rooms")
    op.drop_index("ix_decision_rooms_email_dispatch_status", table_name="decision_rooms")
    op.drop_column("decision_rooms", "form_dispatch_status")
    op.drop_column("decision_rooms", "email_dispatch_status")