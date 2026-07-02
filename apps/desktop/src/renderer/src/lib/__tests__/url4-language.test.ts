import { describe, it, expect, vi } from 'vitest';
import { loadBackendAliases, registerUrl4Language, setUrl4SpecNames } from '../url4-language';

type Provider = {
  provideCompletionItems: (
    model: unknown,
    position: unknown,
  ) => { suggestions: Array<{ label: string }> };
};

function makeMonaco() {
  let provider: Provider | null = null;
  const monaco = {
    languages: {
      register: vi.fn(),
      setLanguageConfiguration: vi.fn(),
      setMonarchTokensProvider: vi.fn(),
      registerCompletionItemProvider: vi.fn((_id: string, p: Provider) => {
        provider = p;
      }),
      CompletionItemKind: { Function: 1, Variable: 2, Keyword: 3, Snippet: 4, Reference: 5 },
      CompletionItemInsertTextRule: { InsertAsSnippet: 4 },
    },
  };
  return { monaco, getProvider: () => provider };
}

const model = { getWordUntilPosition: () => ({ startColumn: 1, endColumn: 1 }) };
const position = { lineNumber: 1, column: 1 };

describe('registerUrl4Language', () => {
  it('registers the language + tokenizer and suggests backends/vars/modifiers + specs', () => {
    const { monaco, getProvider } = makeMonaco();
    registerUrl4Language(monaco as never);

    expect(monaco.languages.register).toHaveBeenCalledWith({ id: 'url4' });
    expect(monaco.languages.setMonarchTokensProvider).toHaveBeenCalled();

    const provider = getProvider();
    expect(provider).toBeTruthy();

    setUrl4SpecNames(['hle-ensemble', 'cookbook']);
    const labels = provider!
      .provideCompletionItems(model, position)
      .suggestions.map((s) => s.label);
    expect(labels).toContain('/antigravity');
    expect(labels).toContain('/huggingface');
    expect(labels).toContain('/claude');
    expect(labels).toContain('/python');
    expect(labels).toContain('$prompt');
    expect(labels).toContain('foreach.on_error=collect');
    expect(labels).toContain('hle-ensemble');
  });

  it('is idempotent — a second call does not re-register', () => {
    const { monaco } = makeMonaco();
    registerUrl4Language(monaco as never); // module-level flag already set above
    expect(monaco.languages.register).not.toHaveBeenCalled();
  });

  // registerUrl4Language is idempotent via module state, so only one provider is
  // ever captured per module instance. These tests reset modules to get a fresh
  // registration (and thus a fresh provider) without disturbing the tests above.
  async function freshProvider(): Promise<{
    mod: typeof import('../url4-language');
    provider: Provider;
  }> {
    vi.resetModules();
    const mod = await import('../url4-language');
    const { monaco, getProvider } = makeMonaco();
    mod.registerUrl4Language(monaco as never);
    return { mod, provider: getProvider()! };
  }

  it('suggests dynamically-configured backend profile aliases (SF-346)', async () => {
    const { mod, provider } = await freshProvider();

    mod.setUrl4BackendAliases(['/huggingface/oss20b', '/gemini/flash']);
    const labels = provider.provideCompletionItems(model, position).suggestions.map((s) => s.label);

    expect(labels).toContain('/huggingface/oss20b');
    expect(labels).toContain('/gemini/flash');
    // static backend paths remain (aliases augment, not replace)
    expect(labels).toContain('/huggingface');
  });

  it('keeps static suggestions when no aliases are configured', async () => {
    const { mod, provider } = await freshProvider();

    mod.setUrl4BackendAliases([]);
    const labels = provider.provideCompletionItems(model, position).suggestions.map((s) => s.label);

    expect(labels).toContain('/claude');
    expect(labels).toContain('$prompt');
  });

  it('refreshBackendAliases clears stale aliases when a later successful load returns none (SF-346)', async () => {
    const { mod, provider } = await freshProvider();
    const labels = (): string[] =>
      provider.provideCompletionItems(model, position).suggestions.map((s) => s.label);

    // Server/config A has a profile → alias appears.
    const withProfile = async (url: string): Promise<{ ok: boolean; body: string }> =>
      url.endsWith('/plugins/backend-aliases')
        ? { ok: true, body: JSON.stringify({ aliases: ['/huggingface/oss20b'] }) }
        : { ok: false, body: '' };
    await mod.refreshBackendAliases(withProfile, 'http://x');
    expect(labels()).toContain('/huggingface/oss20b');

    // Config B yields no aliases → the stale one MUST be cleared,
    // not left in the shared module cache (regresses if the setter is guarded by
    // `if (aliases.length)`).
    const noProfiles = async (): Promise<{ ok: boolean; body: string }> => ({
      ok: true,
      body: JSON.stringify({ aliases: [] }),
    });
    await mod.refreshBackendAliases(noProfiles, 'http://x');
    expect(labels()).not.toContain('/huggingface/oss20b');
    expect(labels()).toContain('/huggingface'); // static backends remain
  });

  it('refreshBackendAliases keeps cached aliases when a later load fails', async () => {
    const { mod, provider } = await freshProvider();
    const labels = (): string[] =>
      provider.provideCompletionItems(model, position).suggestions.map((s) => s.label);

    const withProfile = async (): Promise<{ ok: boolean; body: string }> => ({
      ok: true,
      body: JSON.stringify({ aliases: ['/huggingface/oss20b'] }),
    });
    await mod.refreshBackendAliases(withProfile, 'http://x');
    expect(labels()).toContain('/huggingface/oss20b');

    const failed = async (): Promise<{ ok: boolean; body: string }> => ({ ok: false, body: '' });
    await mod.refreshBackendAliases(failed, 'http://x');

    expect(labels()).toContain('/huggingface/oss20b');
  });
});

describe('loadBackendAliases (SF-346)', () => {
  it('loads aliases from the server-owned backend alias endpoint', async () => {
    const fetchFn = vi.fn(async (url: string): Promise<{ ok: boolean; body: string }> => {
      expect(url).toBe('http://localhost:8000/plugins/backend-aliases');
      return {
        ok: true,
        body: JSON.stringify({ aliases: ['/huggingface/oss20b', '/huggingface/llama8b'] }),
      };
    });

    const aliases = await loadBackendAliases(fetchFn, 'http://localhost:8000');

    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect(aliases).toContain('/huggingface/oss20b');
    expect(aliases).toContain('/huggingface/llama8b');
  });

  it('does not hardcode models — an empty server alias list yields no aliases', async () => {
    const fetchFn = async (url: string): Promise<{ ok: boolean; body: string }> => {
      if (url.endsWith('/plugins/backend-aliases')) {
        return { ok: true, body: JSON.stringify({ aliases: [] }) };
      }
      return { ok: false, body: '' };
    };

    expect(await loadBackendAliases(fetchFn, 'http://localhost:8000')).toEqual([]);
  });

  it('ignores inactive/404 plugins and never throws (fail closed)', async () => {
    const fetchFn = async (): Promise<{ ok: boolean; body: string }> => ({ ok: false, body: '' });
    expect(await loadBackendAliases(fetchFn, 'http://localhost:8000')).toEqual([]);
  });
});
