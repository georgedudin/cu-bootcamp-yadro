"""Worker-side job handlers (George's code). ALL database access on the ML
side lives here. Friend A's pipeline functions are pure:

    pipeline.transcribe_chunk(TranscribeChunkJob) -> ChunkResult
    pipeline.stitch(results, windows, expected_speakers, duration_s) -> StitchResult

The handlers re-validate queue payloads against the contracts, write results
through the retry-safe barrier, and enqueue stitch exactly-once (at-least-once
under crashes — stitch itself is idempotent, so duplicates are harmless).
"""

import logging
from uuid import UUID

from redis import Redis
from rq import Queue, Retry, get_current_job
from sqlalchemy import select, update

from contracts import (
    ChunkResult,
    ChunkWindow,
    RecordingStatus,
    StitchRecordingJob,
    TranscribeChunkJob,
)
from core.barrier import record_chunk_done
from core.models import CHUNK_DONE, CHUNK_FAILED, Chunk, Recording, Segment, Speaker
from core.session import session_scope
from core.settings import get_settings

from ml import pipeline

log = logging.getLogger(__name__)


def _reduce_queue() -> Queue:
    return Queue("reduce", connection=Redis.from_url(get_settings().redis_url))


def _enqueue_stitch(recording_id: UUID) -> None:
    _reduce_queue().enqueue(
        "ml.glue.stitch_recording",
        StitchRecordingJob(recording_id=recording_id).model_dump(mode="json"),
        retry=Retry(max=2, interval=[10, 30]),
        job_timeout=1800,
    )


def _is_final_attempt() -> bool:
    job = get_current_job()
    return job is None or not job.retries_left


def transcribe_chunk(payload: dict) -> None:
    job = TranscribeChunkJob.model_validate(payload)
    try:
        with session_scope() as session:
            session.execute(
                update(Recording)
                .where(
                    Recording.id == job.recording_id,
                    Recording.status == RecordingStatus.queued.value,
                )
                .values(status=RecordingStatus.processing.value)
            )

        result = pipeline.transcribe_chunk(job)

        with session_scope() as session:
            remaining = record_chunk_done(
                session, job.recording_id, job.chunk_index, result.model_dump(mode="json")
            )
            if remaining == 0:
                session.execute(
                    update(Recording)
                    .where(Recording.id == job.recording_id)
                    .values(status=RecordingStatus.stitching.value)
                )
        if remaining == 0:
            _enqueue_stitch(job.recording_id)
        elif remaining is None:
            # Duplicate delivery (e.g. crash after commit, before ack). If the
            # crash window also swallowed the stitch enqueue, recover it here.
            with session_scope() as session:
                rec = session.get(Recording, job.recording_id)
                # rec is None when the recording was wiped (dev cleanup) mid-job
                stuck = rec is not None and rec.status == RecordingStatus.stitching.value
            if stuck:
                _enqueue_stitch(job.recording_id)
    except Exception:
        _note_chunk_failure(job.recording_id, job.chunk_index)
        raise


def _note_chunk_failure(recording_id: UUID, chunk_index: int) -> None:
    final = _is_final_attempt()
    log.exception(
        "chunk %s/%d failed (%s)", recording_id, chunk_index,
        "final — recording failed" if final else "will retry",
    )
    with session_scope() as session:
        session.execute(
            update(Chunk)
            .where(Chunk.recording_id == recording_id, Chunk.chunk_index == chunk_index)
            .values(retry_count=Chunk.retry_count + 1,
                    **({"status": CHUNK_FAILED} if final else {}))
        )
        if final:
            # v1 failure policy (§10): any chunk exhausting retries fails the recording
            session.execute(
                update(Recording)
                .where(Recording.id == recording_id)
                .values(status=RecordingStatus.failed.value)
            )


def stitch_recording(payload: dict) -> None:
    job = StitchRecordingJob.model_validate(payload)
    try:
        with session_scope() as session:
            rec = session.get(Recording, job.recording_id)
            if rec is None:
                log.warning("stitch for unknown recording %s — skipping", job.recording_id)
                return
            chunks = session.scalars(
                select(Chunk)
                .where(Chunk.recording_id == job.recording_id)
                .order_by(Chunk.chunk_index)
            ).all()
            not_done = [c.chunk_index for c in chunks if c.status != CHUNK_DONE]
            if not_done:
                raise RuntimeError(f"stitch before all chunks done: {not_done}")

            stitched = pipeline.stitch(
                results=[ChunkResult.model_validate(c.result) for c in chunks],
                windows=[
                    ChunkWindow(chunk_index=c.chunk_index, start_s=c.start_s, end_s=c.end_s)
                    for c in chunks
                ],
                expected_speakers=rec.expected_speakers,
                duration_s=rec.duration_s,
            )

            # idempotent: replace previous reduce output wholesale, one transaction
            session.query(Speaker).filter_by(recording_id=job.recording_id).delete()
            session.query(Segment).filter_by(recording_id=job.recording_id).delete()
            session.add_all(
                Speaker(
                    recording_id=job.recording_id, speaker_id=s.id, role=s.role.value,
                    total_speech_s=s.total_s, turn_count=s.turn_count,
                )
                for s in stitched.speakers
            )
            session.add_all(
                Segment(
                    recording_id=job.recording_id, start_s=s.start,
                    end_s=s.end, speaker_id=s.speaker_id, text=s.text,
                )
                for s in stitched.segments
            )
            rec.status = RecordingStatus.done.value
        log.info(
            "stitched %s: %d speakers, %d segments",
            job.recording_id, len(stitched.speakers), len(stitched.segments),
        )
    except Exception:
        if _is_final_attempt():
            with session_scope() as session:
                session.execute(
                    update(Recording)
                    .where(Recording.id == job.recording_id)
                    .values(status=RecordingStatus.failed.value)
                )
        raise
