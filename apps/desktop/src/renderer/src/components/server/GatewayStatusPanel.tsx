import { useState } from 'react';
import type { BackendStatusV2 } from '../../../../preload/types';

export function GatewayStatusPanel({
  status,
  onChanged,
  compact = false,
}: {
  status: BackendStatusV2;
  onChanged: () => void;
  compact?: boolean;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gateway = status.gateway;
  const connected = gateway.reachable && gateway.authenticated;
  const shouldShowLogin = gateway.mode === 'external' && status.action === 'login_gateway';

  if (gateway.mode !== 'external') return null;

  const onLogin = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await window.electronAPI.backends.loginGateway(username, password);
      if (!result.ok) {
        setError(result.message ?? 'Gateway login failed');
        return;
      }
      setPassword('');
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={
        compact
          ? 'w-full overflow-hidden rounded-md border border-sidebar-border bg-sidebar-accent/30 p-2'
          : 'rounded-md border border-border bg-muted/20 p-3'
      }
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p
            className={
              compact
                ? 'text-xs font-medium text-sidebar-foreground'
                : 'text-sm font-medium text-foreground'
            }
          >
            <span className="break-words">
              {connected ? `Connected to ${gateway.url}` : 'AIGateway connection'}
            </span>
          </p>
          {!connected && (
            <p className="text-xs text-muted-foreground">
              {status.message ??
                (gateway.reachable ? 'Sign in to continue.' : 'Gateway is unreachable.')}
            </p>
          )}
        </div>
        {connected && (
          <button
            onClick={async () => {
              await window.electronAPI.backends.logoutGateway();
              onChanged();
            }}
            className="rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Log out
          </button>
        )}
      </div>
      {shouldShowLogin && (
        <form
          onSubmit={onLogin}
          className={
            compact
              ? 'mt-2 flex min-w-0 flex-col gap-1.5'
              : 'mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]'
          }
        >
          <input
            value={username}
            onChange={(event) => {
              setUsername(event.target.value);
              setError(null);
            }}
            placeholder="Gateway username"
            className="min-w-0 rounded border border-border bg-background px-2 py-1 text-xs"
            autoComplete="username"
          />
          <input
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setError(null);
            }}
            placeholder="Password"
            type="password"
            className="min-w-0 rounded border border-border bg-background px-2 py-1 text-xs"
            autoComplete="current-password"
          />
          <button
            type="submit"
            disabled={busy || !username || !password}
            className={
              compact
                ? 'w-full rounded bg-chart-1 px-2.5 py-1 text-xs font-semibold text-background hover:bg-chart-1/90 disabled:opacity-60'
                : 'rounded bg-chart-1 px-2.5 py-1 text-xs font-semibold text-background hover:bg-chart-1/90 disabled:opacity-60'
            }
          >
            {busy ? 'Signing in...' : 'Sign in'}
          </button>
          {error && <p className="text-xs text-destructive sm:col-span-3">{error}</p>}
        </form>
      )}
    </div>
  );
}
