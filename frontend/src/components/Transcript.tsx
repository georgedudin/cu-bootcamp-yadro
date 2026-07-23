import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import type { TimelineSegment } from "../types";

// Apple Music-style transcript: during playback the active line is auto-scrolled
// toward the middle and neighbours are dimmed. Manual scroll (wheel/touch)
// switches to browse mode — the view stays exactly where the user left it — and
// a pill or 4 s of idle returns to follow mode. Every segment renders into one
// native scroll container (no windowing / no CSS scroll-smooth), so manual
// scrolling is plain and immediate; only the follow auto-scroll animates.
const IDLE_MS = 4000;

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export default function Transcript({
  segments,
  palette,
  currentIndex,
  isActive,
  onSeek,
}: {
  segments: TimelineSegment[];
  palette: Map<string, string>;
  currentIndex: number;
  isActive: boolean;
  onSeek: (t: number) => void;
}) {
  const { t: tr, speaker } = useI18n();
  const [mode, setMode] = useState<"follow" | "browse">("follow");

  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement | null>(null);
  const idleTimer = useRef(0);

  const follow = useCallback(() => {
    clearTimeout(idleTimer.current);
    setMode("follow");
  }, []);

  // Manual scroll intent (wheel/touch — programmatic scrolls fire neither)
  // switches to browse mode; IDLE_MS after the last interaction we snap back.
  useEffect(() => {
    const c = containerRef.current;
    if (!c) return;
    const onIntent = () => {
      setMode("browse");
      clearTimeout(idleTimer.current);
      idleTimer.current = window.setTimeout(follow, IDLE_MS);
    };
    c.addEventListener("wheel", onIntent, { passive: true });
    c.addEventListener("touchmove", onIntent, { passive: true });
    return () => {
      c.removeEventListener("wheel", onIntent);
      c.removeEventListener("touchmove", onIntent);
      clearTimeout(idleTimer.current);
    };
  }, [follow]);

  // Follow mode: keep the active line vertically centered. scrollTo on the
  // container (NOT scrollIntoView — that would also scroll the page). The
  // browser clamps the target near the list ends, so early/final lines settle
  // at the top/bottom instead of forcing a huge empty margin.
  useEffect(() => {
    const c = containerRef.current;
    const el = activeRef.current;
    if (mode !== "follow" || !c || !el) return;
    c.scrollTo({
      top: el.offsetTop - c.clientHeight / 2 + el.clientHeight / 2,
      behavior: "smooth",
    });
  }, [mode, currentIndex]);

  return (
    <div className="relative">
      <div
        ref={containerRef}
        className="h-96 overflow-y-auto rounded-xl border border-neutral-800 bg-neutral-900/40 px-3 py-4"
      >
        {segments.map((seg, idx) => {
          const active = isActive && idx === currentIndex;
          return (
            <button
              key={idx}
              ref={active ? activeRef : undefined}
              type="button"
              onClick={() => {
                onSeek(seg.start);
                follow();
              }}
              className={
                "flex w-full items-baseline gap-3 rounded-lg px-3 py-2 text-left transition-all duration-300 " +
                (active
                  ? "bg-neutral-800/80 text-neutral-50"
                  : "opacity-40 hover:opacity-75")
              }
            >
              <span className="w-10 shrink-0 text-xs leading-6 tabular-nums text-neutral-500">
                {fmt(seg.start)}
              </span>
              <span className="min-w-0 flex-1 break-words leading-6">
                <span className="mr-2 inline-flex items-center gap-1.5 align-baseline text-xs font-medium text-neutral-400">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: palette.get(seg.speaker_id) }}
                  />
                  {speaker(seg.speaker_id)}
                </span>
                <span className={active ? "text-base" : "text-sm"}>
                  {seg.text}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {mode === "browse" && (
        <button
          type="button"
          onClick={follow}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-red-600 px-4 py-1.5 text-xs font-medium text-white shadow-lg hover:bg-red-500"
        >
          {tr("nowPlaying")}
        </button>
      )}
    </div>
  );
}
