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

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-neutral-100">{filename}</h2>
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
