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
  const cfg = profileStateConfig[profile.state] ?? { dot: 'bg-muted', label: profile.state };

  const onReauth = async (): Promise<void> => {
    setBusy(true);
    try {
      await window.electronAPI.backends.authenticateOAuth(backendName, profile.name);
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

  return (
    <div className="flex items-center justify-between py-1.5">
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn('h-2 w-2 rounded-full shrink-0', cfg.dot)} />
        <span className="text-xs font-medium text-foreground">{profile.name}</span>
        {profile.account_label && (
          <span className="text-xs text-muted-foreground truncate">{profile.account_label}</span>
        )}
        <span className="text-xs text-muted-foreground">· {cfg.label}</span>
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

  const refresh = useCallback(async () => {
    const result = await window.electronAPI.backends.listProfiles(name);
    setProfiles(result.profiles ?? []);
    setLoaded(true);
  }, [name]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const validate = (candidate: string): string | null => {
    if (!candidate) return 'Name is required';
    if (!PROFILE_NAME_RE.test(candidate)) return 'Use lowercase letters, digits, hyphens';
    if (profiles.some((p) => p.name === candidate)) return 'Profile already exists';
    return null;
  };

  const onAdd = async (): Promise<void> => {
    const candidate = newName.trim();
    const err = validate(candidate);
    if (err) {
      setAddError(err);
      return;
    }
    setSubmitting(true);
    setAddError(null);
    try {
      await window.electronAPI.backends.authenticateOAuth(name, candidate);
      setNewName('');
      setAdding(false);
    } finally {
      setSubmitting(false);
      void refresh();
    }
  };

  return (
    <div className="ml-6 mt-1 mb-2 border-t border-border pt-2">
      {loaded && profiles.length === 0 && (
        <p className="text-xs text-muted-foreground py-1">No profiles yet.</p>
      )}
      {profiles.map((p) => (
        <ProfileRow key={p.id || p.name} backendName={name} profile={p} onChanged={refresh} />
      ))}
      {adding ? (
        <div className="flex items-center gap-2 py-1.5">
          <input
            autoFocus
            type="text"
            value={newName}
            onChange={(e) => {
              setNewName(e.target.value);
              setAddError(null);
            }}
            placeholder="profile name (e.g. work)"
            className="flex-1 rounded border border-border bg-background px-2 py-0.5 text-xs"
          />
          <button
            disabled={submitting}
            onClick={onAdd}
            className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 disabled:opacity-60"
          >
            {submitting ? 'Starting…' : 'Confirm'}
          </button>
          <button
            disabled={submitting}
            onClick={() => {
              setAdding(false);
              setNewName('');
              setAddError(null);
            }}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="text-xs text-chart-1 hover:underline mt-1"
        >
          + Add Profile
        </button>
      )}
      {addError && <p className="text-xs text-destructive mt-1">{addError}</p>}
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
  const { toast } = useToast();

  useEffect(() => {
    // Load initial status
    window.electronAPI.backends.getStatus().then(setStatuses);

    // Subscribe to updates
    const unsubStatus = window.electronAPI.backends.onStatusChanged(setStatuses);

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
  if (backends.length === 0) return null;

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
      <div className="divide-y divide-border">
        {backends.map(([name, health]) => (
          <BackendRow key={name} name={name} health={health} />
        ))}
      </div>
    </div>
  );
}
