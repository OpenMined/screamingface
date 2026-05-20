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
    fireEvent.change(input, {
      target: {
        value: 'http://localhost:9105/callback?code=pasted-auth-code&state=pending-state-xyz',
      },
    });
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
  it('does not render gateway status inside the Dashboard Backends panel', async () => {
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

    await waitFor(() => expect(listConnections).toHaveBeenCalledWith('claude'));
    expect(screen.queryByText('Connected to https://gateway.example.com')).toBeNull();
  });

  it('suppresses provider rows in external unauthenticated state', async () => {
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

    render(<BackendStatusPanel />);

    await waitFor(() => expect(screen.queryByLabelText('Loading backends')).toBeNull());
    expect(screen.queryByPlaceholderText(/Gateway username/i)).toBeNull();
    expect(screen.queryByText('Claude')).toBeNull();
    expect(listConnections).not.toHaveBeenCalled();
  });

  it('renders active OAuth connections as connected v2 provider rows', async () => {
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
          authenticated: false,
          action: 'reauth',
          auth_kind: 'browser',
          help_text: 'OAuth profile is missing or expired. Click Authenticate to open a browser.',
          model: 'anthropic/claude-sonnet-4-5',
        },
      },
      provider_auth: {
        providers: {
          claude: { provider: 'anthropic', profile: 'default', state: 'missing_profile' },
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
    expect(await screen.findByText('Connected')).toBeTruthy();
    expect(screen.queryByText('Needs Auth')).toBeNull();
    expect(screen.queryByText(/OAuth profile is missing or expired/i)).toBeNull();
    expect(listProfiles).not.toHaveBeenCalled();
  });

  it('keeps v2 provider rows needing auth when connections are not active', async () => {
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
      action: 'login_provider',
      backends: {
        claude: {
          authenticated: false,
          action: 'reauth',
          auth_kind: 'browser',
          help_text: 'OAuth profile is missing or expired. Click Authenticate to open a browser.',
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

    render(<BackendStatusPanel />);

    await waitFor(() => expect(listConnections).toHaveBeenCalledWith('claude'));
    expect(await screen.findByText('Needs Auth')).toBeTruthy();
    expect(screen.queryByText('Connected')).toBeNull();
  });

  it('keeps v2 provider rows needing auth when multiple active connections are ambiguous', async () => {
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
      action: 'login_provider',
      backends: {
        claude: {
          authenticated: false,
          action: 'reauth',
          auth_kind: 'browser',
          error: 'Multiple active OAuth connections exist; select one with auth_profile.',
          model: 'anthropic/claude-sonnet-4-5',
        },
      },
      provider_auth: {
        providers: {
          claude: { provider: 'anthropic', profile: 'default', state: 'missing_profile' },
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
        },
        {
          id: '00000000-0000-0000-0000-000000000002',
          provider: 'anthropic',
          label: 'personal-anthropic',
          status: 'active',
        },
      ],
    });

    render(<BackendStatusPanel />);

    await waitFor(() => expect(listConnections).toHaveBeenCalledWith('claude'));
    expect(await screen.findByText('Needs Auth')).toBeTruthy();
    expect(await screen.findByText(/Multiple active OAuth connections exist/i)).toBeTruthy();
    expect(await screen.findByText('work-anthropic')).toBeTruthy();
    expect(await screen.findByText('personal-anthropic')).toBeTruthy();
  });

  it('downgrades the v2 provider row when the last active connection is deleted', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
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
      action: 'login_provider',
      backends: {
        claude: {
          authenticated: false,
          action: 'reauth',
          auth_kind: 'browser',
          help_text: 'OAuth profile is missing or expired. Click Authenticate to open a browser.',
          model: 'anthropic/claude-sonnet-4-5',
        },
      },
      provider_auth: {
        providers: {
          claude: { provider: 'anthropic', profile: 'default', state: 'missing_profile' },
        },
      },
    });
    listConnections
      .mockResolvedValueOnce({
        connections: [
          {
            id: '00000000-0000-0000-0000-000000000001',
            provider: 'anthropic',
            label: 'work-anthropic',
            status: 'active',
            account: { email: 'dev@example.com' },
          },
        ],
      })
      .mockResolvedValue({ connections: [] });

    render(<BackendStatusPanel />);

    expect(await screen.findByText('Connected')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Delete connection work-anthropic/i }));

    await waitFor(() =>
      expect(deleteConnection).toHaveBeenCalledWith(
        'claude',
        '00000000-0000-0000-0000-000000000001',
      ),
    );
    expect(await screen.findByText('Needs Auth')).toBeTruthy();
    expect(screen.queryByText('Connected')).toBeNull();
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
    expect(screen.queryByRole('button', { name: /\+ Add Connection/i })).toBeNull();
    expect(screen.queryByPlaceholderText(/connection label/i)).toBeNull();
    const input = within(form).getByLabelText(/Connection authorization code/i);
    fireEvent.change(input, {
      target: {
        value: 'http://localhost:9105/callback?code=pasted-auth-code&state=pending-state-xyz',
      },
    });
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
