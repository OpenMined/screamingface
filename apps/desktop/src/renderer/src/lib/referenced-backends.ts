// Which auth-requiring model backends a url4 expression dispatches to, by
// scanning for their call-paths (/claude, /codex, /gemini, /antigravity,
// /huggingface, /ollama). /python,
// /data and /private are intentionally excluded — no credentials / not models.
// Mirrors the server's backend keying (backend_call_paths[0].lstrip('/')).
const AUTH_BACKENDS = [
  'claude',
  'codex',
  'gemini',
  'antigravity',
  'huggingface',
  'ollama',
] as const;
export type BackendName = (typeof AUTH_BACKENDS)[number];

function backendCallPathRe(name: BackendName): RegExp {
  return new RegExp(`(^|[^A-Za-z0-9_./-])/${name}(?:/[a-z0-9][a-z0-9_-]*)?\\s*\\(`);
}

export function referencedBackends(expression: string): BackendName[] {
  const found: BackendName[] = [];
  for (const name of AUTH_BACKENDS) {
    if (backendCallPathRe(name).test(expression)) found.push(name);
  }
  return found;
}
