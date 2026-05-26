// apps/desktop/src/renderer/src/hooks/use-eval-runs.ts
import { useCallback, useEffect, useRef, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import type { EvalRunDetail, EvalRunSummary } from '@/components/eval/types';

const POLL_MS = 2000;

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await window.electronAPI.server.fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${url}: ${res.body}`);
  }
  return JSON.parse(res.body) as T;
}

export function useEvalRunsList(limit = 50, offset = 0) {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const [data, setData] = useState<EvalRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    if (!base) return;
    setLoading(true);
    try {
      const runs = await fetchJson<EvalRunSummary[]>(
        `${base}/eval_runs?limit=${limit}&offset=${offset}`,
      );
      setData(runs);
      setError(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [base, limit, offset]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}

export function useEvalRunDetail(runId: string | null) {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const [data, setData] = useState<EvalRunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchOnce = useCallback(async () => {
    if (!base || !runId) return null;
    const run = await fetchJson<EvalRunDetail>(`${base}/eval_runs/${runId}`);
    setData(run);
    setError(null);
    return run;
  }, [base, runId]);

  useEffect(() => {
    setData(null);
    setError(null);
    if (!runId || !base) return;

    let cancelled = false;
    setLoading(true);

    void (async () => {
      try {
        const first = await fetchOnce();
        if (cancelled) return;
        // Start polling only if the run is still in flight.
        if (first && first.status === 'running') {
          pollRef.current = setInterval(async () => {
            try {
              const next = await fetchOnce();
              if (next && next.status !== 'running' && pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
              }
            } catch (e) {
              setError(e as Error);
            }
          }, POLL_MS);
        }
      } catch (e) {
        if (!cancelled) setError(e as Error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [runId, base, fetchOnce]);

  return { data, loading, error };
}
