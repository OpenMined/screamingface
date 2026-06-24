import { describe, it, expect, vi } from 'vitest';
import { registerUrl4Language, setUrl4SpecNames } from '../url4-language';

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
});
