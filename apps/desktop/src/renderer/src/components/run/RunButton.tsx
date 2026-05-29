import type { RunState } from './types';

export function RunButton({ state, onRun }: { state: RunState; onRun: () => void }) {
  const running = state === 'running';
  const label = state === 'done' || state === 'failed' ? 'Run again' : 'Run Locally';
  return (
    <button
      type="button"
      onClick={onRun}
      disabled={running}
      className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
    >
      {running ? 'Running…' : label}
    </button>
  );
}
