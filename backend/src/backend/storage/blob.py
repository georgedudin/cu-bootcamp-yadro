"""Blob layout: one directory per recording on the shared volume.

    {BLOB_DIR}/{recording_id}/audio.mp3   original upload (kept for playback)
    {BLOB_DIR}/{recording_id}/audio.wav   canonical 16 kHz mono WAV (workers read this)
"""

import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from core.settings import get_settings


def recording_dir(recording_id: UUID) -> Path:
    return Path(get_settings().blob_dir) / str(recording_id)


def mp3_path(recording_id: UUID) -> Path:
    return recording_dir(recording_id) / "audio.mp3"


def wav_path(recording_id: UUID) -> Path:
    return recording_dir(recording_id) / "audio.wav"


def save_mp3(recording_id: UUID, stream: BinaryIO) -> Path:
    """Stream the upload to disk — the file is never held in memory."""
    target = mp3_path(recording_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        shutil.copyfileobj(stream, out, length=1024 * 1024)
    return target


def delete_all_blobs() -> int:
    """Dev cleanup: remove every per-recording directory. Returns the count.
    Also catches orphan dirs whose DB rows are already gone."""
    base = Path(get_settings().blob_dir)
    if not base.exists():
        return 0
    removed = 0
    for child in base.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed
