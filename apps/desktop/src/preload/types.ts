export interface ServerInfo {
  event: 'ready';
  host: string;
  port: number;
  pid: number;
  scheme: string;
}

export type ServerStatus = 'stopped' | 'starting' | 'ready' | 'error' | 'restarting';
export type VenvStatus = 'unknown' | 'checking' | 'missing' | 'creating' | 'ready' | 'error';
export type SessionStatus = 'starting' | 'running' | 'stopping' | 'stopped' | 'error';

export type SessionType = 'claude' | 'codex' | 'gemini' | 'claude-desktop';

export interface SessionInfo {
  id: string;
  type: SessionType;
  port: number;
  status: SessionStatus;
  createdAt: string;
  workingDir: string;
  pluginConfig?: Record<string, Record<string, unknown>>;
}

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  remoteEntryUrl: string;
  exposedModule: string;
  description?: string;
  iconUrl?: string;
  active: boolean;
}

export interface DiscoveredPlugin {
  state: 'enabled' | 'available';
  version: string | null;
  description: string | null;
  requires_root?: boolean;
  depends?: string[];
  conflicts?: string[];
}

export type BackendAction = 'healthy' | 'reauth' | 'rate_limited' | 'degraded';

export interface BackendHealth {
  authenticated: boolean;
  model?: string;
  tokens_remaining?: number | null;
  requests_remaining?: number | null;
  rate_limit?: Record<string, unknown>;
  error?: string | null;
  action: BackendAction;
  cli_command?: string | null;
  help_text?: string | null;
  auth_kind?: 'cli' | 'browser';
}

export type BackendStatusMap = Record<string, BackendHealth>;

export interface BackendAlert {
  backend: string;
  type: 'reauth' | 'rate_limited' | 'recovered';
  health: BackendHealth;
}

export type BackendProfileState = 'pending' | 'authenticated' | 'error';

export interface BackendProfile {
  id: string;
  provider: string;
  name: string;
  state: BackendProfileState;
  account_label?: string | null;
  last_refreshed_at?: string | null;
}

export interface ListProfilesResult {
  profiles: BackendProfile[];
  error?: string;
}

export interface DeleteProfileResult {
  ok: boolean;
  status?: number;
}

export type ExchangeOAuthCodeResult =
  | { ok: true }
  | { ok: false; status?: number; message?: string };

export type OAuthLauncherResult =
  | { kind: 'complete' }
  | {
      kind: 'failed';
      reason: 'timeout' | 'gateway_error' | 'provider_error' | 'network_error';
      message?: string;
    };

export interface ElectronAPI {
  popup: {
    open: (url: string, title?: string) => Promise<void>;
    close: () => Promise<void>;
  };
  server: {
    start: () => Promise<boolean>;
    stop: () => Promise<void>;
    restart: () => Promise<void>;
    getStatus: () => Promise<{ status: ServerStatus; info: ServerInfo | null }>;
    onStatusChanged: (callback: (status: ServerStatus) => void) => () => void;
    onLog: (callback: (line: string) => void) => () => void;
    fetch: (
      url: string,
      init?: { method?: string; body?: string },
    ) => Promise<{ ok: boolean; status: number; body: string }>;
  };
  venv: {
    detect: () => Promise<{
      status: VenvStatus;
      uvFound: boolean;
      needsSync: boolean;
      autoBootstrap: boolean;
    }>;
    create: () => Promise<boolean>;
    sync: (extra?: string) => Promise<boolean>;
    listPackages: () => Promise<Array<{ name: string; version: string }>>;
    onStatusChanged: (callback: (status: VenvStatus) => void) => () => void;
    onProgress: (callback: (line: string) => void) => () => void;
  };
  plugins: {
    list: () => Promise<PluginManifest[]>;
    install: (url: string) => Promise<PluginManifest>;
    uninstall: (id: string) => Promise<void>;
    activate: (id: string) => Promise<void>;
    deactivate: (id: string) => Promise<void>;
    getCatalog: () => Promise<PluginManifest[]>;
    discover: () => Promise<Record<string, DiscoveredPlugin>>;
    onChanged: (callback: (plugins: PluginManifest[]) => void) => () => void;
  };
  config: {
    read: () => Promise<Record<string, unknown>>;
    write: (config: Record<string, unknown>) => Promise<void>;
    onChanged: (callback: (config: Record<string, unknown>) => void) => () => void;
  };
  backends: {
    getStatus: () => Promise<BackendStatusMap>;
    refresh: () => Promise<BackendStatusMap>;
    authenticate: (backend: string) => Promise<void>;
    authenticateOAuth: (backend: string, profileName?: string) => Promise<OAuthLauncherResult>;
    listProfiles: (backend: string) => Promise<ListProfilesResult>;
    deleteProfile: (backend: string, profileName: string) => Promise<DeleteProfileResult>;
    getPendingAuthState: (backend: string) => Promise<string | null>;
    exchangeOAuthCode: (backend: string, code: string) => Promise<ExchangeOAuthCodeResult>;
    onStatusChanged: (callback: (status: BackendStatusMap) => void) => () => void;
    onAlert: (callback: (alert: BackendAlert) => void) => () => void;
  };
  session: {
    pickDir: () => Promise<string | null>;
    create: (
      type: SessionType,
      workingDir: string,
      pluginConfig?: Record<string, Record<string, unknown>>,
    ) => Promise<SessionInfo>;
    list: () => Promise<SessionInfo[]>;
    terminate: (id: string) => Promise<void>;
    terminateAll: () => Promise<void>;
    remove: (id: string) => Promise<void>;
    update: (
      id: string,
      workingDir: string,
      pluginConfig?: Record<string, Record<string, unknown>>,
    ) => Promise<SessionInfo>;
    restart: (id: string) => Promise<SessionInfo>;
    onSessionsChanged: (callback: (sessions: SessionInfo[]) => void) => () => void;
    onLog: (callback: (id: string, line: string) => void) => () => void;
  };
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
