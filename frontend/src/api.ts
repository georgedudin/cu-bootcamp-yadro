import type {
  RecordingCreateResponse,
  RecordingSummary,
  Timeline,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body — keep the status text
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const listRecordings = () =>
  request<RecordingSummary[]>("/api/recordings");

export const getTimeline = (id: string) =>
  request<Timeline>(`/api/recordings/${id}/timeline`);

export const audioUrl = (id: string) => `/api/recordings/${id}/audio`;

export function uploadRecording(
  file: File,
  expectedSpeakers: number | null,
): Promise<RecordingCreateResponse> {
  const form = new FormData();
  form.append("file", file);
  // Backend validates Form(ge=2); an empty string would 422 — omit when unset.
  if (expectedSpeakers !== null) {
    form.append("expected_speakers", String(expectedSpeakers));
  }
  return request<RecordingCreateResponse>("/api/recordings", {
    method: "POST",
    body: form,
  });
}
