import type { SpeakerRole, TimelineSpeaker } from "./types";

// The FE owns the palette; the backend owns stable ids + roles
// (docs/architecture.md §5A). Teacher = red; students = dimmed distinct hues,
// keyed by the student_N suffix so the color is stable across reloads and
// independent of array order.
const TEACHER = "#ef4444";
const STUDENTS = [
  "#60a5fa",
  "#34d399",
  "#fbbf24",
  "#a78bfa",
  "#f472b6",
  "#2dd4bf",
  "#fb923c",
  "#a3e635",
];

export const SILENCE = "#262626";

export function speakerColor(id: string, role: SpeakerRole): string {
  if (role === "teacher") return TEACHER;
  const n = Number(id.split("_")[1]);
  const i = Number.isFinite(n)
    ? n - 1
    : [...id].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 0);
  return STUDENTS[((i % STUDENTS.length) + STUDENTS.length) % STUDENTS.length];
}

export function paletteFor(speakers: TimelineSpeaker[]): Map<string, string> {
  return new Map(speakers.map((s) => [s.id, speakerColor(s.id, s.role)]));
}
