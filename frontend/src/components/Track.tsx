import { useEffect, useRef } from "react";
import { SILENCE } from "../palette";
import type { TimelineSegment } from "../types";

/** One horizontal strip: gray = silence, colored blocks = speech segments.
 * Segments render once (static divs); only the playhead moves, via rAF +
 * direct style mutation — no React state at animation frequency. */
export default function Track({
  segments,
  durationS,
  palette,
  audioRef,
}: {
  segments: TimelineSegment[];
  durationS: number;
  palette: Map<string, string>;
  audioRef: React.RefObject<HTMLAudioElement | null>;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const playheadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;
    const step = () => {
      const audio = audioRef.current;
      if (audio && playheadRef.current && durationS > 0) {
        const pct = Math.min(100, (audio.currentTime / durationS) * 100);
        playheadRef.current.style.left = `${pct}%`;
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [audioRef, durationS]);

  const seek = (e: React.MouseEvent) => {
    const track = trackRef.current;
    const audio = audioRef.current;
    if (!track || !audio || durationS <= 0) return;
    const rect = track.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    audio.currentTime = Math.max(0, Math.min(1, ratio)) * durationS;
  };

  return (
    <div
      ref={trackRef}
      onClick={seek}
      title="Click to seek"
      className="relative h-10 w-full cursor-pointer overflow-hidden rounded-md"
      style={{ backgroundColor: SILENCE }}
    >
      {segments.map((s, i) => (
        <div
          key={i}
          className="absolute top-0 h-full"
          style={{
            left: `${(s.start / durationS) * 100}%`,
            width: `${((s.end - s.start) / durationS) * 100}%`,
            backgroundColor: palette.get(s.speaker_id) ?? "#525252",
          }}
        />
      ))}
      <div
        ref={playheadRef}
        className="pointer-events-none absolute top-0 h-full w-0.5 bg-white/90 shadow-[0_0_4px_rgba(255,255,255,0.7)]"
        style={{ left: "0%" }}
      />
    </div>
  );
}
