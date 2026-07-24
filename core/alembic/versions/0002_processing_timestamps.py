"""processing timestamps for RTF

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24

"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recordings",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recordings", "processing_completed_at")
    op.drop_column("recordings", "processing_started_at")
