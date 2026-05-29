// apps/desktop/src/renderer/src/components/run/types.ts
// Payload that drives RunView. Today it is constructed from an existing
// eval run row (interim entry); DEMO-018 will deliver it via deep link.
export interface RunPayload {
  spec: string;
  expression: string;
  runId?: string;
}

export type RunState = 'idle' | 'running' | 'done' | 'failed';
