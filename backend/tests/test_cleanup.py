"""DELETE /api/recordings (dev cleanup) on in-memory SQLite.

FK cascade is DB-level (ondelete=CASCADE in the DDL), so the PRAGMA below is
load-bearing: without it SQLite ignores foreign keys and the bulk delete would
orphan children instead of exercising the production cascade path.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import backend.api.recordings as api
import backend.storage.blob as blob
import core.session
from core.models import Base, Chunk, Recording, Segment, Speaker


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    # session_scope resolves get_sessionmaker at call time from module globals
    monkeypatch.setattr(core.session, "get_sessionmaker", lambda: maker)
    return maker


@pytest.fixture
def purged(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "purge_jobs", lambda: calls.append(True))
    return calls


@pytest.fixture
def blob_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(blob, "get_settings", lambda: SimpleNamespace(blob_dir=str(tmp_path)))
    return tmp_path


def _seed(maker, blob_dir):
    with maker() as session:
        for i in range(2):
            rec = Recording(
                id=uuid.uuid4(), filename=f"lecture{i}.mp3", mp3_uri=f"/blob/{i}/audio.mp3",
                chunks_total=2, chunks_remaining=1, status="processing",
            )
            session.add(rec)
            # no relationship() mappings -> the UOW won't order children after
            # their recording by itself; flush the parent first (FK is enforced)
            session.flush()
            session.add(Chunk(recording_id=rec.id, chunk_index=0, start_s=0.0, end_s=45.0))
            session.add(Chunk(recording_id=rec.id, chunk_index=1, start_s=40.0, end_s=85.0))
            session.add(Speaker(
                recording_id=rec.id, speaker_id="teacher", role="teacher",
                total_speech_s=10.0, turn_count=3,
            ))
            session.add(Segment(
                recording_id=rec.id, start_s=0.0, end_s=5.0, speaker_id="teacher", text="hi",
            ))
            d = blob_dir / str(rec.id)
            d.mkdir()
            (d / "audio.mp3").write_bytes(b"mp3")
        session.commit()


def test_cleanup_wipes_rows_files_and_queues(db, purged, blob_dir):
    _seed(db, blob_dir)

    response = api.cleanup_recordings()

    assert response.deleted_recordings == 2
    assert purged == [True]
    with db() as session:
        for model in (Recording, Chunk, Speaker, Segment):
            assert session.query(model).count() == 0, model.__name__
    assert [p for p in blob_dir.iterdir() if p.is_dir()] == []


def test_cleanup_on_empty_state_is_a_noop(db, purged, blob_dir):
    response = api.cleanup_recordings()

    assert response.deleted_recordings == 0
    assert purged == [True]
