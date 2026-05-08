import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import type {
  BackendStatusMap,
  BackendHealth,
  BackendAlert,
  BackendProfile,
} from '../../../../preload/types';
import { useToast } from '@/hooks/use-toast';

const profileStateConfig: Record<string, { dot: string; label: string }> = {
  authenticated: { dot: 'bg-chart-3', label: 'Authenticated' },
  pending: { dot: 'bg-chart-1', label: 'Pending' },
  error: { dot: 'bg-destructive', label: 'Error' },
};

const PROFILE_NAME_RE = /^[a-z0-9-]+$/;

const actionConfig: Record<string, { dot: string; label: string }> = {
  healthy: { dot: 'bg-chart-3', label: 'Ready' },
  reauth: { dot: 'bg-chart-1', label: 'Needs Auth' },
  rate_limited: { dot: 'bg-destructive', label: 'Rate Limited' },
  degraded: { dot: 'bg-chart-1', label: 'Degraded' },
};

const backendLabels: Record<string, string> = {
  claude: 'Claude',
  codex: 'Codex',
  gemini: 'Gemini',
};

function AuthButton({
  name,
  authKind,
  cliCommand,
}: {
  name: string;
  authKind: 'cli' | 'browser';
  cliCommand?: string;
}) {
  const [waiting, setWaiting] = useState(false);

  if (authKind === 'cli') {
    if (!cliCommand) return null;
    return (
      <button
        onClick={() => window.electronAPI.backends.authenticate(name)}
        className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 transition-colors"
      >
        Re-authenticate
      </button>
    );
  }

  // browser
  return (
    <button
      disabled={waiting}
      onClick={async () => {
        setWaiting(true);
        try {
          await window.electronAPI.backends.authenticateOAuth(name);
        } finally {
          setWaiting(false);
        }
      }}
      className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 transition-colors disabled:opacity-60"
    >
      {waiting ? 'Waiting for browser…' : 'Authenticate'}
    </button>
  );
}

function ProfileRow({
  backendName,
  profile,
  onChanged,
}: {
  backendName: string;
  profile: BackendProfile;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cfg = profileStateConfig[profile.state] ?? { dot: 'bg-muted', label: profile.state };

  const onReauth = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const result = await window.electronAPI.backends.authenticateOAuth(
        backendName,
        profile.name,
      );
      if (result.kind === 'failed') {
        const reason = result.message ? `${result.reason}: ${result.message}` : result.reason;
        setError(`Re-auth failed — ${reason}`);
      }
    } catch (e) {
      setError(`Re-auth failed — ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
      onChanged();
    }
  };

  const onDelete = async (): Promise<void> => {
    if (!window.confirm(`Delete profile "${profile.name}"? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await window.electronAPI.backends.deleteProfile(backendName, profile.name);
    } finally {
      setBusy(false);
      onChanged();
    }
  };

  // While the profile is mid-OAuth (browser open, gateway polling), show
  // an animated dot + a "waiting on browser" hint so the user knows the
  // pending row is actively waiting on something, not stuck.
  const isPending = profile.state === 'pending';

  return (
    <div className="flex items-center justify-between py-1.5">
      <div className="flex items-center gap-2 min-w-0">
        <span className="relative inline-flex h-2 w-2 shrink-0">
          {isPending && (
            <span
              className={cn(
                'absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping',
                cfg.dot,
              )}
            />
          )}
          <span className={cn('relative inline-flex h-2 w-2 rounded-full', cfg.dot)} />
        </span>
        <span className="text-xs font-medium text-foreground">{profile.name}</span>
        {profile.account_label && (
          <span className="text-xs text-muted-foreground truncate">{profile.account_label}</span>
        )}
        <span className="text-xs text-muted-foreground">· {cfg.label}</span>
        {isPending && (
          <span className="text-xs text-muted-foreground italic">— waiting on browser</span>
        )}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          disabled={busy}
          onClick={onReauth}
          className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 transition-colors disabled:opacity-60"
        >
          {busy ? 'Working…' : 'Re-authenticate'}
        </button>
        <button
          disabled={busy}
          onClick={onDelete}
          aria-label={`Delete profile ${profile.name}`}
          className="text-xs text-muted-foreground hover:text-destructive transition-colors disabled:opacity-60"
        >
          Delete
        </button>
      </div>
      {error && (
        <p className="basis-full text-xs text-destructive mt-1">{error}</p>
      )}
    </div>
  );
}

