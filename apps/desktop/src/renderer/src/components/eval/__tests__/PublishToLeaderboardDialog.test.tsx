// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { PublishToLeaderboardDialog } from '../PublishToLeaderboardDialog';
import type { EvalRunDetail } from '../types';

const publishMock = vi.fn();
const toastMock = vi.fn();
const hookState: {
  status: 'idle' | 'submitting' | 'success' | 'error';
  error: string | null;
  result: { id: string; benchmarkId: string; specId: string; portalLink: string } | null;
} = { status: 'idle', error: null, result: null };

vi.mock('@/hooks/use-publish-score', () => ({
  usePublishScore: () => ({
    publish: publishMock,
    status: hookState.status,
    error: hookState.error,
    result: hookState.result,
  }),
}));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }));
vi.mock('@/components/Url4Field', () => ({
  Url4Field: ({ value }: { value: string }) => <span data-testid="url4">{value}</span>,
}));

function makeRun(overrides: Partial<EvalRunDetail> = {}): EvalRunDetail {
  return {
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
    ...overrides,
  };
}

beforeEach(() => {
  publishMock.mockReset();
  toastMock.mockReset();
  hookState.status = 'idle';
  hookState.error = null;
  hookState.result = null;
  window.sessionStorage.clear();
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    publish: { openExternal: vi.fn(async () => {}), getContext: vi.fn() },
  };
});

describe('PublishToLeaderboardDialog', () => {
  it('prefills benchmark/spec from a colon-delimited spec_name', () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByPlaceholderText('e.g. hle')).toHaveValue('hle');
    expect(screen.getByDisplayValue('hle-ensemble-three')).toBeInTheDocument();
  });

  it('requires a benchmark id when spec_name has no colon', () => {
    render(
      <PublishToLeaderboardDialog
        run={makeRun({ spec_name: 'hle-claude-single' })}
        serverUrl=""
        onClose={vi.fn()}
      />,
    );
    const benchmark = screen.getByPlaceholderText('e.g. hle');
    expect(benchmark).toHaveValue('');
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    fireEvent.change(benchmark, { target: { value: 'hle' } });
    expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled();
  });

  it('warns about /data refs and publishes the sanitized expression by default', () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByText(/references local/i)).toBeInTheDocument();
    // sanitize defaults on → the displayed/published expression is redacted.
    expect(screen.getByTestId('url4')).toHaveTextContent('/data/<redacted>');
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    expect(publishMock).toHaveBeenCalledTimes(1);
    expect(publishMock.mock.calls[0][0].url4Expression).toContain('/data/<redacted>');
  });

  it('blocks publish if /data refs are neither sanitized nor acknowledged', () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    const sanitize = screen.getByRole('checkbox', { name: /sanitize/i });
    fireEvent.click(sanitize); // uncheck
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /exposes my local data/i }));
    expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled();
  });

  it('blocks a zero-question run with an explanation (preflight guard)', () => {
    const run = makeRun({ total_questions: 0, correct_questions: 0 });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByText(/no graded questions/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
  });

  it('does not block a normal completed run', () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(screen.queryByText(/no graded questions/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled();
  });

  it('persists the submitter name to sessionStorage on publish', () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText('leave blank for anonymous'), {
      target: { value: 'Ada Lovelace' },
    });
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    expect(window.sessionStorage.getItem('sf-leaderboard-submitter')).toBe('Ada Lovelace');
  });

  it('prefills the submitter name from sessionStorage on open', () => {
    window.sessionStorage.setItem('sf-leaderboard-submitter', 'Grace Hopper');
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByPlaceholderText('leave blank for anonymous')).toHaveValue('Grace Hopper');
  });

  it('shows the success state and opens the leaderboard deep link', () => {
    hookState.status = 'success';
    hookState.result = {
      id: 'score-1',
      benchmarkId: 'hle',
      specId: 'hle-ensemble-three',
      portalLink: 'http://localhost:8080/spec.html?benchmark=hle&spec=hle-ensemble-three',
    };
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /view on leaderboard/i }));
    expect(
      (
        window as unknown as {
          electronAPI: { publish: { openExternal: ReturnType<typeof vi.fn> } };
        }
      ).electronAPI.publish.openExternal,
    ).toHaveBeenCalledWith('http://localhost:8080/spec.html?benchmark=hle&spec=hle-ensemble-three');
  });
});
