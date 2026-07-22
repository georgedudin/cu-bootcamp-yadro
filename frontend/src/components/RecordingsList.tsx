import { listRecordings } from "../api";
import { usePoll } from "../hooks/usePoll";
import type { RecordingStatus, RecordingSummary } from "../types";

const STATUS_STYLE: Record<RecordingStatus, string> = {
  uploaded: "bg-neutral-700/60 text-neutral-300",
  queued: "bg-sky-900/60 text-sky-300",
  processing: "bg-amber-900/60 text-amber-300",
  stitching: "bg-violet-900/60 text-violet-300",
  done: "bg-emerald-900/60 text-emerald-300",
  failed: "bg-red-900/60 text-red-300",
};

function fmtDuration(s: number | null): string {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export default function RecordingsList({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (rec: RecordingSummary) => void;
}) {
  const { data: recordings, error } = usePoll(listRecordings, 2500);

  if (!recordings) {
    return (
      <p className="text-sm text-neutral-500">
        {error ? `Can't reach the API: ${error}` : "Loading recordings…"}
      </p>
    );
  }
  if (recordings.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        No recordings yet — upload an mp3 above.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-neutral-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-neutral-900 text-xs uppercase tracking-wide text-neutral-500">
          <tr>
            <th className="px-4 py-2.5">File</th>
            <th className="px-4 py-2.5">Uploaded</th>
            <th className="px-4 py-2.5">Duration</th>
            <th className="px-4 py-2.5">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/70">
          {recordings.map((r) => {
            const clickable = r.status === "done";
            return (
              <tr
                key={r.id}
                onClick={clickable ? () => onSelect(r) : undefined}
                className={
                  (clickable
                    ? "cursor-pointer hover:bg-neutral-900 "
                    : "opacity-80 ") +
                  (r.id === selectedId ? "bg-neutral-900" : "")
                }
              >
                <td className="px-4 py-2.5 font-medium text-neutral-200">
                  {r.filename}
                </td>
                <td className="px-4 py-2.5 text-neutral-400">
                  {new Date(r.uploaded_at).toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-neutral-400">
                  {fmtDuration(r.duration_s)}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[r.status]}`}
                  >
                    {r.status}
                    {r.status === "processing" &&
                      ` ${r.progress.done_chunks}/${r.progress.total_chunks}`}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {error && (
        <p className="border-t border-neutral-800 px-4 py-2 text-xs text-amber-400">
          Refresh failing ({error}) — showing last known state.
        </p>
      )}
    </div>
  );
}
