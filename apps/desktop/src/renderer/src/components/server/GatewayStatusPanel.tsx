import type { BackendStatusV2 } from '../../../../preload/types';

export function GatewayStatusPanel({
  status,
  onChanged,
  onLoginRequest,
  compact = false,
}: {
  status: BackendStatusV2;
  onChanged: () => void;
  onLoginRequest?: () => void;
  compact?: boolean;
}) {
  const gateway = status.gateway;
  const connected = gateway.reachable && gateway.authenticated;
  const shouldShowLogin = gateway.mode === 'external' && status.action === 'login_gateway';

  if (gateway.mode !== 'external') return null;

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
              await window.electronAPI.aigwSession.logout();
              onChanged();
            }}
            className="rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Log out
          </button>
        )}
      </div>
      {shouldShowLogin && (
        <div
          className={
            compact
              ? 'mt-2 flex min-w-0 flex-col gap-1.5'
              : 'mt-3 flex items-center justify-between gap-3'
          }
        >
          <p className="text-xs text-muted-foreground">Sign in once; Desktop will refresh JWTs.</p>
          <button
            type="button"
            onClick={onLoginRequest}
            className={
              compact
                ? 'w-full rounded bg-chart-1 px-2.5 py-1 text-xs font-semibold text-background hover:bg-chart-1/90 disabled:opacity-60'
                : 'rounded bg-chart-1 px-2.5 py-1 text-xs font-semibold text-background hover:bg-chart-1/90 disabled:opacity-60'
            }
          >
            Sign in
          </button>
        </div>
      )}
    </div>
  );
}
