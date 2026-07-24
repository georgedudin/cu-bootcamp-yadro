"""FE <-> BE wire types (architecture §5A). All times are seconds, absolute
from the start of the recording."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import RecordingStatus, SpeakerRole


class WireModel(BaseModel):
    """extra='forbid' -> additionalProperties:false in the exported schema."""

    model_config = ConfigDict(extra="forbid")


class Progress(WireModel):
    done_chunks: int
    total_chunks: int


class RecordingCreateResponse(WireModel):
    id: UUID
    status: RecordingStatus


class RecordingSummary(WireModel):
    id: UUID
    filename: str
    uploaded_at: datetime
    duration_s: float | None
    status: RecordingStatus
    progress: Progress
    rtf: float | None = Field(
        default=None,
        description="Real-time factor: processing wall-time / audio duration "
        "(lower is faster). Set once processing finishes; null while it's still "
        "running or if the duration is unknown.",
    )


class RecordingDetail(RecordingSummary):
    expected_speakers: int | None = Field(
        default=None,
        description="Total distinct speakers expected, INCLUDING the teacher "
        "(12 students + 1 teacher -> 13). Optional upload hint.",
    )


class TimelineSpeaker(WireModel):
    id: str = Field(description="Stable global speaker id: 'teacher', 'student_1', ...")
    role: SpeakerRole
    total_s: float


class TimelineSegment(WireModel):
    start: float
    end: float
    speaker_id: str
    text: str


class CleanupResponse(WireModel):
    """Result of the dev-only DELETE /api/recordings wipe."""

    deleted_recordings: int


class Timeline(WireModel):
    """Render payload for the colored player. Gaps between segments are
    silence — the backend emits NO explicit silence rows; the FE paints gaps
    gray. The FE owns the color palette; the backend owns stable ids + roles."""

    recording_id: UUID
    duration_s: float
    speakers: list[TimelineSpeaker]
    segments: list[TimelineSegment]
