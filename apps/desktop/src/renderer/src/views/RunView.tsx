import { useEvalRun } from '@/hooks/use-eval-run';
import { Url4Viewer } from '@/components/Url4Viewer';
import { RunButton } from '@/components/run/RunButton';
import { RunProgress } from '@/components/run/RunProgress';
import type { RunPayload } from '@/components/run/types';

interface RunViewProps {
  payload: RunPayload;
  serverUrl: string;
  onViewEvalStudio: () => void;
}

export function RunView({ payload, serverUrl, onViewEvalStudio }: RunViewProps) {
  const { run, runState, startRun } = useEvalRun(payload);

  return (
    <div className="flex max-w-3xl flex-col gap-6 p-6">
      <header>
        <div className="text-xs text-muted-foreground">Spec</div>
        <h1 className="text-xl font-semibold">{payload.spec || 'Ad-hoc run'}</h1>
      </header>

      <section>
        <div className="mb-2 text-xs text-muted-foreground">URL4 expression</div>
        <Url4Viewer expression={payload.expression} serverUrl={serverUrl} mode="expanded" />
      </section>

      <section className="flex flex-col gap-3">
        <RunButton state={runState} onRun={() => startRun()} />
        {runState === 'running' && <RunProgress run={run} />}
        {runState === 'done' && run && (
          <div className="flex flex-col gap-2">
            <div className="text-sm">
              Final accuracy:{' '}
              <span className="font-semibold">
                {run.accuracy != null ? `${(run.accuracy * 100).toFixed(1)}%` : 'n/a'}
              </span>{' '}
              ({run.correct_questions ?? 0}/{run.total_questions ?? 0})
            </div>
            <button
              type="button"
              onClick={onViewEvalStudio}
              className="self-start text-sm text-primary underline"
            >
              View in Eval Studio →
            </button>
          </div>
        )}
        {runState === 'failed' && (
          <div className="text-sm text-destructive">
            Run failed: {run?.error ?? 'unknown error'}
          </div>
        )}
      </section>
    </div>
  );
}
