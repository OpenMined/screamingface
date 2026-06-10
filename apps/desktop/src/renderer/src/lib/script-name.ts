// apps/desktop/src/renderer/src/lib/script-name.ts
//
// Python-identifier rule for python-runner script names. Mirrors the server's
// VALID_SCRIPT_NAME (python_runner/plugin.py) — scripts are servable at
// /data/code/<name>.py, so names must be importable Python identifiers.
export const VALID_SCRIPT_NAME = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

export function isValidScriptName(name: string): boolean {
  return VALID_SCRIPT_NAME.test(name);
}

export const SCRIPT_NAME_HINT =
  'Use a Python identifier: start with a letter/underscore; letters, digits, underscores only.';
