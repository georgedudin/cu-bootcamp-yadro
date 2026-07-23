"""The five REST endpoints (architecture §5A). Sync handlers on purpose —
FastAPI runs them in a threadpool, and upload/ingest is blocking work
(disk streaming + ffmpeg)."""

import logging
import subprocess
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.orchestration.ingest import ingest
from backend.orchestration.queue import purge_jobs
from backend.storage.blob import delete_all_blobs, save_mp3
from contracts import (
    CleanupResponse,
    Progress,
    RecordingCreateResponse,
    RecordingDetail,
    RecordingStatus,
    RecordingSummary,
    Timeline,
    TimelineSegment,
    TimelineSpeaker,
)
from core.models import Recording, Segment, Speaker
from core.session import session_scope

log = logging.getLogger(__name__)
router = APIRouter(tags=["recordings"])


def _summary_kwargs(rec: Recording) -> dict:
    return {
        "id": rec.id,
        "filename": rec.filename,
        "uploaded_at": rec.uploaded_at,
        "duration_s": rec.duration_s,
        "status": RecordingStatus(rec.status),
        "progress": Progress(
            done_chunks=rec.chunks_total - rec.chunks_remaining,
            total_chunks=rec.chunks_total,
        ),
    }


def _get_or_404(session, recording_id: UUID) -> Recording:
    rec = session.get(Recording, recording_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    return rec


@router.post("/recordings", status_code=201)
def upload_recording(
    file: UploadFile, expected_speakers: int | None = Form(default=None, ge=2)
) -> RecordingCreateResponse:
    if not (file.filename or "").lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="expected an .mp3 file")

    with session_scope() as session:
        rec = Recording(
            filename=file.filename,
            status=RecordingStatus.uploaded.value,
            expected_speakers=expected_speakers,
            mp3_uri="",
        )
        session.add(rec)
        session.flush()
        recording_id = rec.id
        rec.mp3_uri = str(save_mp3(recording_id, file.file))

    try:
        ingest(recording_id)
    except (subprocess.CalledProcessError, ValueError) as exc:
        log.exception("ingest failed for %s", recording_id)
        with session_scope() as session:
            _get_or_404(session, recording_id).status = RecordingStatus.failed.value
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise HTTPException(status_code=400, detail=f"could not decode audio: {detail}")

    return RecordingCreateResponse(id=recording_id, status=RecordingStatus.queued)


@router.get("/recordings")
def list_recordings() -> list[RecordingSummary]:
    with session_scope() as session:
        recs = session.scalars(select(Recording).order_by(Recording.uploaded_at.desc())).all()
        return [RecordingSummary(**_summary_kwargs(r)) for r in recs]


@router.delete("/recordings")
def cleanup_recordings() -> CleanupResponse:
    """DEV TOOL: wipe everything — jobs, DB rows, audio files — even
    recordings still mid-processing. Order matters: stop new work first,
    then rows (children cascade at the DB level), then files, so the API
    never lists a recording whose blob is already gone. A chunk job already
    executing inside a worker can't be aborted; the glue's missing-row
    guards make its completion a harmless no-op."""
    purge_jobs()
    with session_scope() as session:
        deleted = session.query(Recording).delete()
    removed_dirs = delete_all_blobs()
    log.warning("dev cleanup: %d recordings, %d blob dirs", deleted, removed_dirs)
    return CleanupResponse(deleted_recordings=deleted)


@router.get("/recordings/{recording_id}")
def get_recording(recording_id: UUID) -> RecordingDetail:
    with session_scope() as session:
        rec = _get_or_404(session, recording_id)
        return RecordingDetail(**_summary_kwargs(rec), expected_speakers=rec.expected_speakers)


@router.get("/recordings/{recording_id}/timeline")
def get_timeline(recording_id: UUID) -> Timeline:
    with session_scope() as session:
        rec = _get_or_404(session, recording_id)
        if rec.status != RecordingStatus.done.value:
            raise HTTPException(
                status_code=409, detail=f"timeline not ready: status={rec.status}"
            )
        speakers = session.scalars(
            select(Speaker)
            .where(Speaker.recording_id == recording_id)
            .order_by(Speaker.total_speech_s.desc())
        ).all()
        segments = session.scalars(
            select(Segment)
            .where(Segment.recording_id == recording_id)
            .order_by(Segment.start_s)
        ).all()
        return Timeline(
            recording_id=recording_id,
            duration_s=rec.duration_s,
            speakers=[
                TimelineSpeaker(id=s.speaker_id, role=s.role, total_s=s.total_speech_s)
                for s in speakers
            ],
            segments=[
                TimelineSegment(
                    start=s.start_s, end=s.end_s, speaker_id=s.speaker_id, text=s.text
                )
                for s in segments
            ],
        )


@router.get("/recordings/{recording_id}/audio")
def get_audio(recording_id: UUID) -> FileResponse:
    with session_scope() as session:
        rec = _get_or_404(session, recording_id)
        mp3_uri, filename = rec.mp3_uri, rec.filename
    # FileResponse handles HTTP Range natively -> <audio> seeking works
    return FileResponse(mp3_uri, media_type="audio/mpeg", filename=filename)
