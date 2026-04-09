import { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Square,
  X,
  Terminal,
  Circle,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  Pencil,
  Play,
  Download,
  ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ServerLogs } from '@/components/server/ServerLogs';
import { NewSessionDialog } from '@/components/session/NewSessionDialog';
import { useSessions } from '@/hooks/use-sessions';
import { useServerStatus } from '@/hooks/use-server-status';
import type { SessionInfo, SessionStatus, SessionType } from '../../../preload/types';

interface SessionTypeInfo {
  type: SessionType;
  label: string;
  frontendPlugin: string;
  installCommand: string;
  installUrl: string;
  description: string;
}

const ALL_SESSION_TYPES: SessionTypeInfo[] = [
  {
    type: 'claude',
    label: 'Claude Code',
    frontendPlugin: 'claude-frontend',
    installCommand: 'npm install -g @anthropic-ai/claude-code',
    installUrl: 'https://docs.anthropic.com/en/docs/claude-code',
    description: 'AI coding assistant by Anthropic',
  },
  {
    type: 'codex',
    label: 'Codex',
    frontendPlugin: 'codex-frontend',
    installCommand: 'npm install -g @openai/codex',
    installUrl: 'https://github.com/openai/codex',
    description: 'AI coding agent by OpenAI',
  },
  {
    type: 'gemini',
    label: 'Gemini CLI',
    frontendPlugin: 'gemini-frontend',
    installCommand: 'npm install -g @anthropic-ai/gemini-cli',
    installUrl: 'https://github.com/anthropics/gemini-cli',
    description: 'AI coding assistant by Google',
  },
];

function statusColor(status: SessionStatus): string {
  switch (status) {
    case 'running':
      return 'text-green-400';
    case 'starting':
      return 'text-yellow-400';
    case 'stopping':
      return 'text-orange-400';
    case 'error':
      return 'text-red-400';
    default:
      return 'text-muted-foreground';
  }
}

function statusLabel(status: SessionStatus): string {
  switch (status) {
    case 'starting':
      return 'Starting proxy...';
    case 'running':
      return 'Running';
    case 'stopping':
      return 'Stopping...';
    case 'stopped':
      return 'Stopped';
    case 'error':
      return 'Error';
  }
}

function shortDir(dir: string): string {
  const match = dir.match(/^\/Users\/[^/]+/);
  if (match && dir.startsWith(match[0])) {
    return '~' + dir.slice(match[0].length);
  }
  return dir;
}

function typeLabel(type: SessionType): string {
  return ALL_SESSION_TYPES.find((t) => t.type === type)?.label || type;
}

