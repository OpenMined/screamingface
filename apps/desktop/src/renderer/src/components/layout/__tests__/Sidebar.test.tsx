// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const getStatus = vi.fn(async () => ({}));
const getPollingError = vi.fn(async () => null);
const onStatusChanged = vi.fn(() => () => {});
const onPollingError = vi.fn(() => () => {});
const refresh = vi.fn(async () => ({}));
const logoutAigwSession = vi.fn(async () => undefined);

(window as unknown as { electronAPI: unknown }).electronAPI = {
  backends: {
    getStatus,
    getPollingError,
    onStatusChanged,
    onPollingError,
    refresh,
  },
  aigwSession: {
    logout: logoutAigwSession,
  },
};

import { Sidebar } from '../Sidebar';

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  getStatus.mockClear();
  getStatus.mockResolvedValue({});
  getPollingError.mockClear();
  getPollingError.mockResolvedValue(null);
  onStatusChanged.mockClear();
  onPollingError.mockClear();
  refresh.mockClear();
  refresh.mockResolvedValue({});
  logoutAigwSession.mockClear();
});

describe('Sidebar nav order', () => {
  it('renders core nav items in the expected order', () => {
    const { container } = render(
      <Sidebar currentView="dashboard" onNavigate={vi.fn()} plugins={[]} />,
    );
    const nav = container.querySelector('nav');
    if (!nav) throw new Error('nav not rendered');

    const labels = within(nav)
      .getAllByRole('button')
      .map((button) => button.textContent?.trim());

    expect(labels).toEqual([
      'Dashboard',
      'URL4 Studio',
      'Sessions',
      'Eval Studio',
      'Code Studio',
      'Private Data',
    ]);
  });
});

describe('Sidebar gateway status', () => {
  it('shows external gateway login in the sidebar bottom area', async () => {
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

    const onAigwLoginRequest = vi.fn();
    const { container } = render(
      <Sidebar
        currentView="dashboard"
        onNavigate={vi.fn()}
        plugins={[]}
        onAigwLoginRequest={onAigwLoginRequest}
      />,
    );
    const sidebar = container.querySelector('aside');
    if (!sidebar) throw new Error('sidebar not rendered');

    await within(sidebar).findByText('AIGateway connection');
    fireEvent.click(within(sidebar).getByRole('button', { name: /Sign in/i }));

    expect(onAigwLoginRequest).toHaveBeenCalledOnce();
  });

  it('keeps compact gateway login stacked inside the sidebar', async () => {
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

    const { container } = render(
      <Sidebar currentView="dashboard" onNavigate={vi.fn()} plugins={[]} />,
    );
    const sidebar = container.querySelector('aside');
    if (!sidebar) throw new Error('sidebar not rendered');

    const button = await within(sidebar).findByRole('button', { name: /Sign in/i });
    const wrapper = button.parentElement;

    expect(wrapper?.className).toContain('flex-col');
    expect(wrapper?.className).not.toContain('sm:grid-cols');
  });

  it('does not show gateway login for local managed mode', async () => {
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
      action: 'login_gateway',
    });

    render(<Sidebar currentView="dashboard" onNavigate={vi.fn()} plugins={[]} />);

    await waitFor(() => expect(getStatus).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Sign in/i })).toBeNull();
  });

  it('shows polling failures after repeated backend status errors', async () => {
    getPollingError.mockResolvedValue({
      status: 401,
      code: 'desktop_secret_invalid',
      message: 'Desktop secret invalid',
      consecutiveFailures: 2,
    });

    render(<Sidebar currentView="dashboard" onNavigate={vi.fn()} plugins={[]} />);

    expect(await screen.findByLabelText('Backend polling error')).toBeTruthy();
    expect(screen.getByText('SF status unavailable')).toBeTruthy();
    expect(screen.getByText('HTTP 401: desktop_secret_invalid')).toBeTruthy();
  });

  it('suppresses polling failure banner for one transient failure', async () => {
    getPollingError.mockResolvedValue({
      message: 'timeout',
      consecutiveFailures: 1,
    });

    render(<Sidebar currentView="dashboard" onNavigate={vi.fn()} plugins={[]} />);

    await waitFor(() => expect(getPollingError).toHaveBeenCalled());
    expect(screen.queryByLabelText('Backend polling error')).toBeNull();
  });

  it('renders external gateway URL and logout when connected', async () => {
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
    });

    render(<Sidebar currentView="dashboard" onNavigate={vi.fn()} plugins={[]} />);

    expect(await screen.findByText('Connected to https://gateway.example.com')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Log out/i }));
    await waitFor(() => expect(logoutAigwSession).toHaveBeenCalled());
  });
});
