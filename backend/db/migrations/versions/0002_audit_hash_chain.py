"""Audit log hash chain — prev_hash / entry_hash per entry

Revision ID: 0002_audit_hash_chain
Revises: 0001_initial
Create Date: 2026-10-24 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_audit_hash_chain"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: rows written before this migration stay unchained ("legacy")
    op.add_column("audit_logs", sa.Column("prev_hash", sa.Text(), nullable=True))
    op.add_column("audit_logs", sa.Column("entry_hash", sa.Text(), nullable=True))
    op.create_index("ix_audit_logs_prev_hash", "audit_logs", ["prev_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_prev_hash", table_name="audit_logs")
    op.drop_column("audit_logs", "entry_hash")
    op.drop_column("audit_logs", "prev_hash")
