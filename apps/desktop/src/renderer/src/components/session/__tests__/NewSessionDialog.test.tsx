// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const serverFetch = vi.fn();
const pickDir = vi.fn();

(window as unknown as { electronAPI: unknown }).electronAPI = {
  server: { fetch: serverFetch },
  session: { pickDir },
};

Object.defineProperty(globalThis, 'crypto', {
  value: { randomUUID: () => 'a36f68dd-e09d-4000-8000-000000000000' },
});

vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({
    info: { scheme: 'http', host: '127.0.0.1', port: 8001 },
  }),
}));

vi.mock('@/components/rjsf-theme', () => ({
  ThemedForm: ({ formData }: { formData: Record<string, unknown> }) => (
    <pre data-testid="form-data">{JSON.stringify(formData)}</pre>
  ),
}));

vi.mock('@/components/rjsf-utils', () => ({ inlineRefs: (schema: unknown) => schema }));

import { NewSessionDialog } from '../NewSessionDialog';

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  serverFetch.mockReset();
  pickDir.mockReset();
  serverFetch.mockImplementation(async (url: string) => {
    if (url.endsWith('/schema')) {
      return {
        ok: true,
        body: JSON.stringify({
          properties: {
            upstream_url: { type: 'string', title: 'Upstream Url' },
            default_backend_path: { type: 'string', title: 'Default Backend Path' },
          },
        }),
      };
    }
    return {
      ok: true,
      body: JSON.stringify({
        upstream_url: 'https://api.openai.com',
        default_backend_path: '/codex',
      }),
    };
  });
});

describe('NewSessionDialog', () => {
  it('loads and launches Codex sessions with codex-frontend settings', async () => {
    const onLaunch = vi.fn();

    render(<NewSessionDialog type="codex" onLaunch={onLaunch} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(serverFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8001/plugins/codex-frontend/schema',
      );
      expect(serverFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8001/plugins/codex-frontend/settings',
      );
    });
    expect((await screen.findByTestId('form-data')).textContent).toContain(
      'https://api.openai.com',
    );

    fireEvent.click(screen.getByRole('button', { name: /Launch Session/i }));

    expect(onLaunch).toHaveBeenCalledWith('codex', '/tmp/sf-a36f68dde09d', {
      'codex-frontend': {
        upstream_url: 'https://api.openai.com',
        default_backend_path: '/codex',
      },
    });
  });
});
