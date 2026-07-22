import { useEffect, useRef, useState } from "react";

/** Poll `fetcher` every `ms`. Chained setTimeout (not setInterval) so a slow
 * response never overlaps the next request; keeps the last good data across
 * transient errors. */
export function usePoll<T>(fetcher: () => Promise<T>, ms: number) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;

  useEffect(() => {
    let alive = true;
    let timer = 0;
    const tick = async () => {
      try {
        const d = await fetchRef.current();
        if (alive) {
          setData(d);
          setError(undefined);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) timer = window.setTimeout(tick, ms);
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [ms]);

  return { data, error };
}
