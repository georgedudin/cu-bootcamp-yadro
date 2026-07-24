import { useI18n } from "../i18n";
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

// Real-time factor: only set once processing finished (null while running).
function fmtRtf(rtf: number | null | undefined): string {
  if (rtf == null) return "—";
  return `${rtf.toFixed(2)}×`;
}

export default function RecordingsList({
  recordings,
  error,
  selectedId,
  onSelect,
}: {
  recordings: RecordingSummary[];
  error?: string;
  selectedId: string | null;
  onSelect: (rec: RecordingSummary) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="overflow-x-auto rounded-xl border border-neutral-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-neutral-900 text-xs uppercase tracking-wide text-neutral-500">
          <tr>
            <th className="px-4 py-2.5">{t("colFile")}</th>
            <th className="px-4 py-2.5">{t("colUploaded")}</th>
            <th className="px-4 py-2.5">{t("colDuration")}</th>
            <th className="px-4 py-2.5" title={t("colRtfHint")}>
              {t("colRtf")}
            </th>
            <th className="px-4 py-2.5">{t("colStatus")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/70">
          {recordings.map((r, i) => {
            const clickable = r.status === "done";
            return (
              <tr
                key={r.id}
                onClick={clickable ? () => onSelect(r) : undefined}
                style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}
                className={
                  "animate-fade-in-up transition-colors " +
                  (clickable
                    ? "cursor-pointer hover:bg-neutral-900 "
                    : "opacity-80 ") +
                  (r.id === selectedId ? "bg-neutral-900" : "")
                }
              >
                <td className="px-4 py-2.5 font-medium text-neutral-200">
                  {r.filename}
                </td>
                <td className="whitespace-nowrap px-4 py-2.5 tabular-nums text-neutral-400">
                  {new Date(r.uploaded_at).toLocaleString()}
                </td>
                <td className="whitespace-nowrap px-4 py-2.5 tabular-nums text-neutral-400">
                  {fmtDuration(r.duration_s)}
                </td>
                <td className="whitespace-nowrap px-4 py-2.5 tabular-nums text-neutral-400">
                  {fmtRtf(r.rtf)}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium tabular-nums ${STATUS_STYLE[r.status]}`}
                  >
                    {t(`st_${r.status}`)}
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
          {t("refreshFailing", { error })}
        </p>
      )}
    </div>
  );
}