function ProfilesSubPanel({ name }: { name: string }) {
  const [profiles, setProfiles] = useState<BackendProfile[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [addError, setAddError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [hasPendingAuth, setHasPendingAuth] = useState(false);
  const [pasteCode, setPasteCode] = useState('');
  const [pasteBusy, setPasteBusy] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const result = await window.electronAPI.backends.listProfiles(name);
    setProfiles(result.profiles ?? []);
    setLoaded(true);
  }, [name]);

  const checkPending = useCallback(async () => {
    const s = await window.electronAPI.backends.getPendingAuthState(name);
    setHasPendingAuth(!!s);
  }, [name]);

  useEffect(() => {
    void refresh();
    void checkPending();
  }, [refresh, checkPending]);

  const onPasteSubmit = async (e?: React.FormEvent): Promise<void> => {
    e?.preventDefault();
    if (pasteBusy) return;
    const code = pasteCode.trim();
    if (!code) {
      setPasteError('Paste the authorization code');
      return;
    }
    setPasteBusy(true);
    setPasteError(null);
    try {
      const result = await window.electronAPI.backends.exchangeOAuthCode(name, code);
      if (result.ok) {
        setPasteCode('');
        setHasPendingAuth(false);
        await refresh();
      } else {
        setPasteError(result.message ?? `Exchange failed${result.status ? ` (${result.status})` : ''}`);
      }
    } catch (err) {
      setPasteError(err instanceof Error ? err.message : String(err));
    } finally {
      setPasteBusy(false);
    }
  };

  const validate = (candidate: string): string | null => {
    if (!candidate) return 'Name is required';
    if (!PROFILE_NAME_RE.test(candidate)) return 'Use lowercase letters, digits, hyphens';
    if (profiles.some((p) => p.name === candidate)) return 'Profile already exists';
    return null;
  };

  const onAdd = (e?: React.FormEvent): void => {
    e?.preventDefault();
    if (submitting) return;
    const candidate = newName.trim();
    const err = validate(candidate);
    if (err) {
      setAddError(err);
      return;
    }
    setSubmitting(true);
    setAddError(null);
    // Close the form immediately — the browser will open right away,
    // and the long-running poll happens in the background. We surface
    // any failure via panel-level addError, then refresh the list.
    setAdding(false);
    setNewName('');
    void (async () => {
      // Briefly poll for the launcher to publish the PKCE state so the
      // paste-code fallback form can become available before the long
      // poll resolves.
      const pendingPoll = setInterval(() => {
        void checkPending();
      }, 500);
      try {
        const result = await window.electronAPI.backends.authenticateOAuth(name, candidate);
        if (result.kind === 'failed') {
          const reason = result.message ? `${result.reason}: ${result.message}` : result.reason;
          setAddError(`Authentication failed for "${candidate}" — ${reason}`);
        }
      } catch (err2) {
        setAddError(
          `Authentication failed for "${candidate}" — ${err2 instanceof Error ? err2.message : String(err2)}`,
        );
      } finally {
        clearInterval(pendingPoll);
        setSubmitting(false);
        void refresh();
        void checkPending();
      }
    })();
  };

  const onCancel = (): void => {
    setAdding(false);
    setNewName('');
    setAddError(null);
  };

  return (
    <div className="ml-6 mt-1 mb-2 border-t border-border pt-2">
      {!loaded && (
        <div className="flex items-center gap-2 py-1 animate-pulse" aria-label="Loading profiles">
          <span className="h-2 w-2 rounded-full shrink-0 bg-muted" />
          <span className="h-3 w-16 rounded bg-muted" />
        </div>
      )}
      {loaded && profiles.length === 0 && (
        <p className="text-xs text-muted-foreground py-1">No profiles yet.</p>
      )}
      {profiles.map((p) => (
        <ProfileRow
          key={p.id || p.name}
          backendName={name}
          profile={p}
          onChanged={() => {
            void refresh();
            void checkPending();
          }}
        />
      ))}
      {adding ? (
        <form onSubmit={onAdd} className="flex items-center gap-2 py-1.5">
          <input
            autoFocus
            type="text"
            value={newName}
            onChange={(e) => {
              setNewName(e.target.value);
              setAddError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.preventDefault();
                onCancel();
              }
            }}
            placeholder="profile name (e.g. work)"
            className="flex-1 rounded border border-border bg-background px-2 py-0.5 text-xs"
          />
          <button
            type="submit"
            className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30"
          >
            Confirm
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        </form>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="rounded bg-chart-1 px-2.5 py-1 text-xs font-semibold text-background hover:bg-chart-1/90 transition-colors mt-1"
        >
          + Add Profile
        </button>
      )}
      {addError && <p className="text-xs text-destructive mt-1">{addError}</p>}
      {hasPendingAuth && (
        <form
          onSubmit={onPasteSubmit}
          className="flex items-center gap-2 py-1.5 mt-2 border-t border-border pt-2"
          aria-label="Paste authorization code"
        >
          <span className="text-xs text-muted-foreground">Pasted authorization code?</span>
          <input
            type="text"
            value={pasteCode}
            onChange={(e) => {
              setPasteCode(e.target.value);
              setPasteError(null);
            }}
            placeholder="paste code here"
            aria-label="Authorization code"
            className="flex-1 rounded border border-border bg-background px-2 py-0.5 text-xs font-mono"
          />
          <button
            type="submit"
            disabled={pasteBusy}
            className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 disabled:opacity-60"
          >
            {pasteBusy ? 'Submitting…' : 'Submit'}
          </button>
        </form>
      )}
      {pasteError && <p className="text-xs text-destructive mt-1">{pasteError}</p>}
    </div>
  );
}

