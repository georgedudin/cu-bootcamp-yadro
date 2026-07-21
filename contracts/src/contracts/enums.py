"""Shared enums — string-valued so they export as JSON-Schema string enums
and generate TypeScript string-literal unions."""

from enum import Enum


class RecordingStatus(str, Enum):
    """Lifecycle of a recording (architecture §5A state machine).

    uploaded -> queued -> processing -> stitching -> done
    Any stage can end in `failed` (after retries).
    """

    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    stitching = "stitching"
    done = "done"
    failed = "failed"


class SpeakerRole(str, Enum):
    teacher = "teacher"
    student = "student"
