// @vitest-environment jsdom
import { renderHook, act, waitFor } from '@testing-library/react';
import { it, expect, vi, beforeEach } from 'vitest';

const toast = vi.fn();
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast }) }));
vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({ info: { scheme: 'http', host: 'localhost', port: 8000 } }),
}));

import { useCodeScripts } from '../use-code-scripts';

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
    plugins: ['python-runner'],
    plugin_config: { 'python-runner': { scripts: { check_correct: 'def main():\n    pass' } } },
  };
}

let written: TestConfig[];
const fetchMock = vi.fn();

beforeEach(() => {
  written = [];
  toast.mockClear();
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({ ok: true, status: 200, body: '{}' });
  // @ts-expect-error minimal electronAPI surface
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

function lastScripts(): Record<string, string> {
  return written.at(-1)!.plugin_config['python-runner'].scripts as Record<string, string>;
}

it('loads scripts from the local config', async () => {
  const { result } = renderHook(() => useCodeScripts());
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.scripts).toEqual([
    { name: 'check_correct', source: 'def main():\n    pass' },
  ]);
});

it('createScript writes a new empty-source key', async () => {
  const { result } = renderHook(() => useCodeScripts());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.createScript('helper')).toBe(true);
  });
  expect(Object.keys(lastScripts())).toEqual(['check_correct', 'helper']);
  expect(lastScripts().helper).toBe('');
});

it('rejects an invalid (non-identifier) name without writing', async () => {
  const { result } = renderHook(() => useCodeScripts());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.createScript('bad name!')).toBe(false);
  });
  expect(written).toHaveLength(0);
  expect(toast).toHaveBeenCalled();
});

it('rejects a duplicate name without writing', async () => {
  const { result } = renderHook(() => useCodeScripts());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.createScript('check_correct')).toBe(false);
  });
  expect(written).toHaveLength(0);
});

it('renameScript swaps the key, keeps the source', async () => {
  const { result } = renderHook(() => useCodeScripts());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.renameScript('check_correct', 'grader')).toBe(true);
  });
  expect(Object.keys(lastScripts())).toEqual(['grader']);
  expect(lastScripts().grader).toBe('def main():\n    pass');
});

it('saveSource updates the source', async () => {
  const { result } = renderHook(() => useCodeScripts());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.saveSource('check_correct', 'print(1)')).toBe(true);
  });
  expect(lastScripts().check_correct).toBe('print(1)');
});

it('deleteScript removes the key', async () => {
  const { result } = renderHook(() => useCodeScripts());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    expect(await result.current.deleteScript('check_correct')).toBe(true);
  });
  expect(lastScripts()).toEqual({});
});
