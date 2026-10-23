"""Initial schema — all 7 tables + outbox

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-20 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("reference_number", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="OBSERVE"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="raw"),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("source_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="INITIALIZE"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "agent_actions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("agent_actions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("payload_hash", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("agent_actions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("audit_logs")
    op.drop_table("approvals")
    op.drop_table("agent_actions")
    op.drop_table("agent_tasks")
    op.drop_table("events")
    op.drop_table("documents")
    op.drop_table("shipments")
