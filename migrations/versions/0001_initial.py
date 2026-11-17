"""initial schema: questionnaire_versions, submissions

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JsonType = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "questionnaire_versions",
        sa.Column("version", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("definition", JsonType, nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("questionnaire_version", sa.Integer, sa.ForeignKey("questionnaire_versions.version"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("respondent_name", sa.String(120), nullable=True),
        sa.Column("department_code", sa.String(64), nullable=False),
        sa.Column("answers", JsonType, nullable=False),
    )
    op.create_index("ix_submissions_questionnaire_version", "submissions", ["questionnaire_version"])
    op.create_index("ix_submissions_work_date", "submissions", ["work_date"])
    op.create_index("ix_submissions_department_code", "submissions", ["department_code"])


def downgrade() -> None:
    op.drop_table("submissions")
    op.drop_table("questionnaire_versions")
