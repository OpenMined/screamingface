// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const getStatus = vi.fn(async () => ({}));
const onStatusChanged = vi.fn(() => () => {});
const refresh = vi.fn(async () => ({}));
const loginGateway = vi.fn(async () => ({ ok: true }));
const logoutGateway = vi.fn(async () => undefined);

(window as unknown as { electronAPI: unknown }).electronAPI = {
  backends: {
    getStatus,
    onStatusChanged,
    refresh,
    loginGateway,
    logoutGateway,
  },
};

import { Sidebar } from '../Sidebar';

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  getStatus.mockClear();
  getStatus.mockResolvedValue({});
  onStatusChanged.mockClear();
  refresh.mockClear();
  refresh.mockResolvedValue({});
  loginGateway.mockClear();
  loginGateway.mockResolvedValue({ ok: true });
  logoutGateway.mockClear();
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

    const { container } = render(
      <Sidebar currentView="dashboard" onNavigate={vi.fn()} plugins={[]} />,
    );
    const sidebar = container.querySelector('aside');
    if (!sidebar) throw new Error('sidebar not rendered');

    const username = await within(sidebar).findByPlaceholderText(/Gateway username/i);
    const password = within(sidebar).getByPlaceholderText(/Password/i);
    fireEvent.change(username, { target: { value: 'admin' } });
    fireEvent.change(password, { target: { value: 'secret-password' } });
    fireEvent.click(within(sidebar).getByRole('button', { name: /Sign in/i }));

    await waitFor(() => expect(loginGateway).toHaveBeenCalledWith('admin', 'secret-password'));
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

    const form = (await within(sidebar).findByPlaceholderText(/Gateway username/i)).closest('form');

    expect(form?.className).toContain('flex-col');
    expect(form?.className).not.toContain('sm:grid-cols');
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
    expect(screen.queryByPlaceholderText(/Gateway username/i)).toBeNull();
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
    await waitFor(() => expect(logoutGateway).toHaveBeenCalled());
  });
});
