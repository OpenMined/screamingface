// apps/desktop/src/renderer/src/hooks/use-known-benchmarks.ts
//
// Loads the canonical benchmarks registered on the scoreboard (GET
// /v1/benchmarks via the main process, exempt from renderer CORS) for pre-flight
// validation of the derived benchmark id in the publish dialog (SF-300 follow-up).
//
// `benchmarks` is null while loading AND when the registry is unreachable —
// callers must gate on `loading` so they don't treat "still fetching" or
// "registry down" as "benchmark not registered".

import { useEffect, useState } from 'react';
import type { KnownBenchmark } from '../../../../preload/types';

export interface KnownBenchmarksState {
  benchmarks: KnownBenchmark[] | null;
  loading: boolean;
}

export function useKnownBenchmarks(): KnownBenchmarksState {
  const [benchmarks, setBenchmarks] = useState<KnownBenchmark[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void window.electronAPI.publish
      .listBenchmarks()
      .then((list) => {
        if (active) setBenchmarks(list);
      })
      .catch(() => {
        if (active) setBenchmarks(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return { benchmarks, loading };
}
