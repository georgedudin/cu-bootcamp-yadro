"""Postgres is the source of truth (architecture §6). Redis only moves jobs.

recordings 1:N chunks   (map results: segments + turn embeddings in result JSON)
           1:N speakers (reduce output: stable global ids + roles)
           1:N segments (reduce output: the final timeline the FE reads)
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from contracts import RecordingStatus

# Chunk-level states (internal — not on the wire; the FE only sees progress counts)
CHUNK_PENDING = "pending"
CHUNK_DONE = "done"
CHUNK_FAILED = "failed"

ResultJSON = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    duration_s: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default=RecordingStatus.uploaded.value)
    # RTF timing: started = the first chunk flips queued->processing; completed =
    # stitch marks the recording done. rtf = (completed - started) / duration_s.
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    expected_speakers: Mapped[int | None] = mapped_column(Integer)
    chunks_total: Mapped[int] = mapped_column(Integer, default=0)
    chunks_remaining: Mapped[int] = mapped_column(Integer, default=0)
    mp3_uri: Mapped[str] = mapped_column(String(1024))
    wav_uri: Mapped[str | None] = mapped_column(String(1024))


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("recording_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default=CHUNK_PENDING)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(ResultJSON)


class Speaker(Base):
    __tablename__ = "speakers"
    __table_args__ = (UniqueConstraint("recording_id", "speaker_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="CASCADE")
    )
    speaker_id: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))
    total_speech_s: Mapped[float] = mapped_column(Float)
    turn_count: Mapped[int] = mapped_column(Integer)


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (Index("ix_segments_recording_start", "recording_id", "start_s"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="CASCADE")
    )
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    speaker_id: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
