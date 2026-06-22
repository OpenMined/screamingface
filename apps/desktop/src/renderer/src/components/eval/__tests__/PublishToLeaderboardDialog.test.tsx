// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
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

function benchmarkInput(): HTMLInputElement {
  return screen.getByRole('combobox', { name: 'Benchmark' }) as HTMLInputElement;
}

afterEach(cleanup);

beforeEach(() => {
  publishMock.mockReset();
  toastMock.mockReset();
  hookState.status = 'idle';
  hookState.error = null;
  hookState.result = null;
  window.sessionStorage.clear();
  listBenchmarksMock.mockReset().mockResolvedValue([
    { id: 'hle', displayName: 'News Hallucinations' },
    { id: 'livetruth', displayName: 'News Livetruth' },
  ]);
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    publish: {
      openExternal: vi.fn(async () => {}),
      getContext: vi.fn(),
      listBenchmarks: listBenchmarksMock,
    },
  };
});

describe('PublishToLeaderboardDialog — benchmark combobox', () => {
  it('opens with a blank benchmark and Publish disabled until one is chosen', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(benchmarkInput().value).toBe('');
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    fireEvent.focus(benchmarkInput());
    fireEvent.mouseDown(await screen.findByRole('option', { name: /livetruth/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
  });

  it('filters registered benchmarks and allows free text', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'live' } });
    // Options load async via useKnownBenchmarks — wait for the filtered option.
    expect(await screen.findByRole('option', { name: /livetruth/i })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /^hle/i })).not.toBeInTheDocument();
    fireEvent.change(benchmarkInput(), { target: { value: 'brand-new-2026' } });
    expect(benchmarkInput().value).toBe('brand-new-2026');
  });

  it('shows ✓ registered for a registered value and ⚠ + suggestion for an unknown one', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'hle' } });
    expect(await screen.findByText(/registered benchmark/i)).toBeInTheDocument();
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruh' } });
    expect(await screen.findByText(/not a registered scoreboard benchmark/i)).toBeInTheDocument();
    expect(screen.getByText('livetruth')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled();
  });

  it('stays silent about registration while the registry is unreachable', async () => {
    listBenchmarksMock.mockResolvedValue(null);
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'whatever' } });
    await Promise.resolve();
    expect(screen.queryByText(/registered benchmark/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not a registered scoreboard benchmark/i)).not.toBeInTheDocument();
  });

  it('publishes the chosen benchmark id plus the content signature', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    await waitFor(() => expect(publishMock).toHaveBeenCalledTimes(1));
    const sent = publishMock.mock.calls[0][0];
    expect(sent.benchmarkId).toBe('livetruth');
    expect(sent.benchmarkSignature).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe('PublishToLeaderboardDialog — guards & misc', () => {
  it('prefills spec id from the colon-delimited spec_name', () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByDisplayValue('hle-ensemble-three')).toBeInTheDocument();
  });

  it('blocks a zero-question run with an explanation (preflight guard)', () => {
    render(
      <PublishToLeaderboardDialog
        run={makeRun({ total_questions: 0, correct_questions: 0 })}
        serverUrl=""
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/no graded questions/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
  });

  it('warns about /data refs and publishes the sanitized expression by default', async () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    expect(screen.getByText(/references local/i)).toBeInTheDocument();
    expect(screen.getByTestId('url4')).toHaveTextContent('/data/<redacted>');
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    expect(publishMock).toHaveBeenCalledTimes(1);
    expect(publishMock.mock.calls[0][0].url4Expression).toContain('/data/<redacted>');
  });

  it('blocks publish if /data refs are neither sanitized nor acknowledged', async () => {
    const run = makeRun({ url4_expression: '(/data/abc123)!$prompt' });
    render(<PublishToLeaderboardDialog run={run} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /sanitize/i })); // uncheck
    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /exposes my local data/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /publish/i })).toBeEnabled());
  });

  it('persists the submitter name to sessionStorage on publish', async () => {
    render(<PublishToLeaderboardDialog run={makeRun()} serverUrl="" onClose={vi.fn()} />);
    fireEvent.change(benchmarkInput(), { target: { value: 'livetruth' } });
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
