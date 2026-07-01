// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, within, cleanup, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const authenticate = vi.fn();
const authenticateOAuth = vi.fn(async () => ({ kind: 'complete' }));
const authenticateOAuthConnection = vi.fn(async () => ({ kind: 'complete' }));
const getStatus = vi.fn(async () => ({}));
const getPollingError = vi.fn(async () => null);
const onStatusChanged = vi.fn(() => () => {});
const onPollingError = vi.fn(() => () => {});
const onAlert = vi.fn(() => () => {});
const refresh = vi.fn();
const loginGateway = vi.fn(async () => ({ ok: true }));
const logoutGateway = vi.fn(async () => undefined);
const listProfiles = vi.fn(async () => ({ profiles: [] }));
const deleteProfile = vi.fn(async () => ({ ok: true }));
const setProfileApiKey = vi.fn(
  async () => ({ ok: true }) as { ok: boolean; status?: number; message?: string },
);
const getPendingAuthState = vi.fn(async (): Promise<string | null> => null);
const exchangeOAuthCode = vi.fn(async () => ({ ok: true }) as { ok: boolean; message?: string });
const listConnections = vi.fn(async () => ({ connections: [] }));
const createConnectionApiKey = vi.fn(
  async () => ({ ok: true }) as { ok: boolean; status?: number; message?: string },
);
const setConnectionApiKey = vi.fn(
  async () => ({ ok: true }) as { ok: boolean; status?: number; message?: string },
);
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
    getPollingError,
    onStatusChanged,
    onPollingError,
    onAlert,
    refresh,
    loginGateway,
    logoutGateway,
    listProfiles,
    deleteProfile,
    setProfileApiKey,
    getPendingAuthState,
    exchangeOAuthCode,
    listConnections,
    createConnectionApiKey,
    setConnectionApiKey,
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
  getPollingError.mockClear();
  getPollingError.mockResolvedValue(null);
  onPollingError.mockClear();
  listProfiles.mockClear();
  loginGateway.mockClear();
  logoutGateway.mockClear();
  listProfiles.mockResolvedValue({ profiles: [] });
  deleteProfile.mockClear();
  deleteProfile.mockResolvedValue({ ok: true });
  setProfileApiKey.mockClear();
  setProfileApiKey.mockResolvedValue({ ok: true });
  getPendingAuthState.mockClear();
  getPendingAuthState.mockResolvedValue(null);
  exchangeOAuthCode.mockClear();
  exchangeOAuthCode.mockResolvedValue({ ok: true });
  listConnections.mockClear();
  listConnections.mockResolvedValue({ connections: [] });
  createConnectionApiKey.mockClear();
  createConnectionApiKey.mockResolvedValue({ ok: true });
  setConnectionApiKey.mockClear();
  setConnectionApiKey.mockResolvedValue({ ok: true });
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