export function SessionsView() {
  const {
    sessions,
    logs,
    createSession,
    terminateSession,
    removeSession,
    updateSession,
    restartSession,
    clearLogs,
  } = useSessions();
  const { status: serverStatus, info: serverInfo } = useServerStatus();
  const [dialogType, setDialogType] = useState<SessionType | null>(null);
  const [editingSession, setEditingSession] = useState<SessionInfo | null>(null);
  const [installPrompt, setInstallPrompt] = useState<SessionTypeInfo | null>(null);
  const [activePlugins, setActivePlugins] = useState<Record<string, unknown>>({});

  // Fetch active plugins from server to determine which session types are available
  const serverUrl = serverInfo
    ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}`
    : null;

  const fetchPlugins = useCallback(async () => {
    if (!serverUrl || serverStatus !== 'ready') return;
    try {
      const res = await window.electronAPI.server.fetch(`${serverUrl}/plugins`);
      if (res.ok) setActivePlugins(JSON.parse(res.body));
    } catch {
      /* server not ready */
    }
  }, [serverUrl, serverStatus]);

  useEffect(() => {
    fetchPlugins();
  }, [fetchPlugins]);

  const isAvailable = (t: SessionTypeInfo) => t.frontendPlugin in activePlugins;

  const handleSessionButton = (t: SessionTypeInfo) => {
    if (isAvailable(t)) {
      setDialogType(t.type);
    } else {
      setInstallPrompt(t);
    }
  };

  const activeSessions = sessions.filter((s) => s.status !== 'stopped');
  const stoppedSessions = sessions.filter((s) => s.status === 'stopped');

  const handleLaunch = async (
    type: SessionType,
    workingDir: string,
    pluginConfig: Record<string, Record<string, unknown>>,
  ) => {
    if (editingSession) {
      await updateSession(editingSession.id, workingDir, pluginConfig);
      await restartSession(editingSession.id);
      setEditingSession(null);
    } else {
      setDialogType(null);
      await createSession(type, workingDir, pluginConfig);
    }
  };

  const handleCloseDialog = () => {
    setDialogType(null);
    setEditingSession(null);
  };

  return (
    <div className="flex h-full flex-col">
      {/* New / Edit session dialog */}
      {(dialogType || editingSession) && (
        <NewSessionDialog
          type={editingSession?.type || dialogType!}
          editSession={editingSession ?? undefined}
          onLaunch={handleLaunch}
          onClose={handleCloseDialog}
        />
      )}

      {/* Install prompt overlay */}
      {installPrompt && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setInstallPrompt(null)}
        >
          <div
            className="relative w-[420px] overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Gradient accent bar */}
            <div className="h-1 bg-gradient-to-r from-purple-500 via-pink-500 to-orange-500" />

            <div className="p-6">
              {/* Icon + title */}
              <div className="mb-4 flex items-start gap-4">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <Download className="h-5 w-5 text-muted-foreground" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-foreground">
                    {installPrompt.label} is not installed
                  </h2>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {installPrompt.description}
                  </p>
                </div>
              </div>

              {/* Install command */}
              <div className="mb-4 rounded-lg bg-muted/50 p-3">
                <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Install via terminal
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-background px-3 py-2 font-mono text-xs text-foreground">
                    {installPrompt.installCommand}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0 text-xs"
                    onClick={() => {
                      navigator.clipboard.writeText(installPrompt.installCommand);
                    }}
                  >
                    Copy
                  </Button>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between">
                <button
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => window.open(installPrompt.installUrl, '_blank')}
                >
                  <ExternalLink className="h-3 w-3" />
                  Documentation
                </button>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setInstallPrompt(null)}>
                    Close
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      setInstallPrompt(null);
                      fetchPlugins();
                    }}
                  >
                    I've installed it
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Sessions</h1>
          <p className="text-xs text-muted-foreground">
            Each session runs a CLI tool in its own terminal with a dedicated proxy
          </p>
        </div>
        <div className="flex gap-2">
          {ALL_SESSION_TYPES.map((t) => {
            const available = isAvailable(t);
            return (
              <Button
                key={t.type}
                variant="outline"
                size="sm"
                className={available ? '' : 'opacity-40 border-dashed'}
                onClick={() => handleSessionButton(t)}
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                {t.label}
              </Button>
            );
          })}
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-6">
        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Terminal className="mb-4 h-10 w-10 opacity-20" />
            <p className="mb-1 text-sm font-medium">No sessions yet</p>
            <p className="mb-4 text-xs">
              Start a new session to launch a CLI tool in an external terminal
            </p>
            <div className="flex gap-2">
              {ALL_SESSION_TYPES.map((t) => {
                const available = isAvailable(t);
                return (
                  <Button
                    key={t.type}
                    variant="outline"
                    size="sm"
                    className={available ? '' : 'opacity-40 border-dashed'}
                    onClick={() => handleSessionButton(t)}
                  >
                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                    {t.label}
                  </Button>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {activeSessions.length > 0 && (
              <div>
                <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Active
                </h2>
                <div className="space-y-2">
                  {activeSessions.map((s) => (
                    <SessionCard
                      key={s.id}
                      session={s}
                      logs={logs[s.id] || []}
                      onClearLogs={() => clearLogs(s.id)}
                      onStop={() => terminateSession(s.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {stoppedSessions.length > 0 && (
              <div>
                <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Stopped
                </h2>
                <div className="space-y-2">
                  {stoppedSessions.map((s) => (
                    <SessionCard
                      key={s.id}
                      session={s}
                      logs={logs[s.id] || []}
                      onClearLogs={() => clearLogs(s.id)}
                      onRemove={() => removeSession(s.id)}
                      onEdit={() => setEditingSession(s)}
                      onRestart={() => restartSession(s.id)}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SessionCard({
  session,
  logs,
  onClearLogs,
  onStop,
  onRemove,
  onEdit,
  onRestart,
}: {
  session: {
    id: string;
    type: SessionType;
    port: number;
    status: SessionStatus;
    workingDir: string;
    createdAt: string;
  };
  logs: string[];
  onClearLogs: () => void;
  onStop?: () => void;
  onRemove?: () => void;
  onEdit?: () => void;
  onRestart?: () => void;
}) {
  const [showLogs, setShowLogs] = useState(false);

  const time = new Date(session.createdAt).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  // Auto-expand logs on error
  useEffect(() => {
    if (session.status === 'error' && logs.length > 0) {
      setShowLogs(true);
    }
  }, [session.status, logs.length]);

  return (
    <div className="space-y-0">
      <div className="flex items-center gap-4 rounded-lg border border-border bg-card px-4 py-3">
        {/* Status dot */}
        <Circle className={`h-2.5 w-2.5 shrink-0 fill-current ${statusColor(session.status)}`} />

        {/* Info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm font-medium text-foreground">
              {shortDir(session.workingDir)}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="font-medium">{typeLabel(session.type)}</span>
            <span>Port {session.port}</span>
            <span>{statusLabel(session.status)}</span>
            <span>{time}</span>
          </div>
        </div>

        {/* Logs toggle */}
        <button
          onClick={() => setShowLogs(!showLogs)}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {showLogs ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Logs{logs.length > 0 && ` (${logs.length})`}
        </button>

        {/* Actions */}
        {onStop && session.status !== 'stopped' && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onStop}
            className="h-8 w-8 text-destructive hover:text-destructive"
            title="Stop session"
          >
            <Square className="h-3.5 w-3.5" />
          </Button>
        )}
        {onEdit && (session.status === 'stopped' || session.status === 'error') && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onEdit}
            className="h-8 w-8 text-muted-foreground hover:text-foreground"
            title="Edit settings"
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
        {onRestart && (session.status === 'stopped' || session.status === 'error') && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onRestart}
            className="h-8 w-8 text-green-400 hover:text-green-300"
            title="Restart session"
          >
            <Play className="h-3.5 w-3.5" />
          </Button>
        )}
        {onRemove && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onRemove}
            className="h-8 w-8 text-muted-foreground hover:text-foreground"
            title="Remove from list"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Expandable logs — reuses ServerLogs with copy, clear, fullscreen, folding */}
      {showLogs && (
        <div className="mt-1">
          <ServerLogs logs={logs} onClear={onClearLogs} />
        </div>
      )}
    </div>
  );
}
