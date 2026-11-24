"""Idempotency key and payload hash on submissions (safe retries).

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("idempotency_key", sa.String(36), nullable=True))
    op.add_column("submissions", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.create_index("uq_submissions_idempotency_key", "submissions", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_submissions_idempotency_key", table_name="submissions")
    op.drop_column("submissions", "payload_hash")
    op.drop_column("submissions", "idempotency_key")
