"""Ingest (architecture §4.1) — synchronous on upload.

mp3 is already on disk when this runs. Steps: decode ONCE to the canonical
16 kHz mono WAV -> measure duration -> plan chunk windows -> create chunk rows
+ set the barrier counter -> COMMIT -> enqueue one job per chunk -> queued.

DB state is committed BEFORE enqueueing so a worker can never race a row that
does not exist yet. If enqueueing dies halfway the recording stays 'queued'
with jobs missing — v1 accepts that (re-upload); do not reorder the two steps.
"""

import logging
import subprocess
import wave
from uuid import UUID

from contracts import RecordingStatus, TranscribeChunkJob
from core.models import Chunk, Recording
from core.session import session_scope
from core.settings import get_settings

from backend.orchestration.queue import enqueue_transcribe_chunk
from backend.storage.blob import mp3_path, wav_path

log = logging.getLogger(__name__)


def plan_chunks(
    duration_s: float, window_s: float, overlap_s: float
) -> list[tuple[int, float, float]]:
    """Windows of `window_s` seconds advancing by `window_s - overlap_s`.

    The last window is clamped to the duration. A window whose non-overlap
    part would start past the end is never created — that audio is already
    fully covered by the previous window.
    """
    if duration_s <= 0:
        raise ValueError(f"non-positive duration: {duration_s}")
    if overlap_s >= window_s:
        raise ValueError(f"overlap {overlap_s} must be < window {window_s}")
    stride = window_s - overlap_s
    chunks: list[tuple[int, float, float]] = []
    index = 0
    while True:
        start = index * stride
        if index > 0 and start + overlap_s >= duration_s:
            break
        end = min(start + window_s, duration_s)
        chunks.append((index, start, end))
        if end >= duration_s:
            break
        index += 1
    return chunks


def decode_to_wav(recording_id: UUID) -> float:
    """ffmpeg decode-once: mp3 -> canonical mono WAV at TARGET_SR. Returns duration."""
    src, dst = mp3_path(recording_id), wav_path(recording_id)
    settings = get_settings()
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-ac", "1", "-ar", str(settings.target_sr), "-vn", str(dst)],
        check=True,
        capture_output=True,
        text=True,
    )
    with wave.open(str(dst), "rb") as w:
        return w.getnframes() / w.getframerate()


def ingest(recording_id: UUID) -> None:
    settings = get_settings()
    duration = decode_to_wav(recording_id)
    windows = plan_chunks(duration, settings.chunk_window_s, settings.chunk_overlap_s)

    with session_scope() as session:
        rec = session.get(Recording, recording_id)
        rec.duration_s = duration
        rec.wav_uri = str(wav_path(recording_id))
        rec.chunks_total = len(windows)
        rec.chunks_remaining = len(windows)
        rec.status = RecordingStatus.queued.value
        for index, start, end in windows:
            session.add(
                Chunk(recording_id=recording_id, chunk_index=index, start_s=start, end_s=end)
            )
        expected = rec.expected_speakers

    for index, start, end in windows:
        enqueue_transcribe_chunk(
            TranscribeChunkJob(
                recording_id=recording_id,
                chunk_index=index,
                wav_uri=str(wav_path(recording_id)),
                start_s=start,
                end_s=end,
                target_sr=settings.target_sr,
                expected_speakers=expected,
            )
        )
    log.info("ingested %s: %.1fs, %d chunks", recording_id, duration, len(windows))
