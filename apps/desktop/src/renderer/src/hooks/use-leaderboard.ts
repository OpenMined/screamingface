// apps/desktop/src/renderer/src/hooks/use-leaderboard.ts
//
// Loads the ranked leaderboard for one benchmark (GET /v1/leaderboard/{id} via
// the main process, exempt from renderer CORS). Re-fetches whenever
// `benchmarkId` changes; `refresh()` re-fetches the current benchmark on
// demand (manual retry — see fetch-leaderboard.ts for why reads don't retry
// automatically the way publish does).
//
// `error` is distinct from "no entries": a benchmark with zero submissions is
// a successful, non-null response with an empty `entries` array.

import { useCallback, useEffect, useState } from 'react';
import type { LeaderboardData } from '../../../../preload/types';

export interface LeaderboardState {
  data: LeaderboardData | null;
  loading: boolean;
  error: boolean;
  refresh: () => void;
}

export function useLeaderboard(benchmarkId: string | null): LeaderboardState {
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (benchmarkId === null) {
      setData(null);
      setLoading(false);
      setError(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(false);
    void window.electronAPI.leaderboard
      .getLeaderboard(benchmarkId)
      .then((result) => {
        if (!active) return;
        setData(result);
        setError(result === null);
      })
      .catch(() => {
        if (active) {
          setData(null);
          setError(true);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [benchmarkId, version]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  return { data, loading, error, refresh };
}
