"""initial schema: recordings, chunks, speakers, segments

Revision ID: 0001
Revises:
Create Date: 2026-07-22

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recordings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expected_speakers", sa.Integer(), nullable=True),
        sa.Column("chunks_total", sa.Integer(), nullable=False),
        sa.Column("chunks_remaining", sa.Integer(), nullable=False),
        sa.Column("mp3_uri", sa.String(1024), nullable=False),
        sa.Column("wav_uri", sa.String(1024), nullable=True),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recording_id",
            sa.Uuid(),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("result", JSONB(), nullable=True),
        sa.UniqueConstraint("recording_id", "chunk_index"),
    )
    op.create_table(
        "speakers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recording_id",
            sa.Uuid(),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("speaker_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("total_speech_s", sa.Float(), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("recording_id", "speaker_id"),
    )
    op.create_table(
        "segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recording_id",
            sa.Uuid(),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("speaker_id", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index("ix_segments_recording_start", "segments", ["recording_id", "start_s"])


def downgrade() -> None:
    op.drop_index("ix_segments_recording_start", table_name="segments")
    op.drop_table("segments")
    op.drop_table("speakers")
    op.drop_table("chunks")
    op.drop_table("recordings")
