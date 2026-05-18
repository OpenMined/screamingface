// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const authenticate = vi.fn();
const authenticateOAuth = vi.fn(async () => ({ kind: 'complete' }));
const authenticateOAuthConnection = vi.fn(async () => ({ kind: 'complete' }));
const getStatus = vi.fn(async () => ({}));
const onStatusChanged = vi.fn(() => () => {});
const onAlert = vi.fn(() => () => {});
const refresh = vi.fn();
const loginGateway = vi.fn(async () => ({ ok: true }));
const logoutGateway = vi.fn(async () => undefined);
const listProfiles = vi.fn(async () => ({ profiles: [] }));
const deleteProfile = vi.fn(async () => ({ ok: true }));
const getPendingAuthState = vi.fn(async (): Promise<string | null> => null);
const exchangeOAuthCode = vi.fn(async () => ({ ok: true }) as { ok: boolean; message?: string });
const listConnections = vi.fn(async () => ({ connections: [] }));
const deleteConnection = vi.fn(async () => ({ ok: true }));
const refreshConnection = vi.fn(async () => ({ ok: true }));
const getPendingConnectionAuthState = vi.fn(async (): Promise<string | null> => null);
const exchangeOAuthConnectionCode = vi.fn(
  async () => ({ ok: true }) as { ok: boolean; message?: string },
);

(window as unknown as { electronAPI: unknown }).electronAPI = {
  backends: {
    authenticate,
    authenticateOAuth,
    authenticateOAuthConnection,
    getStatus,
    onStatusChanged,
    onAlert,
    refresh,
    loginGateway,
    logoutGateway,
    listProfiles,
    deleteProfile,
    getPendingAuthState,
    exchangeOAuthCode,
    listConnections,
    deleteConnection,
    refreshConnection,
    getPendingConnectionAuthState,
    exchangeOAuthConnectionCode,
  },
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

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  authenticate.mockClear();
  authenticateOAuth.mockClear();
  authenticateOAuth.mockImplementation(async () => ({ kind: 'complete' }));
  authenticateOAuthConnection.mockClear();
  authenticateOAuthConnection.mockImplementation(async () => ({ kind: 'complete' }));
  listProfiles.mockClear();
  loginGateway.mockClear();
  logoutGateway.mockClear();
  listProfiles.mockResolvedValue({ profiles: [] });
  deleteProfile.mockClear();
  deleteProfile.mockResolvedValue({ ok: true });
  getPendingAuthState.mockClear();
  getPendingAuthState.mockResolvedValue(null);
  exchangeOAuthCode.mockClear();
  exchangeOAuthCode.mockResolvedValue({ ok: true });
  listConnections.mockClear();
  listConnections.mockResolvedValue({ connections: [] });
  deleteConnection.mockClear();
  deleteConnection.mockResolvedValue({ ok: true });
  refreshConnection.mockClear();
  refreshConnection.mockResolvedValue({ ok: true });
  getPendingConnectionAuthState.mockClear();
  getPendingConnectionAuthState.mockResolvedValue(null);
  exchangeOAuthConnectionCode.mockClear();
  exchangeOAuthConnectionCode.mockResolvedValue({ ok: true });
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

describe('BackendStatusPanel auth_kind=browser sub-panel', () => {
  it('renders all profiles returned by listProfiles', async () => {
    listProfiles.mockResolvedValue({
      profiles: [
        { id: 'anthropic:default', provider: 'anthropic', name: 'default', state: 'authenticated' },
        { id: 'anthropic:work', provider: 'anthropic', name: 'work', state: 'pending' },
      ],
    });
    render(<BackendStatusPanel />);
    await waitFor(() => expect(listProfiles).toHaveBeenCalledWith('claude'));
    expect(await screen.findByText('default')).toBeTruthy();
    expect(await screen.findByText('work')).toBeTruthy();
  });

  it('clicking Re-authenticate on a specific profile passes the profile name', async () => {
    listProfiles.mockResolvedValue({
      profiles: [
        { id: 'anthropic:work', provider: 'anthropic', name: 'work', state: 'authenticated' },
      ],
    });
    render(<BackendStatusPanel />);
    const row = await screen.findByText('work');
    const buttons = within(row.closest('div')!.parentElement!).getAllByRole('button', {
      name: /Re-authenticate/i,
    });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(authenticateOAuth).toHaveBeenCalledWith('claude', 'work'));
  });

  it('clicking Delete calls deleteProfile and refreshes', async () => {
    listProfiles
      .mockResolvedValueOnce({
        profiles: [
          { id: 'anthropic:work', provider: 'anthropic', name: 'work', state: 'authenticated' },
        ],
      })
      .mockResolvedValueOnce({ profiles: [] });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<BackendStatusPanel />);
    await screen.findByText('work');
    const deleteBtn = screen.getByRole('button', { name: /Delete profile work/i });
    fireEvent.click(deleteBtn);
    await waitFor(() => expect(deleteProfile).toHaveBeenCalledWith('claude', 'work'));
    await waitFor(() => expect(screen.queryByText('work')).toBeNull());
    confirmSpy.mockRestore();
  });

  it('shows paste-code form when an OAuth flow is in-flight and Submit calls exchangeOAuthCode', async () => {
    listProfiles.mockResolvedValue({
      profiles: [{ id: 'anthropic:work', provider: 'anthropic', name: 'work', state: 'pending' }],
    });
    getPendingAuthState.mockResolvedValue('pending-state-xyz');
    const { container } = render(<BackendStatusPanel />);
    await waitFor(() => expect(getPendingAuthState).toHaveBeenCalledWith('claude', 'work'));
    const form = await waitFor(() => {
      const f = container.querySelector('form[aria-label="Paste authorization code"]');
      if (!f) throw new Error('paste form not yet rendered');
      return f as HTMLFormElement;
    });
    const input = within(form).getByLabelText(/Authorization code/i);
    fireEvent.change(input, { target: { value: 'pasted-auth-code' } });
    fireEvent.click(within(form).getByRole('button', { name: /Submit/i }));
    await waitFor(() =>
      expect(exchangeOAuthCode).toHaveBeenCalledWith('claude', 'pasted-auth-code', 'work'),
    );
  });

  it('Add Profile flow validates and calls authenticateOAuth with new name', async () => {
    render(<BackendStatusPanel />);
    await waitFor(() => expect(listProfiles).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /\+ Add Profile/i }));
    const input = screen.getByPlaceholderText(/profile name/i);
    fireEvent.change(input, { target: { value: 'work' } });
    fireEvent.click(screen.getByRole('button', { name: /Confirm/i }));
    await waitFor(() => expect(authenticateOAuth).toHaveBeenCalledWith('claude', 'work'));
  });
});

