// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { PublishToLeaderboardDialog } from '../PublishToLeaderboardDialog';
import type { EvalRunDetail } from '../types';

const publishMock = vi.fn();
const toastMock = vi.fn();
const listBenchmarksMock = vi.fn();
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

const QUESTIONS: EvalRunDetail['questions'] = [
  {
    id: 'q-0',
    idx: 0,
    question: '2+2?',
    expected: '4',
    predicted: '4',
    correct: true,
    raw_output: null,
    error: null,
  },
];

function makeRun(overrides: Partial<EvalRunDetail> = {}): EvalRunDetail {
  return {
    id: 'eval-run-1',
    spec_name: 'hle:hle-ensemble-three',
    url4_expression:
      'https://screamingface.ai/honest-agi-live-week-3.eval.jsonl*(/claude($item.question))',
    started_at: '2026-05-04T11:00:00Z',
    finished_at: '2026-05-04T11:55:00Z',
    status: 'done',
    accuracy: 0.81,
    total_questions: 1000,
    correct_questions: 810,
    error: null,
    favorite: false,
    questions: QUESTIONS,
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
  // Default: the derived benchmark (honest-agi-live-week-3) IS registered, so
  // the registry note is "registered" and existing tests are unaffected.
  listBenchmarksMock
    .mockReset()
    .mockResolvedValue([{ id: 'honest-agi-live-week-3', displayName: 'Honest AGI Live week 3' }]);
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    publish: {
      openExternal: vi.fn(async () => {}),
      getContext: vi.fn(),
      listBenchmarks: listBenchmarksMock,
    },
  };
});

describe('PublishToLeaderboardDialog', () => {
  it('auto-derives a read-only benchmark identity from the dataset filename and prefills spec', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    // Spec id still prefilled from the colon-delimited spec_name.
    expect(screen.getByDisplayValue('hle-ensemble-three')).toBeInTheDocument();
    // Benchmark is derived + read-only — no free-text input, label shown instead.
    expect(screen.queryByPlaceholderText('e.g. hle')).not.toBeInTheDocument();
    const identity = await screen.findByTestId('benchmark-identity');
    // Derivation is async (Web Crypto SHA-256 signature) — wait for the resolved
    // label, not just the element, which first renders a "Deriving…" placeholder.
    await waitFor(() => expect(identity).toHaveTextContent('Honest AGI Live week 3'));
    expect(identity).toHaveTextContent('honest-agi-live-week-3');
    expect(screen.getByText(/From honest-agi-live-week-3\.eval\.jsonl/i)).toBeInTheDocument();
  });

  it('marks the derived benchmark as registered when it is in the scoreboard registry', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(await screen.findByText(/registered benchmark/i)).toBeInTheDocument();
    expect(screen.queryByText(/not a registered scoreboard benchmark/i)).not.toBeInTheDocument();
  });

  it('warns (non-blocking) with a closest-match suggestion when the id is not registered', async () => {
    listBenchmarksMock.mockResolvedValue([
      { id: 'honest-agi-live-week-4', displayName: 'Honest AGI Live week 4' },
    ]);
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(await screen.findByText(/not a registered scoreboard benchmark/i)).toBeInTheDocument();
    expect(screen.getByText('honest-agi-live-week-4')).toBeInTheDocument();
    // Advisory only — publish stays enabled (the server is the hard gate).
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
  });

  it('stays silent about registration when the registry is unreachable', async () => {
    listBenchmarksMock.mockResolvedValue(null);
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    const identity = await screen.findByTestId('benchmark-identity');
    await waitFor(() => expect(identity).toHaveTextContent('Honest AGI Live week 3'));
    expect(screen.queryByText(/registered benchmark/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not a registered scoreboard benchmark/i)).not.toBeInTheDocument();
  });

  it('publishes the derived benchmark id + content signature (no manual entry)', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    await screen.findByTestId('benchmark-identity');
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    await waitFor(() => expect(publishMock).toHaveBeenCalledTimes(1));
    const sent = publishMock.mock.calls[0][0];
    expect(sent.benchmarkId).toBe('honest-agi-live-week-3');
    expect(sent.benchmarkSignature).toMatch(/^[0-9a-f]{64}$/);
  });

  it('blocks publish when the run has no graded content to sign the identity', async () => {
    render(
      <PublishToLeaderboardDialog
        run={makeRun({ questions: [] })}
        serverUrl=""
        onClose={vi.fn()}
      />,
    );
    await screen.findByTestId('benchmark-identity');
    expect(await screen.findByText(/no graded content/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
  });

  it('warns about /data refs and publishes the sanitized expression by default', async () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByText(/references local/i)).toBeInTheDocument();
    // sanitize defaults on → the displayed/published expression is redacted.
    expect(screen.getByTestId('url4')).toHaveTextContent('/data/<redacted>');
    await screen.findByTestId('benchmark-identity');
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    expect(publishMock).toHaveBeenCalledTimes(1);
    expect(publishMock.mock.calls[0][0].url4Expression).toContain('/data/<redacted>');
  });

  it('blocks publish if /data refs are neither sanitized nor acknowledged', async () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    await screen.findByTestId('benchmark-identity');
    const sanitize = screen.getByRole('checkbox', { name: /sanitize/i });
    fireEvent.click(sanitize); // uncheck
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /exposes my local data/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
  });

  it('blocks a zero-question run with an explanation (preflight guard)', () => {
    const run = makeRun({ total_questions: 0, correct_questions: 0 });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByText(/no graded questions/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
  });

  it('does not block a normal completed run', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(screen.queryByText(/no graded questions/i)).not.toBeInTheDocument();
    await screen.findByTestId('benchmark-identity');
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
  });

  it('persists the submitter name to sessionStorage on publish', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    await screen.findByTestId('benchmark-identity');
    fireEvent.change(screen.getByPlaceholderText('leave blank for anonymous'), {
      target: { value: 'Ada Lovelace' },
    });
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
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
