// apps/desktop/src/renderer/src/hooks/use-publish-score.ts
//
// Publishes a local eval_run aggregate to the public scoreboard (SF-181 /
// D-SCORE-006). The actual POST (wire-shape build, Idempotency-Key, retries,
// error mapping) runs in the Electron main process via publish:submitScore, so
// it is exempt from renderer CORS (SF-273). This hook just maps the run into the
// IPC request and drives the UI state machine.

import { useCallback, useState } from 'react';
import type { EvalRunDetail } from '@/components/eval/types';
import type { PublishResult, PublishScoreRequest } from '../../../../preload/types';

export type PublishStatus = 'idle' | 'submitting' | 'success' | 'error';

export interface PublishInputs {
  run: EvalRunDetail;
  benchmarkId: string;
  specId: string;
  /** url4 expression to publish — already sanitized if the user chose to. */
  url4Expression: string;
  providers: string[];
  /** null/empty → anonymous. */
  submittedBy: string | null;
}

export type { PublishResult };

/** Flatten the run + form fields into the serializable IPC request. */
function toRequest(inputs: PublishInputs): PublishScoreRequest {
  const { run } = inputs;
  return {
    benchmarkId: inputs.benchmarkId,
    specId: inputs.specId,
    url4Expression: inputs.url4Expression,
    providers: inputs.providers,
    submittedBy: inputs.submittedBy,
    runId: run.id,
    totalQuestions: run.total_questions ?? 0,
    correctQuestions: run.correct_questions ?? 0,
    ranAtLocal: run.finished_at ?? run.started_at,
  };
}

export function usePublishScore() {
  const [status, setStatus] = useState<PublishStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PublishResult | null>(null);

  const publish = useCallback(async (inputs: PublishInputs): Promise<PublishResult | null> => {
    setStatus('submitting');
    setError(null);
    try {
      const outcome = await window.electronAPI.publish.submitScore(toRequest(inputs));
      if (outcome.ok) {
        setResult(outcome.value);
        setStatus('success');
        return outcome.value;
      }
      setError(outcome.error);
      setStatus('error');
      return null;
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  return { publish, status, error, result };
}