describe('BackendStatusPanel v2 gateway status', () => {
  it('renders the gateway URL when connected', async () => {
    getStatus.mockResolvedValue({
      version: 2,
      gateway: {
        mode: 'external',
        managed_by_runner: false,
        reachable: true,
        authenticated: true,
        auth_required: true,
        url: 'https://gateway.example.com',
      },
      action: 'healthy',
      backends: {
        claude: {
          authenticated: true,
          action: 'healthy',
          auth_kind: 'browser',
          model: 'anthropic/claude-sonnet-4-5',
        },
      },
      provider_auth: {
        providers: {
          claude: { provider: 'anthropic', profile: 'default', state: 'authenticated' },
        },
      },
    });

    render(<BackendStatusPanel />);

    expect(await screen.findByText('Connected to https://gateway.example.com')).toBeTruthy();
  });

  it('shows gateway login form before provider rows in external unauthenticated state', async () => {
    getStatus.mockResolvedValue({
      version: 2,
      gateway: {
        mode: 'external',
        managed_by_runner: false,
        reachable: true,
        authenticated: false,
        auth_required: true,
        url: 'https://gateway.example.com',
      },
      action: 'login_gateway',
    });

    render(<BackendStatusPanel />);

    const username = await screen.findByPlaceholderText(/Gateway username/i);
    const password = screen.getByPlaceholderText(/Password/i);
    fireEvent.change(username, { target: { value: 'admin' } });
    fireEvent.change(password, { target: { value: 'secret-password' } });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/i }));
    await waitFor(() => expect(loginGateway).toHaveBeenCalledWith('admin', 'secret-password'));
    expect(screen.queryByText('Claude')).toBeNull();
  });

  it('renders OAuth connections from v2 provider rows', async () => {
    getStatus.mockResolvedValue({
      version: 2,
      gateway: {
        mode: 'local_managed',
        managed_by_runner: true,
        reachable: true,
        authenticated: true,
        auth_required: false,
        url: 'http://127.0.0.1:9105',
      },
      action: 'healthy',
      backends: {
        claude: {
          authenticated: true,
          action: 'healthy',
          auth_kind: 'browser',
          model: 'anthropic/claude-sonnet-4-5',
        },
      },
      provider_auth: {
        providers: {
          claude: { provider: 'anthropic', profile: 'default', state: 'authenticated' },
        },
      },
    });
    listConnections.mockResolvedValue({
      connections: [
        {
          id: '00000000-0000-0000-0000-000000000001',
          provider: 'anthropic',
          label: 'work-anthropic',
          status: 'active',
          account: { email: 'dev@example.com' },
        },
      ],
    });

    render(<BackendStatusPanel />);

    await waitFor(() => expect(listConnections).toHaveBeenCalledWith('claude'));
    expect(await screen.findByText('work-anthropic')).toBeTruthy();
    expect(await screen.findByText('dev@example.com')).toBeTruthy();
    expect(listProfiles).not.toHaveBeenCalled();
  });

  it('Add Connection validates anthropic labels and starts connection OAuth', async () => {
    getStatus.mockResolvedValue({
      version: 2,
      gateway: {
        mode: 'local_managed',
        managed_by_runner: true,
        reachable: true,
        authenticated: true,
        auth_required: false,
        url: 'http://127.0.0.1:9105',
      },
      action: 'healthy',
      backends: {
        claude: {
          authenticated: false,
          action: 'reauth',
          auth_kind: 'browser',
          model: 'anthropic/claude-sonnet-4-5',
        },
      },
      provider_auth: {
        providers: {
          claude: { provider: 'anthropic', profile: 'default', state: 'missing_profile' },
        },
      },
    });
    authenticateOAuthConnection.mockResolvedValue({
      kind: 'complete',
      connection: {
        id: '00000000-0000-0000-0000-000000000001',
        provider: 'anthropic',
        label: 'work-anthropic',
        status: 'active',
      },
    });

    render(<BackendStatusPanel />);
    await waitFor(() => expect(listConnections).toHaveBeenCalledWith('claude'));
    fireEvent.click(screen.getByRole('button', { name: /\+ Add Connection/i }));
    fireEvent.click(screen.getByRole('button', { name: /Start/i }));
    expect(await screen.findByText('Connection label is required')).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText(/connection label/i), {
      target: { value: 'work-anthropic' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Start/i }));

    await waitFor(() =>
      expect(authenticateOAuthConnection).toHaveBeenCalledWith('claude', 'work-anthropic'),
    );
    expect(await screen.findByText('Connected work-anthropic.')).toBeTruthy();
  });

  it('shows connection paste-code form and submits pasted OAuth code', async () => {
    getStatus.mockResolvedValue({
      version: 2,
      gateway: {
        mode: 'local_managed',
        managed_by_runner: true,
        reachable: true,
        authenticated: true,
        auth_required: false,
        url: 'http://127.0.0.1:9105',
      },
      action: 'healthy',
      backends: {
        claude: {
          authenticated: false,
          action: 'reauth',
          auth_kind: 'browser',
          model: 'anthropic/claude-sonnet-4-5',
        },
      },
      provider_auth: {
        providers: {
          claude: { provider: 'anthropic', profile: 'default', state: 'pending' },
        },
      },
    });
    listConnections.mockResolvedValue({
      connections: [
        {
          id: '00000000-0000-0000-0000-000000000001',
          provider: 'anthropic',
          label: 'work-anthropic',
          status: 'pending',
        },
      ],
    });
    getPendingConnectionAuthState.mockResolvedValue('pending-state-xyz');

    const { container } = render(<BackendStatusPanel />);
    await waitFor(() =>
      expect(getPendingConnectionAuthState).toHaveBeenCalledWith(
        'claude',
        '00000000-0000-0000-0000-000000000001',
      ),
    );
    const form = await waitFor(() => {
      const f = container.querySelector('form[aria-label="Paste connection authorization code"]');
      if (!f) throw new Error('connection paste form not yet rendered');
      return f as HTMLFormElement;
    });
    const input = within(form).getByLabelText(/Connection authorization code/i);
    fireEvent.change(input, { target: { value: 'pasted-auth-code' } });
    fireEvent.click(within(form).getByRole('button', { name: /Submit/i }));

    await waitFor(() =>
      expect(exchangeOAuthConnectionCode).toHaveBeenCalledWith(
        'claude',
        '00000000-0000-0000-0000-000000000001',
        'pasted-auth-code',
      ),
    );
  });
});

describe('BackendStatusPanel auth_kind=cli (regression)', () => {
  it('still calls authenticate(name) for CLI backends via top-level button', async () => {
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
    // CLI backends do not invoke listProfiles (no sub-panel).
    expect(listProfiles).not.toHaveBeenCalled();
  });
});
