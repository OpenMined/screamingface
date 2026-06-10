// @vitest-environment jsdom
import { renderHook, act, waitFor } from '@testing-library/react';
import { it, expect, vi, beforeEach } from 'vitest';

const toast = vi.fn();
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast }) }));
vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({ info: { scheme: 'http', host: 'localhost', port: 8000 } }),
}));

import { useUrl4Specs } from '../use-url4-specs';

interface TestConfig {
  version: string;
  server: Record<string, unknown>;
  plugins: string[];
  plugin_config: Record<string, Record<string, unknown>>;
}

function baseConfig(): TestConfig {
  return {
    version: '1',
    server: {},
    plugins: ['url4-specs'],
    plugin_config: { 'url4-specs': { specs: { Alpha: { expression: '/claude()!hi' } } } },
  };
}

let written: TestConfig[];
const fetchMock = vi.fn();

beforeEach(() => {
  written = [];
  toast.mockClear();
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({ ok: true, status: 200, body: '{}' });
  // @ts-expect-error minimal electronAPI surface for the hook under test
  window.electronAPI = {
    config: {
      read: vi.fn().mockResolvedValue(baseConfig()),
      write: vi.fn().mockImplementation(async (c: TestConfig) => {
        written.push(c);
      }),
      onChanged: vi.fn().mockReturnValue(() => {}),
    },
    server: { fetch: fetchMock },
  };
});

function lastSpecs(): Record<string, { expression: string }> {
  return written.at(-1)!.plugin_config['url4-specs'].specs as Record<
    string,
    { expression: string }
  >;
}

it('loads specs from the local config', async () => {
  const { result } = renderHook(() => useUrl4Specs());
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.specs).toEqual([{ name: 'Alpha', expression: '/claude()!hi' }]);
});

it('createSpec writes a new empty-expression key, preserving order', async () => {
  const { result } = renderHook(() => useUrl4Specs());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.createSpec('Beta')).toBe(true);
  });
  expect(Object.keys(lastSpecs())).toEqual(['Alpha', 'Beta']);
  expect(lastSpecs().Beta).toEqual({ expression: '' });
});

it('createSpec rejects a duplicate name without writing', async () => {
  const { result } = renderHook(() => useUrl4Specs());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.createSpec('Alpha')).toBe(false);
  });
  expect(written).toHaveLength(0);
  expect(toast).toHaveBeenCalled();
});

it('renameSpec swaps the key in place and keeps the expression', async () => {
  const { result } = renderHook(() => useUrl4Specs());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.renameSpec('Alpha', 'Renamed')).toBe(true);
  });
  expect(Object.keys(lastSpecs())).toEqual(['Renamed']);
  expect(lastSpecs().Renamed.expression).toBe('/claude()!hi');
});

it('deleteSpec removes the key', async () => {
  const { result } = renderHook(() => useUrl4Specs());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.deleteSpec('Alpha')).toBe(true);
  });
  expect(lastSpecs()).toEqual({});
});

it('saveExpression updates only the expression', async () => {
  const { result } = renderHook(() => useUrl4Specs());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.saveExpression('Alpha', '/codex()!new')).toBe(true);
  });
  expect(lastSpecs().Alpha).toEqual({ expression: '/codex()!new' });
});

it('aborts the write when server validation rejects', async () => {
  fetchMock.mockResolvedValue({
    ok: false,
    status: 422,
    body: JSON.stringify({ detail: 'bad spec' }),
  });
  const { result } = renderHook(() => useUrl4Specs());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.createSpec('Beta')).toBe(false);
  });
  expect(written).toHaveLength(0);
  expect(toast).toHaveBeenCalledWith(
    expect.objectContaining({ variant: 'error', description: 'bad spec' }),
  );
});
