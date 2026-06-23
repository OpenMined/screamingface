// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react';
import { it, expect, vi, afterEach, beforeEach } from 'vitest';

const { getContext, openExternal } = vi.hoisted(() => ({
  getContext: vi.fn(),
  openExternal: vi.fn(),
}));

beforeEach(() => {
  getContext.mockReset().mockResolvedValue({
    scoreboardUrl: 'https://scoreboard.screamingface.ai',
    portalUrl: 'https://portal.test',
    client: { name: 'test', version: '0.0.0', platform: 'test' },
  });
  openExternal.mockReset().mockResolvedValue(undefined);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).electronAPI = { publish: { getContext, openExternal } };
});
afterEach(cleanup);

import { LeaderboardLink } from '../LeaderboardLink';

it('renders the static leaderboard label', () => {
  render(<LeaderboardLink />);
  expect(screen.getByText(/check leaderboard/i)).toBeTruthy();
});

it('resolves the scoreboard URL via the publish context (reused, not hardcoded)', async () => {
  render(<LeaderboardLink />);
  await waitFor(() => expect(getContext).toHaveBeenCalled());
});

it('opens the resolved scoreboard URL through the external IPC, not window.open', async () => {
  render(<LeaderboardLink />);
  const button = screen.getByRole('button', { name: /check leaderboard/i });
  await waitFor(() => expect(button).not.toBeDisabled());
  fireEvent.click(button);
  expect(openExternal).toHaveBeenCalledWith('https://scoreboard.screamingface.ai');
});

it('stays disabled (no-op) until the URL resolves', async () => {
  let resolve!: (value: unknown) => void;
  getContext.mockReturnValue(new Promise((r) => (resolve = r)));
  render(<LeaderboardLink />);
  const button = screen.getByRole('button', { name: /check leaderboard/i });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(openExternal).not.toHaveBeenCalled();
  resolve({
    scoreboardUrl: 'https://scoreboard.screamingface.ai',
    portalUrl: 'https://portal.test',
    client: { name: 'test', version: '0.0.0', platform: 'test' },
  });
  await waitFor(() => expect(button).not.toBeDisabled());
});
