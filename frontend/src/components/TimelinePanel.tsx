import { useEffect, useMemo, useRef, useState } from "react";
import { audioUrl, getTimeline } from "../api";
import { useI18n } from "../i18n";
import { paletteFor } from "../palette";
import type { Timeline, TimelineSegment } from "../types";
import Track from "./Track";
import Transcript from "./Transcript";

/** Last segment with start <= t, or -1 before the first one. Segments are
 * sorted by start; gaps between them are silence. */
function indexForTime(segs: TimelineSegment[], t: number): number {
  let lo = 0;
  let hi = segs.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (segs[m].start <= t) {
      ans = m;
      lo = m + 1;
    } else {
      hi = m - 1;
    }
  }
  return ans;
}

function fmtTimestamp(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export default function TimelinePanel({
  id,
  filename,
}: {
  id: string;
  filename: string;
}) {
  const { t, speaker } = useI18n();
  const [timeline, setTimeline] = useState<Timeline>();
  const [error, setError] = useState<string>();
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [isActive, setIsActive] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    setTimeline(undefined);
    setError(undefined);
    setCurrentIndex(-1);
    setIsActive(false);
    let alive = true;
    getTimeline(id)
      .then((t) => alive && setTimeline(t))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [id]);

  const palette = useMemo(
    () => paletteFor(timeline?.speakers ?? []),
    [timeline],
  );

  if (error) {
    return (
      <p className="text-sm text-red-400">{t("timelineError", { error })}</p>
    );
  }
  if (!timeline) {
    return (
      <p className="text-sm text-neutral-500">{t("loadingTimeline")}</p>
    );
  }

  const onTimeUpdate = () => {
    const audio = audioRef.current;
    if (!audio) return;
    const t = audio.currentTime;
    const idx = indexForTime(timeline.segments, t);
    setCurrentIndex(idx);
    setIsActive(idx >= 0 && t <= timeline.segments[idx].end);
  };

  const seek = (t: number) => {
    const audio = audioRef.current;
    if (audio) audio.currentTime = t;
  };

  // Build a self-contained Markdown transcript and trigger a client-side
  // download — no backend round-trip; the timeline payload is already loaded.
  const downloadTranscript = () => {
    const lines = [
      `# ${filename}`,
      "",
      `> ${t("mdTranscript")} · ${t("colDuration")}: ` +
        `${fmtTimestamp(timeline.duration_s)} · ` +
        `${t("mdSpeakers")}: ${timeline.speakers.length}`,
      "",
    ];
    for (const seg of timeline.segments) {
      lines.push(
        `**[${fmtTimestamp(seg.start)}] ${speaker(seg.speaker_id)}:** ${seg.text}`,
      );
      lines.push("");
    }
    const blob = new Blob([lines.join("\n")], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename.replace(/\.[^./\\]+$/, "")}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="min-w-0 truncate text-lg font-semibold text-neutral-100">
          {filename}
        </h2>
        <button
          type="button"
          onClick={downloadTranscript}
          title={t("download")}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-xs font-medium text-neutral-200 transition-colors hover:bg-neutral-800"
        >
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-3.5 w-3.5"
            aria-hidden="true"
          >
            <path d="M10 2a.75.75 0 0 1 .75.75v7.19l2.22-2.22a.75.75 0 1 1 1.06 1.06l-3.5 3.5a.75.75 0 0 1-1.06 0l-3.5-3.5a.75.75 0 1 1 1.06-1.06l2.22 2.22V2.75A.75.75 0 0 1 10 2Z" />
            <path d="M3.5 12.75a.75.75 0 0 1 .75.75v1.5c0 .138.112.25.25.25h11a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 15.5 16.5h-11A1.75 1.75 0 0 1 2.75 14.75v-1.5a.75.75 0 0 1 .75-.75Z" />
          </svg>
          {t("download")}
        </button>
      </div>
      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={audioUrl(id)}
        onTimeUpdate={onTimeUpdate}
        className="w-full"
      />
      <Track
        segments={timeline.segments}
        durationS={timeline.duration_s}
        palette={palette}
        audioRef={audioRef}
      />
      <div className="flex flex-wrap gap-3 text-xs text-neutral-300">
        {timeline.speakers.map((s) => (
          <span key={s.id} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: palette.get(s.id) }}
            />
            {speaker(s.id)}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5 text-neutral-500">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-neutral-800" />
          {t("silence")}
        </span>
      </div>
      <Transcript
        segments={timeline.segments}
        palette={palette}
        currentIndex={currentIndex}
        isActive={isActive}
        onSeek={seek}
      />
    </div>
  );
}
