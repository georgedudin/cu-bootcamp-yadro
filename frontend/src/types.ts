// Single import point for wire types. Source of truth is the backend's
// Pydantic models -> contracts/generated/contracts.ts (never edit by hand).
export type {
  CleanupResponse,
  Progress,
  RecordingCreateResponse,
  RecordingDetail,
  RecordingStatus,
  RecordingSummary,
  SpeakerRole,
  Timeline,
  TimelineSegment,
  TimelineSpeaker,
} from "@contracts";
