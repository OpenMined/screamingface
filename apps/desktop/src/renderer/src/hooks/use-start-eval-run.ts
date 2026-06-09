// apps/desktop/src/renderer/src/hooks/use-start-eval-run.ts
//
// Fire-and-forget start of an eval run: POST /ensemble?q=<expr> with a fresh
// run id. Server-side creates the eval_run row (HOOK_RUN_STARTED) and the run
// continues regardless of this request; the runs list + detail panel poll for
// truth. Returns the new run id so the caller can select it. (SF-248)
import { useCallback } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import type { RunPayload } from '@/components/run/types';

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

export function useStartEvalRun() {
  const { info } = useServerStatus();
  const base = serverBase(info);

  return useCallback(
    (payload: RunPayload): string | null => {
      if (!base) return null;
      const runId = crypto.randomUUID();
      void window.electronAPI.server.fetch(
        `${base}/ensemble?q=${encodeURIComponent(payload.expression)}`,
        { headers: { 'X-SF-Run-Id': runId, 'X-SF-Run-Spec': payload.spec } },
      );
      return runId;
    },
    [base],
  );
}
