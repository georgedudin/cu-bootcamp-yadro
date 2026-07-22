import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { TimelineSegment } from "../types";

// Apple Music-style transcript: the current speech block is centered and
// prominent, neighbors are dimmed, and the view follows playback. Manual
// scrolling switches to browse mode (window slides under the user); a pill or
// 4 s of idle returns to follow mode. Only ~2*WINDOW blocks are ever in the
// DOM, so 1h+ lectures with thousands of segments stay cheap.
const WINDOW = 25;
const SHIFT = 12;
const EDGE_PX = 150;
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
  const [mode, setMode] = useState<"follow" | "browse">("follow");
  const [browseCenter, setBrowseCenter] = useState<number | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement | null>(null);
  const autoScrolling = useRef(false);
  const idleTimer = useRef(0);
  // Set when the window is about to prepend items; consumed by the layout
  // effect to keep the viewport visually still while the slice shifts.
  const pendingAdjust = useRef<{ scrollTop: number; scrollHeight: number } | null>(
    null,
  );

  const center =
    mode === "follow"
      ? Math.max(0, currentIndex)
      : (browseCenter ?? Math.max(0, currentIndex));
  const sliceStart = Math.max(0, center - WINDOW);
  const sliceEnd = Math.min(segments.length, center + WINDOW + 1);

  const follow = useCallback(() => {
    clearTimeout(idleTimer.current);
    setMode("follow");
    setBrowseCenter(null);
  }, []);

  // Manual scroll intent (wheel/touch — programmatic scrolls fire neither).
  useEffect(() => {
    const c = containerRef.current;
    if (!c) return;
    const onIntent = () => {
      setMode("browse");
      setBrowseCenter((b) => b ?? Math.max(0, currentIndex));
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
  }, [currentIndex, follow]);

  // In browse mode, slide the window when the user nears a slice edge.
  useEffect(() => {
    const c = containerRef.current;
    if (!c || mode !== "browse") return;
    const onScroll = () => {
      if (autoScrolling.current) return;
      const bottomGap = c.scrollHeight - c.scrollTop - c.clientHeight;
      if (c.scrollTop < EDGE_PX && sliceStart > 0) {
        pendingAdjust.current = {
          scrollTop: c.scrollTop,
          scrollHeight: c.scrollHeight,
        };
        setBrowseCenter((b) => Math.max(0, (b ?? center) - SHIFT));
      } else if (bottomGap < EDGE_PX && sliceEnd < segments.length) {
        setBrowseCenter((b) =>
          Math.min(segments.length - 1, (b ?? center) + SHIFT),
        );
      }
    };
    c.addEventListener("scroll", onScroll, { passive: true });
    return () => c.removeEventListener("scroll", onScroll);
  }, [mode, sliceStart, sliceEnd, center, segments.length]);

  // Compensate scrollTop after items were prepended, so the view stays put.
  useLayoutEffect(() => {
    const c = containerRef.current;
    const p = pendingAdjust.current;
    if (c && p) {
      c.scrollTop = p.scrollTop + (c.scrollHeight - p.scrollHeight);
      pendingAdjust.current = null;
    }
  }, [sliceStart]);

  // Follow mode: keep the active block vertically centered. scrollTo on the
  // container (NOT scrollIntoView — that would also scroll the page).
  useEffect(() => {
    const c = containerRef.current;
    const el = activeRef.current;
    if (mode !== "follow" || !c || !el) return;
    autoScrolling.current = true;
    c.scrollTo({
      top: el.offsetTop - c.clientHeight / 2 + el.clientHeight / 2,
      behavior: "smooth",
    });
    const done = () => {
      autoScrolling.current = false;
    };
    c.addEventListener("scrollend", done, { once: true });
    const fallback = window.setTimeout(done, 500);
    return () => {
      c.removeEventListener("scrollend", done);
      clearTimeout(fallback);
    };
  }, [mode, currentIndex]);

  return (
    <div className="relative">
      <div
        ref={containerRef}
        className="h-96 overflow-y-auto rounded-xl border border-neutral-800 bg-neutral-900/40 px-3 py-32"
      >
        {segments.slice(sliceStart, sliceEnd).map((seg, i) => {
          const idx = sliceStart + i;
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
                "block w-full rounded-lg px-3 py-2 text-left transition-all duration-300 " +
                (active
                  ? "bg-neutral-800/80 text-neutral-50"
                  : "opacity-40 hover:opacity-75")
              }
            >
              <span className="mr-3 inline-block w-10 text-xs tabular-nums text-neutral-500">
                {fmt(seg.start)}
              </span>
              <span
                className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                style={{ backgroundColor: palette.get(seg.speaker_id) }}
              />
              <span className="mr-3 text-xs font-medium text-neutral-400">
                {seg.speaker_id}
              </span>
              <span className={active ? "text-base" : "text-sm"}>
                {seg.text}
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
          Now playing ↓
        </button>
      )}
    </div>
  );
}
