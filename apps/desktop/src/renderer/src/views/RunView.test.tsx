// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';

const startRun = vi.fn();
let mockHook = { run: null as unknown, runState: 'idle' as string, startRun };

vi.mock('@/hooks/use-eval-run', () => ({ useEvalRun: () => mockHook }));
vi.mock('@/components/Url4Viewer', () => ({
  Url4Viewer: ({ expression }: { expression: string }) => <code>{expression}</code>,
}));

afterEach(() => {
  cleanup();
  startRun.mockReset();
  mockHook = { run: null, runState: 'idle', startRun };
});

import { RunView } from './RunView';

const payload = { spec: 'HLE', expression: 'transform(url, intent)' };

it('shows spec, expression, and a Run button that triggers startRun', () => {
  render(<RunView payload={payload} serverUrl="http://x" onViewEvalStudio={vi.fn()} />);
  expect(screen.getByText('HLE')).toBeTruthy();
  expect(screen.getByText('transform(url, intent)')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /run locally/i }));
  expect(startRun).toHaveBeenCalledTimes(1);
});

it('shows result + eval studio link when done', () => {
  mockHook = {
    run: { status: 'done', accuracy: 0.5, correct_questions: 2, total_questions: 4 },
    runState: 'done',
    startRun,
  };
  const onViewEvalStudio = vi.fn();
  render(<RunView payload={payload} serverUrl="http://x" onViewEvalStudio={onViewEvalStudio} />);
  expect(screen.getByText(/50(\.0)?%/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /view in eval studio/i }));
  expect(onViewEvalStudio).toHaveBeenCalled();
});

it('shows error + try again when failed', () => {
  mockHook = {
    run: {
      status: 'failed',
      error: 'boom',
      accuracy: null,
      correct_questions: null,
      total_questions: null,
    },
    runState: 'failed',
    startRun,
  };
  render(<RunView payload={payload} serverUrl="http://x" onViewEvalStudio={vi.fn()} />);
  expect(screen.getByText(/boom/)).toBeTruthy();
  expect(screen.getByRole('button', { name: /run again/i })).toBeTruthy();
});
