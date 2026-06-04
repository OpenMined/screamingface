// apps/desktop/src/renderer/src/hooks/use-eval-run.ts
import { useCallback, useEffect, useRef, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import type { EvalRunDetail } from '@/components/eval/types';
import type { RunPayload, RunState } from '@/components/run/types';

const POLL_MS = 2000;

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

export function useEvalRun(payload: RunPayload) {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const [run, setRun] = useState<EvalRunDetail | null>(null);
  const [runState, setRunState] = useState<RunState>('idle');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(
    async (runId: string) => {
      if (!base) return;
      const res = await window.electronAPI.server.fetch(`${base}/eval_runs/${runId}`);
      if (!res.ok) return; // 404 before row is created -> keep polling
      const fresh = JSON.parse(res.body) as EvalRunDetail;
      setRun(fresh);
      if (fresh.status === 'done') {
        setRunState('done');
        stop();
      } else if (fresh.status === 'failed') {
        setRunState('failed');
        stop();
      }
    },
    [base, stop],
  );

  const startRun = useCallback(
    (expressionOverride?: string) => {
      if (!base) return;
      const expression = expressionOverride ?? payload.expression;
      // An edited expression is always a new run, so never reuse a pinned
      // (deep-link) runId for it; mint a fresh one.
      const runId =
        expressionOverride !== undefined
          ? crypto.randomUUID()
          : (payload.runId ?? crypto.randomUUID());
      setRun(null);
      setRunState('running');
      // Fire-and-forget: this drives server-side run creation. The main-side
      // fetch times out at 5s but the run continues; polling is the truth.
      void window.electronAPI.server.fetch(`${base}/ensemble?q=${encodeURIComponent(expression)}`, {
        headers: { 'X-SF-Run-Id': runId, 'X-SF-Run-Spec': payload.spec },
      });
      stop();
      pollRef.current = setInterval(() => poll(runId), POLL_MS);
      void poll(runId);
    },
    [base, payload, poll, stop],
  );

  useEffect(() => stop, [stop]);

  return { run, runState, startRun };
}
