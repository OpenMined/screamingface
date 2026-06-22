// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { EvalRunDetail } from '../EvalRunDetail';
import type { EvalRunDetail as EvalRunDetailData } from '../types';

const runData: EvalRunDetailData = {
  id: 'eval-run-1',
  spec_name: 'hle:hle-ensemble-three',
  url4_expression: 'url4://ensemble(claude,codex,gemini)/hle',
  started_at: '2026-05-04T11:00:00Z',
  finished_at: '2026-05-04T11:55:00Z',
  status: 'done',
  accuracy: 0.81,
  total_questions: 1000,
  correct_questions: 810,
  error: null,
  favorite: false,
  questions: [],
};

const deleteRun = vi.fn();
vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({ info: { scheme: 'http', host: 'localhost', port: 8000 } }),
}));
vi.mock('@/hooks/use-eval-runs', () => ({
  useEvalRunDetail: () => ({ data: runData, loading: false, error: null, refresh: vi.fn() }),
}));
vi.mock('@/hooks/use-eval-run-actions', () => ({
  useEvalRunActions: () => ({ deleteRun }),
}));
vi.mock('@/components/Url4Field', () => ({
  Url4Field: ({ value }: { value: string }) => <span data-testid="url4">{value}</span>,
}));
vi.mock('@/components/eval/EvalQuestionsTable', () => ({
  EvalQuestionsTable: () => null,
}));

// Stand in for the lazy monaco popup; surfaces the action props EvalRunDetail wires.
vi.mock('@/components/CodeEditorPopup', () => ({
  default: ({
    onSave,
    confirmLabel,
    secondaryLabel,
    value,
  }: {
    onSave?: (v: string) => void;
    confirmLabel?: string;
    secondaryLabel?: string;
    value: string;
  }) => (
    <div data-testid="code-popup">
      {onSave && <button onClick={() => onSave(value)}>{confirmLabel ?? 'PRIMARY'}</button>}
      {secondaryLabel && <span data-testid="secondary">{secondaryLabel}</span>}
    </div>
  ),
}));

describe('EvalRunDetail edit popup controls', () => {
  beforeEach(() => {
    deleteRun.mockReset();
  });

  it('labels the primary action "Run" with no "Save" or "Re-run" control', async () => {
    const onRunLocally = vi.fn();
    render(<EvalRunDetail runId="eval-run-1" onRunLocally={onRunLocally} />);

    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    await screen.findByTestId('code-popup');

    expect(screen.getByRole('button', { name: 'Run' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('secondary')).not.toBeInTheDocument();
  });

  it('Run starts a fresh run from the edited expression', async () => {
    const onRunLocally = vi.fn();
    render(<EvalRunDetail runId="eval-run-1" onRunLocally={onRunLocally} />);

    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    await screen.findByTestId('code-popup');
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    expect(onRunLocally).toHaveBeenCalledWith({
      spec: runData.spec_name,
      expression: runData.url4_expression,
    });
  });
});
