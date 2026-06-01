// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AigwSessionController } from '@/hooks/use-aigw-session';

const toast = vi.fn();

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast }),
}));

import { AigwLoginDialog } from '../AigwLoginDialog';

const loggedOutSnapshot = {
  hasValidJwt: false,
  jwtExpiresAt: null,
  isLoggedIn: false,
  username: null,
  gatewayUrl: 'https://gateway.example.com',
  rememberAvailable: true,
  secureStorageAvailable: true,
  storedInPlaintext: false,
  lastError: null,
};

function makeSession(overrides: Partial<AigwSessionController> = {}): AigwSessionController {
  return {
    ...loggedOutSnapshot,
    jwt: null,
    loaded: true,
    expiredNonce: 0,
    getJwt: vi.fn(async () => null),
    login: vi.fn(async () => ({
      ok: true,
      snapshot: {
        ...loggedOutSnapshot,
        hasValidJwt: true,
        isLoggedIn: true,
        username: 'admin',
        jwtExpiresAt: '2026-01-01T01:00:00.000Z',
      },
    })),
    logout: vi.fn(async () => loggedOutSnapshot),
    setGatewayUrl: vi.fn(async () => loggedOutSnapshot),
    ...overrides,
  } as AigwSessionController;
}

describe('AigwLoginDialog', () => {
  beforeEach(() => {
    toast.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it('submits credentials, closes, and shows success toast', async () => {
    const session = makeSession();
    const onClose = vi.fn();
    const onSignedIn = vi.fn();

    render(<AigwLoginDialog open session={session} onClose={onClose} onSignedIn={onSignedIn} />);

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test123' } });
    fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }));

    await waitFor(() => {
      expect(session.login).toHaveBeenCalledWith('admin', 'test123', { persist: true });
    });
    expect(onClose).toHaveBeenCalledOnce();
    expect(onSignedIn).toHaveBeenCalledOnce();
    expect(toast).toHaveBeenCalledWith({ variant: 'success', title: 'Signed in to AIGateway' });
  });

  it('shows failed login errors inline', async () => {
    const session = makeSession({
      login: vi.fn(async () => ({
        ok: false,
        message: 'Invalid credentials',
        snapshot: loggedOutSnapshot,
      })),
    });

    render(<AigwLoginDialog open session={session} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }));

    expect(await screen.findByText('Invalid credentials')).toBeTruthy();
  });

  it('emits plaintext persistence warning toast returned by the session service', async () => {
    const session = makeSession({
      login: vi.fn(async () => ({
        ok: true,
        warning: 'AIGateway password was saved in plaintext.',
        snapshot: { ...loggedOutSnapshot, hasValidJwt: true, isLoggedIn: true },
      })),
    });

    render(<AigwLoginDialog open session={session} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test123' } });
    fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        variant: 'warning',
        title: 'Credentials saved without OS encryption',
        description: 'AIGateway password was saved in plaintext.',
      });
    });
  });

  it('labels OS-provided encryption save failures as not saved', async () => {
    const session = makeSession({
      login: vi.fn(async () => ({
        ok: true,
        warning: 'AIGateway password was not saved because OS-provided encryption failed.',
        snapshot: { ...loggedOutSnapshot, hasValidJwt: true, isLoggedIn: true },
      })),
    });

    render(<AigwLoginDialog open session={session} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test123' } });
    fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        variant: 'warning',
        title: 'Password not saved',
        description: 'AIGateway password was not saved because OS-provided encryption failed.',
      });
    });
  });

  it('requires explicit consent before plaintext password storage', async () => {
    const session = makeSession({
      secureStorageAvailable: false,
      login: vi.fn(async () => ({
        ok: true,
        snapshot: { ...loggedOutSnapshot, hasValidJwt: true, isLoggedIn: true },
      })),
    });

    render(<AigwLoginDialog open session={session} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test123' } });
    expect(screen.getByRole('button', { name: /^Sign in$/i })).toHaveProperty('disabled', true);

    fireEvent.click(
      screen.getByLabelText('I understand this will save my AIGateway password in plaintext.'),
    );
    fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }));

    await waitFor(() => {
      expect(session.login).toHaveBeenCalledWith('admin', 'test123', {
        persist: true,
        allowPlaintextStorage: true,
      });
    });
  });

  it('explains session-only login when password saving is off', async () => {
    const session = makeSession();

    render(<AigwLoginDialog open session={session} onClose={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('Save password on this device for future launches'));

    expect(
      screen.getByText(
        'Not saved to disk. Desktop keeps credentials in memory for this app session only.',
      ),
    ).toBeTruthy();
  });
});
