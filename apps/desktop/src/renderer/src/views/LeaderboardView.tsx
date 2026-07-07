// apps/desktop/src/renderer/src/views/LeaderboardView.tsx
//
// In-app read-only view of the public scoreboard (OME-321). Net-new screen —
// there was no prior mock-data leaderboard view to replace; the existing
// "Check Leaderboard" button (LeaderboardLink.tsx) still opens the full public
// portal externally and is unaffected by this view.
//
// Deferred (not in this pass): verified-badge visual treatment, client-side
// filtering/sorting beyond the API's accuracy-desc order, spec-history
// drill-in, and comparing a local run against the board (that's OME-318).

import { useEffect, useMemo, useState } from 'react';
import { Combobox } from '@/components/ui/combobox';
import { useKnownBenchmarks } from '@/hooks/use-known-benchmarks';
import { useLeaderboard } from '@/hooks/use-leaderboard';
import { LeaderboardTable } from '@/components/leaderboard/LeaderboardTable';

export function LeaderboardView() {
  const { benchmarks, loading: benchmarksLoading } = useKnownBenchmarks();
  const [benchmarkId, setBenchmarkId] = useState<string | null>(null);

  // Default to the first registered benchmark once the registry loads, so the
  // common single-benchmark case doesn't require an extra click.
  useEffect(() => {
    if (benchmarkId === null && benchmarks && benchmarks.length > 0) {
      setBenchmarkId(benchmarks[0].id);
    }
  }, [benchmarkId, benchmarks]);

  const options = useMemo(
    () => (benchmarks ?? []).map((b) => ({ value: b.id, label: b.displayName })),
    [benchmarks],
  );

  const { data, loading, error, refresh } = useLeaderboard(benchmarkId);

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Leaderboard</h1>
        {benchmarks && benchmarks.length > 0 && benchmarkId !== null && (
          <div className="w-64">
            <Combobox
              value={benchmarkId}
              onChange={setBenchmarkId}
              options={options}
              placeholder="Select a benchmark"
              aria-label="Benchmark"
            />
          </div>
        )}
      </div>

      {benchmarksLoading && (
        <div className="p-6 text-sm text-muted-foreground">Loading benchmarks…</div>
      )}

      {!benchmarksLoading && (!benchmarks || benchmarks.length === 0) && (
        <div className="p-6 text-sm text-muted-foreground">
          No benchmarks are registered on the scoreboard yet.
        </div>
      )}

      {!benchmarksLoading && benchmarks && benchmarks.length > 0 && (
        <div className="rounded-md border border-border">
          {loading && <div className="p-6 text-sm text-muted-foreground">Loading leaderboard…</div>}
          {!loading && error && (
            <div className="flex items-center justify-between gap-3 p-6 text-sm text-destructive">
              <span>Couldn&apos;t load the leaderboard. Check your connection and try again.</span>
              <button
                type="button"
                onClick={refresh}
                className="shrink-0 rounded border border-border px-2 py-1 text-xs text-foreground hover:bg-muted/50"
              >
                Retry
              </button>
            </div>
          )}
          {!loading && !error && data && <LeaderboardTable entries={data.entries} />}
        </div>
      )}
    </div>
  );
}
