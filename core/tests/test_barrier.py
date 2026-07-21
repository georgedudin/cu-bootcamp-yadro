"""Barrier semantics on an in-memory SQLite DB (UPDATE..RETURNING works on
SQLite >= 3.35, so the exact production statements are exercised)."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.barrier import record_chunk_done
from core.models import Base, Chunk, Recording


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


@pytest.fixture
def recording(session):
    rec = Recording(
        id=uuid.uuid4(), filename="x.mp3", mp3_uri="/blob/x.mp3",
        chunks_total=3, chunks_remaining=3, status="processing",
    )
    session.add(rec)
    for i in range(3):
        session.add(Chunk(recording_id=rec.id, chunk_index=i, start_s=i * 40.0, end_s=i * 40.0 + 45.0))
    session.commit()
    return rec


def test_last_chunk_observes_zero_exactly_once(session, recording):
    assert record_chunk_done(session, recording.id, 0, {"r": 0}) == 2
    assert record_chunk_done(session, recording.id, 1, {"r": 1}) == 1
    assert record_chunk_done(session, recording.id, 2, {"r": 2}) == 0
    session.commit()


def test_duplicate_delivery_does_not_double_decrement(session, recording):
    assert record_chunk_done(session, recording.id, 0, {"v": 1}) == 2
    session.commit()
    # same chunk delivered again (RQ is at-least-once): no decrement
    assert record_chunk_done(session, recording.id, 0, {"v": 2}) is None
    session.commit()
    assert session.get(Recording, recording.id).chunks_remaining == 2


def test_crash_before_commit_rolls_back_both_statements(session, recording):
    record_chunk_done(session, recording.id, 0, {"v": 1})
    session.rollback()  # simulated worker crash mid-job
    rec = session.get(Recording, recording.id)
    assert rec.chunks_remaining == 3
    # the retry now succeeds and decrements exactly once
    assert record_chunk_done(session, recording.id, 0, {"v": 2}) == 2
    session.commit()
