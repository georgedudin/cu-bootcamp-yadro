"""BE <-> ML job + result types (architecture §5B), plus the pure-pipeline
seam types the worker glue passes to Friend A's functions.

Friend A's pipeline depends ONLY on this package — never on core/backend.
All times are seconds, absolute from the start of the recording.
"""

from typing import Annotated
from uuid import UUID

from annotated_types import Len
from pydantic import Field

from contracts.enums import SpeakerRole
from contracts.rest import TimelineSegment, TimelineSpeaker, WireModel

EMBEDDING_DIM = 192  # speechbrain ECAPA output size


def _strip_len_constraint(schema: dict) -> None:
    # Keep the exported schema/TS a plain number[] — the 192-length invariant
    # is enforced in Python only (architecture §5B).
    schema.pop("minItems", None)
    schema.pop("maxItems", None)


class TranscribeChunkJob(WireModel):
    """Map job: transcribe + diarize + embed one window of the canonical WAV."""

    recording_id: UUID
    chunk_index: int
    wav_uri: str
    start_s: float
    end_s: float
    target_sr: int
    expected_speakers: int | None = Field(
        default=None,
        description="Total distinct speakers expected, INCLUDING the teacher.",
    )


class Word(WireModel):
    start: float
    end: float
    word: str


class ChunkSegment(WireModel):
    start: float
    end: float
    text: str
    local_speaker: str = Field(
        description="Chunk-LOCAL diarization label (e.g. 'SPEAKER_00'). "
        "Meaningless across chunks — the stitch step maps it to a global id."
    )
    words: list[Word]


class Turn(WireModel):
    start: float
    end: float
    local_speaker: str
    embedding: Annotated[list[float], Len(EMBEDDING_DIM, EMBEDDING_DIM)] = Field(
        description="ECAPA speaker embedding. Exactly 192 floats — enforced in "
        "Python; JSON Schema / TS see a plain number[].",
        json_schema_extra=_strip_len_constraint,
    )


class ChunkResult(WireModel):
    """Output of the map step, upserted keyed by (recording_id, chunk_index)."""

    recording_id: UUID
    chunk_index: int
    segments: list[ChunkSegment]
    turns: list[Turn]


class StitchRecordingJob(WireModel):
    """Reduce job: fired exactly once by the atomic barrier."""

    recording_id: UUID


class ChunkWindow(WireModel):
    """A chunk's window in the recording. The glue passes these to stitch()
    so it can dedupe the overlap seams between adjacent chunks."""

    chunk_index: int
    start_s: float
    end_s: float


class StitchSpeaker(TimelineSpeaker):
    """TimelineSpeaker + bookkeeping the DB keeps but the FE doesn't need."""

    turn_count: int


class StitchResult(WireModel):
    """Output of the reduce step: global speakers + the final timeline segments."""

    speakers: list[StitchSpeaker]
    segments: list[TimelineSegment]


__all__ = [
    "EMBEDDING_DIM",
    "TranscribeChunkJob",
    "Word",
    "ChunkSegment",
    "Turn",
    "ChunkResult",
    "StitchRecordingJob",
    "ChunkWindow",
    "StitchSpeaker",
    "StitchResult",
    "SpeakerRole",
]
