// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';

vi.mock('@/hooks/use-code-scripts', () => ({
  useCodeScripts: () => ({
    scripts: [],
    loading: false,
    error: null,
    createScript: vi.fn(),
    renameScript: vi.fn(),
    deleteScript: vi.fn(),
    saveSource: vi.fn(),
  }),
}));
vi.mock('@/components/code/CodeScriptDetail', () => ({ CodeScriptDetail: () => null }));

afterEach(cleanup);

import { CodeStudioView } from './CodeStudioView';

it('renders header, New script, both pane toggles, and the empty state', () => {
  render(<CodeStudioView />);
  expect(screen.getByText('Code Studio')).toBeTruthy();
  expect(screen.getByRole('button', { name: /new script/i })).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide scripts list/i })).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide script details/i })).toBeTruthy();
  expect(screen.getByText('Select a script to see details')).toBeTruthy();
});