function BackendRow({ name, health }: { name: string; health: BackendHealth }) {
  const config = actionConfig[health.action] || actionConfig.degraded;
  const label = backendLabels[name] || name;
  const isBrowser = health.auth_kind === 'browser';

  return (
    <div className="py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <span className={cn('h-2.5 w-2.5 rounded-full shrink-0', config.dot)} />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">{label}</span>
              {health.model && (
                <code className="text-xs text-muted-foreground truncate">{health.model}</code>
              )}
            </div>
            {health.action === 'healthy' && health.tokens_remaining != null && (
              <p className="text-xs text-muted-foreground">
                {Math.round(health.tokens_remaining / 1000)}k tokens remaining
              </p>
            )}
            {health.action !== 'healthy' && health.help_text && (
              <p className="text-xs text-muted-foreground truncate">{health.help_text}</p>
            )}
            {health.action !== 'healthy' && !health.help_text && health.error && (
              <p className="text-xs text-destructive truncate">{health.error}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-2">
          <span className="text-xs text-muted-foreground">{config.label}</span>
          {/*
           * For browser-mode backends, the profile sub-panel is the single source of
           * truth for auth actions (per-profile Re-authenticate). The top-level
           * Authenticate button is hidden to avoid two concurrent auth UIs.
           * CLI-mode backends keep the existing Re-authenticate button.
           */}
          {!isBrowser && health.action === 'reauth' && (
            <AuthButton
              name={name}
              authKind={health.auth_kind ?? 'cli'}
              cliCommand={health.cli_command ?? undefined}
            />
          )}
        </div>
      </div>
      {isBrowser && <ProfilesSubPanel name={name} />}
    </div>
  );
}

export function BackendStatusPanel() {
  const [statuses, setStatuses] = useState<BackendStatusMap>({});
  const [loaded, setLoaded] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    // Load initial status
    window.electronAPI.backends.getStatus().then((s) => {
      setStatuses(s);
      setLoaded(true);
    });

    // Subscribe to updates
    const unsubStatus = window.electronAPI.backends.onStatusChanged((s) => {
      setStatuses(s);
      setLoaded(true);
    });

    const unsubAlert = window.electronAPI.backends.onAlert((alert: BackendAlert) => {
      const label = backendLabels[alert.backend] || alert.backend;
      if (alert.type === 'reauth') {
        toast({
          variant: 'error',
          title: `${label} needs re-authentication`,
          description: alert.health.cli_command
            ? `Run: ${alert.health.cli_command}`
            : 'Check backend credentials',
        });
      } else if (alert.type === 'rate_limited') {
        toast({
          variant: 'warning',
          title: `${label} rate limited`,
          description: 'API rate budget exhausted. Will recover automatically.',
        });
      } else if (alert.type === 'recovered') {
        toast({
          variant: 'success',
          title: `${label} recovered`,
          description: 'Backend is healthy again.',
        });
      }
    });

    return () => {
      unsubStatus();
      unsubAlert();
    };
  }, [toast]);

  const backends = Object.entries(statuses);
  // Hide entirely only when we KNOW the server has no backends (loaded + empty).
  // While the initial fetch is in flight we render a skeleton so the panel
  // doesn't pop in suddenly.
  if (loaded && backends.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-foreground">Backends</h3>
        <button
          onClick={() => window.electronAPI.backends.refresh()}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Refresh
        </button>
      </div>
      {!loaded && (
        <div className="space-y-2 py-1" aria-label="Loading backends">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3 py-2 animate-pulse">
              <span className="h-2.5 w-2.5 rounded-full shrink-0 bg-muted" />
              <div className="h-3 w-24 rounded bg-muted" />
              <div className="h-3 w-32 rounded bg-muted/50" />
            </div>
          ))}
        </div>
      )}
      <div className="divide-y divide-border">
        {backends.map(([name, health]) => (
          <BackendRow key={name} name={name} health={health} />
        ))}
      </div>
    </div>
  );
}
