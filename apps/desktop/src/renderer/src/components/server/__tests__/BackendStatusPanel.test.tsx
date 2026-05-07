// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authenticate = vi.fn();
const authenticateOAuth = vi.fn(async () => ({ kind: 'complete' }));
const getStatus = vi.fn(async () => ({}));
const onStatusChanged = vi.fn(() => () => {});
const onAlert = vi.fn(() => () => {});
const refresh = vi.fn();

(window as unknown as { electronAPI: unknown }).electronAPI = {
  backends: { authenticate, authenticateOAuth, getStatus, onStatusChanged, onAlert, refresh },
};

// Stub the toast hook used by the component to avoid pulling in providers.
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

// Stub cn util to a trivial implementation (it's just classname concat).
vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

import { BackendStatusPanel } from '../BackendStatusPanel';

beforeEach(() => {
  authenticate.mockClear();
  authenticateOAuth.mockClear();
  authenticateOAuth.mockImplementation(async () => ({ kind: 'complete' }));
  getStatus.mockResolvedValue({
    claude: {
      authenticated: false,
      action: 'reauth',
      auth_kind: 'browser',
      cli_command: null,
      help_text: 'Sign in via browser',
      model: 'anthropic/claude-sonnet-4-5',
    },
  });
});

describe('BackendStatusPanel auth_kind=browser', () => {
  it('renders an Authenticate button that calls authenticateOAuth', async () => {
    render(<BackendStatusPanel />);
    const btn = await screen.findByRole('button', { name: /Authenticate/i });
    fireEvent.click(btn);
    await waitFor(() => expect(authenticateOAuth).toHaveBeenCalledWith('claude'));
    expect(authenticate).not.toHaveBeenCalled();
  });

  it('shows Waiting... while launcher is in flight', async () => {
    let resolve: (v: unknown) => void = () => {};
    authenticateOAuth.mockImplementationOnce(
      () => new Promise((r) => (resolve = r as (v: unknown) => void)),
    );
    render(<BackendStatusPanel />);
    const btn = await screen.findByRole('button', { name: /Authenticate/i });
    fireEvent.click(btn);
    const waitingNode = await screen.findByText(/Waiting for browser/i);
    expect(waitingNode).toBeTruthy();
    resolve({ kind: 'complete' });
  });
});

describe('BackendStatusPanel auth_kind=cli (regression)', () => {
  it('still calls authenticate(name) for CLI backends', async () => {
    getStatus.mockResolvedValue({
      claude: {
        authenticated: false,
        action: 'reauth',
        auth_kind: 'cli',
        cli_command: 'claude auth login',
        help_text: '...',
        model: 'anthropic/claude-sonnet-4-5',
      },
    });
    render(<BackendStatusPanel />);
    const btn = await screen.findByRole('button', { name: /Re-authenticate/i });
    fireEvent.click(btn);
    await waitFor(() => expect(authenticate).toHaveBeenCalledWith('claude'));
    expect(authenticateOAuth).not.toHaveBeenCalled();
  });
});