describe('BackendStatusPanel API-key profiles (SF-244)', () => {
  it('Add Profile with API key auth calls setProfileApiKey and closes the form', async () => {
    render(<BackendStatusPanel />);
    await waitFor(() => expect(listProfiles).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /\+ Add Profile/i }));
    fireEvent.change(screen.getByLabelText(/Authentication type/i), {
      target: { value: 'api_key' },
    });
    fireEvent.change(screen.getByPlaceholderText(/profile name/i), { target: { value: 'keyed' } });
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'sk-ant-api03-test-1234' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Confirm/i }));

    await waitFor(() =>
      expect(setProfileApiKey).toHaveBeenCalledWith('claude', 'keyed', 'sk-ant-api03-test-1234'),
    );
    expect(authenticateOAuth).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByPlaceholderText(/profile name/i)).toBeNull());
  });

  it('rejects a too-short API key without calling the IPC', async () => {
    render(<BackendStatusPanel />);
    await waitFor(() => expect(listProfiles).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /\+ Add Profile/i }));
    fireEvent.change(screen.getByLabelText(/Authentication type/i), {
      target: { value: 'api_key' },
    });
    fireEvent.change(screen.getByPlaceholderText(/profile name/i), { target: { value: 'keyed' } });
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: /Confirm/i }));

    expect(await screen.findByText(/Paste a valid API key/i)).toBeTruthy();
    expect(setProfileApiKey).not.toHaveBeenCalled();
  });

  it('keeps the form open and surfaces the gateway message when the save fails', async () => {
    setProfileApiKey.mockResolvedValue({
      ok: false,
      status: 400,
      message: 'api_key_not_supported',
    });
    render(<BackendStatusPanel />);
    await waitFor(() => expect(listProfiles).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /\+ Add Profile/i }));
    fireEvent.change(screen.getByLabelText(/Authentication type/i), {
      target: { value: 'api_key' },
    });
    fireEvent.change(screen.getByPlaceholderText(/profile name/i), { target: { value: 'keyed' } });
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'sk-proj-test-key-1234' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Confirm/i }));

    expect(await screen.findByText(/api_key_not_supported/i)).toBeTruthy();
    expect(screen.getByPlaceholderText(/profile name/i)).toBeTruthy();
  });

  it('renders the API key badge and Replace key flow instead of Re-authenticate', async () => {
    listProfiles.mockResolvedValue({
      profiles: [
        {
          id: 'anthropic:keyed',
          provider: 'anthropic',
          name: 'keyed',
          state: 'authenticated',
          auth_type: 'api_key',
          account_label: 'API key ····1234',
        },
      ],
    });
    render(<BackendStatusPanel />);
    await screen.findByText('keyed');
    expect(screen.getByText('API key')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Re-authenticate/i })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Replace key/i }));
    fireEvent.change(screen.getByLabelText(/New API key/i), {
      target: { value: 'sk-ant-api03-rotated-9999' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() =>
      expect(setProfileApiKey).toHaveBeenCalledWith('claude', 'keyed', 'sk-ant-api03-rotated-9999'),
    );
  });

  it('shows a load error instead of "No profiles yet." when listProfiles fails', async () => {
    listProfiles.mockResolvedValue({ profiles: [], error: 'gateway_unreachable' });
    render(<BackendStatusPanel />);
    expect(await screen.findByText(/Couldn't load profiles/i)).toBeTruthy();
    expect(screen.queryByText(/No profiles yet\./i)).toBeNull();
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

  const v2WithApiKey = (supports: boolean) => ({
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
        model: 'anthropic/claude-sonnet-4-5',
      },
    },
    provider_auth: {
      providers: {
        claude: {
          provider: 'anthropic',
          profile: 'default',
          state: 'missing_profile',
          supports_api_key: supports,
        },
      },
    },
  });

  it('offers the API-key option when the provider supports it', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    render(<BackendStatusPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '+ Add Connection' }));
    expect(screen.getByLabelText('Authentication type')).toBeTruthy();
  });

  it('hides the API-key option when the provider does not support it', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(false));
    render(<BackendStatusPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '+ Add Connection' }));
    expect(screen.queryByLabelText('Authentication type')).toBeNull();
  });

  it('adding via API key calls createConnectionApiKey and not OAuth', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    render(<BackendStatusPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '+ Add Connection' }));
    fireEvent.change(screen.getByLabelText('Authentication type'), {
      target: { value: 'api_key' },
    });
    fireEvent.change(screen.getByPlaceholderText(/connection label/i), {
      target: { value: 'work' },
    });
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'sk-ant-api03-secret-key' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() =>
      expect(createConnectionApiKey).toHaveBeenCalledWith(
        'claude',
        'work',
        'sk-ant-api03-secret-key',
      ),
    );
    expect(authenticateOAuthConnection).not.toHaveBeenCalled();
  });

  it('renders an api-key connection with a badge and Replace key, no Refresh', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    listConnections.mockResolvedValue({
      connections: [
        {
          id: '00000000-0000-0000-0000-000000000009',
          provider: 'anthropic',
          label: 'work-key',
          status: 'active',
          auth_type: 'api_key',
        },
      ],
    });
    render(<BackendStatusPanel />);
    expect(await screen.findByText('work-key')).toBeTruthy();
    expect(screen.getByText('API key')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Replace key' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Refresh' })).toBeNull();
    // An active api-key connection counts toward the connected indicator.
    expect(await screen.findByText('Connected')).toBeTruthy();
  });

  it('counts active OAuth and API-key connections together as ambiguous', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    listConnections.mockResolvedValue({
      connections: [
        {
          id: '00000000-0000-0000-0000-000000000012',
          provider: 'anthropic',
          label: 'work-oauth',
          status: 'active',
        },
        {
          id: '00000000-0000-0000-0000-000000000013',
          provider: 'anthropic',
          label: 'work-key',
          status: 'active',
          auth_type: 'api_key',
        },
      ],
    });

    render(<BackendStatusPanel />);

    expect(await screen.findByText('work-oauth')).toBeTruthy();
    expect(await screen.findByText('work-key')).toBeTruthy();
    expect(await screen.findByText('Needs Auth')).toBeTruthy();
    expect(screen.queryByText('Connected')).toBeNull();
  });

  it('does not show the OAuth browser-sign-in UI during an api-key save', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    let resolveSave: (v: { ok: boolean }) => void = () => {};
    createConnectionApiKey.mockImplementation(
      () => new Promise((r) => (resolveSave = r as (v: { ok: boolean }) => void)),
    );
    render(<BackendStatusPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '+ Add Connection' }));
    fireEvent.change(screen.getByLabelText('Authentication type'), {
      target: { value: 'api_key' },
    });
    fireEvent.change(screen.getByPlaceholderText(/connection label/i), {
      target: { value: 'work' },
    });
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'sk-ant-api03-secret-key' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    // While the save is in flight the form stays visible ("Saving…") and the
    // OAuth "Waiting for browser sign-in" message must NOT appear (F5).
    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeTruthy();
    expect(screen.queryByText(/Waiting for browser sign-in/i)).toBeNull();
    // Resolve inside act and wait for the post-save state to flush so the test
    // leaves no un-acted update behind (RF2-2).
    await act(async () => {
      resolveSave({ ok: true });
    });
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Saving…' })).toBeNull());
  });

  it('shows Replace key for an errored api-key connection (recovery)', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    listConnections.mockResolvedValue({
      connections: [
        {
          id: '00000000-0000-0000-0000-000000000010',
          provider: 'anthropic',
          label: 'work-key',
          status: 'error',
          auth_type: 'api_key',
          error_message: 'bad key',
        },
      ],
    });
    render(<BackendStatusPanel />);
    expect(await screen.findByText('work-key')).toBeTruthy();
    // Even errored, an api-key connection can be re-keyed in place (RF2-1).
    expect(screen.getByRole('button', { name: 'Replace key' })).toBeTruthy();
  });

  it('shows an inline error if a Replace-key IPC call rejects (defensive, R3-3)', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    listConnections.mockResolvedValue({
      connections: [
        {
          id: '00000000-0000-0000-0000-000000000011',
          provider: 'anthropic',
          label: 'work-key',
          status: 'active',
          auth_type: 'api_key',
        },
      ],
    });
    setConnectionApiKey.mockRejectedValueOnce(new Error('ipc exploded'));
    render(<BackendStatusPanel />);
    await screen.findByText('work-key');
    fireEvent.click(screen.getByRole('button', { name: 'Replace key' }));
    fireEvent.change(screen.getByLabelText('New API key'), {
      target: { value: 'sk-ant-api03-new-key-value' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(/Replace failed/i)).toBeTruthy();
  });

  it('ignores duplicate Replace-key submits while a save is busy', async () => {
    getStatus.mockResolvedValue(v2WithApiKey(true));
    listConnections.mockResolvedValue({
      connections: [
        {
          id: '00000000-0000-0000-0000-000000000014',
          provider: 'anthropic',
          label: 'work-key',
          status: 'active',
          auth_type: 'api_key',
        },
      ],
    });
    let resolveSave: (v: { ok: boolean }) => void = () => {};
    setConnectionApiKey.mockImplementation(
      () =>
        new Promise<{ ok: boolean }>((resolve) => {
          resolveSave = resolve;
        }),
    );

    render(<BackendStatusPanel />);
    await screen.findByText('work-key');
    fireEvent.click(screen.getByRole('button', { name: 'Replace key' }));
    fireEvent.change(screen.getByLabelText('New API key'), {
      target: { value: 'sk-ant-api03-new-key-value' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeTruthy();

    fireEvent.submit(screen.getByRole('form', { name: /Replace API key/i }));

    expect(setConnectionApiKey).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveSave({ ok: true });
    });
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

describe('BackendStatusPanel huggingface (api-key-only, SF-345)', () => {
  const v2Huggingface = () => ({
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
      huggingface: {
        authenticated: false,
        action: 'reauth',
        auth_kind: 'browser',
        model: 'huggingface/deepseek-ai/DeepSeek-R1:novita',
      },
    },
    provider_auth: {
      providers: {
        huggingface: {
          provider: 'huggingface',
          profile: 'default',
          state: 'missing_profile',
          supports_api_key: true,
          supports_oauth: false,
        },
      },
    },
  });

  it('renders the friendly "Hugging Face" display label', async () => {
    getStatus.mockResolvedValue(v2Huggingface());
    render(<BackendStatusPanel />);
    expect(await screen.findByText('Hugging Face')).toBeTruthy();
  });

  it('defaults to API key and hides the OAuth option (no dead-end OAuth start)', async () => {
    getStatus.mockResolvedValue(v2Huggingface());
    render(<BackendStatusPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '+ Add Connection' }));
    // api-key-only: no auth-type dropdown; the API key field is shown directly.
    expect(screen.queryByLabelText('Authentication type')).toBeNull();
    expect(screen.getByLabelText('API key')).toBeTruthy();
  });

  it('creates an api-key connection and never starts OAuth', async () => {
    getStatus.mockResolvedValue(v2Huggingface());
    render(<BackendStatusPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '+ Add Connection' }));
    fireEvent.change(screen.getByPlaceholderText(/connection label/i), {
      target: { value: 'work' },
    });
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'hf_secret_token_123456' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() =>
      expect(createConnectionApiKey).toHaveBeenCalledWith(
        'huggingface',
        'work',
        'hf_secret_token_123456',
      ),
    );
    expect(authenticateOAuthConnection).not.toHaveBeenCalled();
  });
});
