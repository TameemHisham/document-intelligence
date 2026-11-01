"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** Fetch JSON; re-fetch with reload(). Polls every `pollMs` while `shouldPoll(data)` is true. */
export function useApi<T>(path: string | null, opts: { pollMs?: number; shouldPoll?: (d: T) => boolean } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const { pollMs = 2000, shouldPoll } = opts;

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      try {
        const d = await api<T>(path);
        if (cancelled) return;
        setData(d);
        setError(null);
        if (shouldPoll?.(d)) timer = setTimeout(run, pollMs);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    run();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, pollMs]);

  return { data, error, reload, setData };
}

export const isBusy = (s: string) => s === "pending" || s === "processing";
