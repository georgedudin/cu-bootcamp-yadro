"""Single source of truth for every wire type in the system.

Pydantic models here -> `make contracts` -> JSON Schema (schema/) -> generated
TypeScript (generated/contracts.ts, imported by the frontend).
"""

from contracts.enums import RecordingStatus, SpeakerRole
from contracts.jobs import (
    EMBEDDING_DIM,
    ChunkResult,
    ChunkSegment,
    ChunkWindow,
    StitchRecordingJob,
    StitchResult,
    StitchSpeaker,
    TranscribeChunkJob,
    Turn,
    Word,
)
from contracts.rest import (
    CleanupResponse,
    Progress,
    RecordingCreateResponse,
    RecordingDetail,
    RecordingSummary,
    Timeline,
    TimelineSegment,
    TimelineSpeaker,
)

CONTRACTS_VERSION = "0.1.0"

__all__ = [
    "CONTRACTS_VERSION",
    "EMBEDDING_DIM",
    "RecordingStatus",
    "SpeakerRole",
    "CleanupResponse",
    "Progress",
    "RecordingCreateResponse",
    "RecordingSummary",
    "RecordingDetail",
    "TimelineSpeaker",
    "TimelineSegment",
    "Timeline",
    "TranscribeChunkJob",
    "Word",
    "ChunkSegment",
    "Turn",
    "ChunkResult",
    "StitchRecordingJob",
    "ChunkWindow",
    "StitchSpeaker",
    "StitchResult",
]
