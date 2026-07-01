// apps/desktop/src/renderer/src/lib/url4-language.ts
//
// Registers a "url4" Monaco language: a Monarch tokenizer for highlighting and a
// static-list completion provider (SF-249). Validation (squiggles) comes from
// the server's /ensemble/highlight endpoint and is wired per-editor in
// Url4MonacoEditor. Registration is idempotent.
import type { Monaco } from '@monaco-editor/react';

const LANGUAGE_ID = 'url4';

// Backend dispatch paths and well-known variables/modifiers for autocomplete.
const BACKENDS = [
  '/claude',
  '/codex',
  '/gemini',
  '/antigravity',
  '/huggingface',
  '/python',
  '/ollama',
];
const VARIABLES = ['$prompt', '$consensus', '$item.', '$var.'];
const MODIFIERS = ['foreach.concurrency=', 'foreach.on_error=collect'];

// Spec names are dynamic (per server). Url4MonacoEditor refreshes this cache;
// the completion provider reads it. Module-level so the single registered
// provider always sees the latest list.
let specNames: string[] = [];
export function setUrl4SpecNames(names: string[]): void {
  specNames = names;
}

// SF-346: dynamically-configured backend profile aliases (e.g. '/huggingface/oss20b').
// Populated best-effort from server plugin settings via loadBackendAliases(); read by
// the shared completion provider. Module-level so the single provider sees the latest.
let backendAliases: string[] = [];
export function setUrl4BackendAliases(aliases: string[]): void {
  backendAliases = aliases;
}

// Profile-capable backends and the SF plugin(s) that may serve each URL4 path. Only the
// plugin NAMES are fixed (a small known set, like BACKENDS above); the aliases come
// dynamically from each plugin's `profiles` config — individual models are never hardcoded.
const PROFILE_CAPABLE_BACKENDS: Array<{ path: string; plugins: string[] }> = [
  { path: '/claude', plugins: ['aigw-claude-backend', 'claude-backend-api'] },
  { path: '/codex', plugins: ['aigw-codex-backend', 'codex-backend-api'] },
  { path: '/gemini', plugins: ['aigw-gemini-backend', 'gemini-backend-api'] },
  { path: '/antigravity', plugins: ['aigw-antigravity-backend'] },
  { path: '/huggingface', plugins: ['aigw-huggingface-backend'] },
  { path: '/ollama', plugins: ['aigw-ollama-backend', 'ollama-backend-api'] },
];

/**
 * Fetch each profile-capable backend plugin's settings and derive `/path/<alias>`
 * suggestions from its configured `profiles`. Best-effort and fail-closed: inactive or
 * conflicting plugins 404 and are skipped, and any error yields no aliases rather than
 * throwing. `fetchFn` matches window.electronAPI.server.fetch's shape.
 */
export async function loadBackendAliases(
  fetchFn: (url: string) => Promise<{ ok: boolean; body: string }>,
  serverUrl: string,
): Promise<string[]> {
  const out: string[] = [];
  for (const { path, plugins } of PROFILE_CAPABLE_BACKENDS) {
    for (const name of plugins) {
      try {
        const res = await fetchFn(`${serverUrl}/plugins/${name}/settings`);
        if (!res.ok) continue;
        const data = JSON.parse(res.body) as { profiles?: Record<string, unknown> };
        if (data.profiles) {
          for (const alias of Object.keys(data.profiles)) out.push(`${path}/${alias}`);
          break; // one active plugin per path (conflicts guarantee a single owner)
        }
      } catch {
        /* inactive plugin / offline / malformed body — skip */
      }
    }
  }
  return out;
}

/**
 * Load configured backend aliases and publish them to the completion cache.
 * ALWAYS overwrites the cache — including with an empty list — so aliases from a
 * previously-selected server/config are cleared rather than left stale in the
 * module-level cache. (`loadBackendAliases` is fail-closed, returning [] on
 * offline or when no plugin has profiles.) Best-effort: never throws.
 */
export async function refreshBackendAliases(
  fetchFn: (url: string) => Promise<{ ok: boolean; body: string }>,
  serverUrl: string,
): Promise<void> {
  setUrl4BackendAliases(await loadBackendAliases(fetchFn, serverUrl));
}

let registered = false;

export function registerUrl4Language(monaco: Monaco): void {
  if (registered) return;
  registered = true;

  monaco.languages.register({ id: LANGUAGE_ID });

  monaco.languages.setLanguageConfiguration(LANGUAGE_ID, {
    brackets: [['(', ')']],
    autoClosingPairs: [
      { open: '(', close: ')' },
      { open: "'", close: "'" },
    ],
    surroundingPairs: [
      { open: '(', close: ')' },
      { open: "'", close: "'" },
    ],
  });

  monaco.languages.setMonarchTokensProvider(LANGUAGE_ID, {
    tokenizer: {
      root: [
        [/'/, { token: 'string.quote', next: '@string' }],
        [/https?:\/\/[^\s()!,'"]+/, 'type'], // urls
        [/\/[A-Za-z0-9_./-]+/, 'type'], // /data/..., /claude, /python ...
        [/\$[A-Za-z_][\w.]*/, 'variable'], // $item.question, $prompt
        [/\bforeach\.[a-z_]+/, 'keyword'],
        [/\b(consensus|on_error|concurrency|collect|weights)\b/, 'keyword'],
        [/-?\d+\.\d+|-?\d+/, 'number'], // weights / numbers
        [/[()]/, '@brackets'],
        [/[,;:!*=]/, 'delimiter'],
      ],
      string: [
        [/[^']+/, 'string'],
        [/'/, { token: 'string.quote', next: '@pop' }],
      ],
    },
  });

  monaco.languages.registerCompletionItemProvider(LANGUAGE_ID, {
    triggerCharacters: ['/', '$', '.', '('],
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };
      const { CompletionItemKind, CompletionItemInsertTextRule } = monaco.languages;
      const suggestions = [
        ...BACKENDS.map((label) => ({
          label,
          kind: CompletionItemKind.Function,
          insertText: label,
          range,
        })),
        ...backendAliases.map((label) => ({
          label,
          kind: CompletionItemKind.Function,
          insertText: label,
          detail: 'url4 profile alias',
          range,
        })),
        ...VARIABLES.map((label) => ({
          label,
          kind: CompletionItemKind.Variable,
          insertText: label,
          range,
        })),
        ...MODIFIERS.map((label) => ({
          label,
          kind: CompletionItemKind.Keyword,
          insertText: label,
          range,
        })),
        {
          label: 'weight (provider:0.40:)',
          kind: CompletionItemKind.Snippet,
          insertText: '${1:provider}:${2:0.40}:',
          insertTextRules: CompletionItemInsertTextRule.InsertAsSnippet,
          range,
        },
        ...specNames.map((label) => ({
          label,
          kind: CompletionItemKind.Reference,
          insertText: label,
          detail: 'url4 spec',
          range,
        })),
      ];
      return { suggestions };
    },
  });
}
