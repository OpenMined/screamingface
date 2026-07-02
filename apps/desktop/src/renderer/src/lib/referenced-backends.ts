// Which auth-requiring model backends a url4 expression dispatches to, by
// scanning for their call-paths (/claude, /codex, /gemini, /antigravity,
// /huggingface, /ollama). /python,
// /data and /private are intentionally excluded — no credentials / not models.
// Mirrors the server's backend keying (backend_call_paths[0].lstrip('/')).
import { backendCallPathRe } from './backend-call-path';

const AUTH_BACKENDS = [
  'claude',
  'codex',
  'gemini',
  'antigravity',
  'huggingface',
  'ollama',
] as const;
export type BackendName = (typeof AUTH_BACKENDS)[number];

export function referencedBackends(expression: string): BackendName[] {
  const found: BackendName[] = [];
  for (const name of AUTH_BACKENDS) {
    if (backendCallPathRe(name).test(expression)) found.push(name);
  }
  return found;
}
