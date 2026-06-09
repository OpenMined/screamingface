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
export type GatewayAction =
  | 'healthy'
  | 'starting'
  | 'probing'
  | 'login_gateway'
  | 'login_provider'
  | 'gateway_unreachable'
  | 'gateway_misconfigured'
  | 'gateway_url_missing';

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

export interface BackendPollingError {
  status?: number;
  code?: string;
  message: string;
  consecutiveFailures: number;
}

export interface GatewayStatus {
  mode: 'local_managed' | 'external';
  managed_by_runner: boolean;
  reachable: boolean;
  authenticated: boolean;
  auth_required: boolean;
  url: string;
}

export interface ProviderAuthStatus {
  provider: string;
  profile: string;
  state: 'authenticated' | 'pending' | 'missing_profile' | 'error';
}

export interface BackendStatusV2 {
  version: 2;
  gateway: GatewayStatus;
  action: GatewayAction;
  message?: string;
  provider_auth?: { providers: Record<string, ProviderAuthStatus> };
  backends?: BackendStatusMap;
}

export type BackendStatusResponse = BackendStatusMap | BackendStatusV2;

export interface BackendAlert {
  backend: string;
  type: 'reauth' | 'rate_limited' | 'recovered';
  health: BackendHealth;
}

export type BackendProfileState = 'pending' | 'authenticated' | 'error';

export type BackendProfileAuthType = 'oauth' | 'api_key';

export interface BackendProfile {
  id: string;
  provider: string;
  name: string;
  state: BackendProfileState;
  auth_type?: BackendProfileAuthType;
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

export interface SetProfileApiKeyResult {
  ok: boolean;
  status?: number;
  message?: string;
}

export type OAuthConnectionStatus = 'pending' | 'active' | 'expired' | 'revoked' | 'error';

export interface OAuthConnectionAccount {
  sub?: string | null;
  email?: string | null;
  name?: string | null;
  raw?: Record<string, unknown>;
}

export interface OAuthConnection {
  id: string;
  provider: string;
  label: string;
  status: OAuthConnectionStatus;
  account?: OAuthConnectionAccount | null;
  created_at?: string;
  last_used_at?: string | null;
  last_refreshed_at?: string | null;
  error_message?: string | null;
  is_duplicate?: boolean;
}

export interface ListConnectionsResult {
  connections: OAuthConnection[];
  error?: string;
}

export interface DeleteConnectionResult {
  ok: boolean;
  status?: number;
}

export interface RefreshConnectionResult {
  ok: boolean;
  status?: number;
  connection?: OAuthConnection;
  message?: string;
}

export type ExchangeOAuthCodeResult =
  | { ok: true }
  | { ok: false; status?: number; message?: string };

export type GatewayLoginResult = { ok: true } | { ok: false; message?: string };

export interface AigwSessionSnapshot {
  hasValidJwt: boolean;
  jwtExpiresAt: string | null;
  isLoggedIn: boolean;
  username: string | null;
  gatewayUrl: string;
  rememberAvailable: boolean;
  secureStorageAvailable: boolean;
  storedInPlaintext: boolean;
  lastError: string | null;
}

export type AigwLoginResult =
  | { ok: true; snapshot: AigwSessionSnapshot; warning?: string }
  | { ok: false; message: string; snapshot: AigwSessionSnapshot };

export interface AigwLoginOptions {
  persist?: boolean;
  allowPlaintextStorage?: boolean;
}

export type OAuthLauncherResult =
  | { kind: 'complete'; connection?: OAuthConnection; isDuplicate?: boolean }
  | {
      kind: 'failed';
      reason: 'timeout' | 'gateway_error' | 'provider_error' | 'network_error' | 'cancelled';
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
      init?: { method?: string; body?: string; headers?: Record<string, string> },
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
    getStatus: () => Promise<BackendStatusResponse>;
    getPollingError: () => Promise<BackendPollingError | null>;
    refresh: () => Promise<BackendStatusResponse>;
    authenticate: (backend: string) => Promise<void>;
    loginGateway: (username: string, password: string) => Promise<GatewayLoginResult>;
    logoutGateway: () => Promise<void>;
    authenticateOAuth: (backend: string, profileName?: string) => Promise<OAuthLauncherResult>;
    authenticateOAuthConnection: (backend: string, label?: string) => Promise<OAuthLauncherResult>;
    listProfiles: (backend: string) => Promise<ListProfilesResult>;
    deleteProfile: (backend: string, profileName: string) => Promise<DeleteProfileResult>;
    setProfileApiKey: (
      backend: string,
      profileName: string,
      apiKey: string,
    ) => Promise<SetProfileApiKeyResult>;
    listConnections: (backend: string) => Promise<ListConnectionsResult>;
    deleteConnection: (backend: string, connectionId: string) => Promise<DeleteConnectionResult>;
    refreshConnection: (backend: string, connectionId: string) => Promise<RefreshConnectionResult>;
    getPendingAuthState: (backend: string, profileName?: string) => Promise<string | null>;
    getPendingConnectionAuthState: (
      backend: string,
      connectionId?: string,
    ) => Promise<string | null>;
    exchangeOAuthCode: (
      backend: string,
      code: string,
      profileName?: string,
    ) => Promise<ExchangeOAuthCodeResult>;
    exchangeOAuthConnectionCode: (
      backend: string,
      connectionId: string,
      code: string,
    ) => Promise<ExchangeOAuthCodeResult>;
    onStatusChanged: (callback: (status: BackendStatusResponse) => void) => () => void;
    onPollingError: (callback: (error: BackendPollingError | null) => void) => () => void;
    onAlert: (callback: (alert: BackendAlert) => void) => () => void;
  };
  aigwSession: {
    getState: () => Promise<AigwSessionSnapshot>;
    getJwt: () => Promise<string | null>;
    isLoggedIn: () => Promise<boolean>;
    login: (
      username: string,
      password: string,
      options?: AigwLoginOptions,
    ) => Promise<AigwLoginResult>;
    logout: () => Promise<AigwSessionSnapshot>;
    setGatewayUrl: (gatewayUrl: string) => Promise<AigwSessionSnapshot>;
    onChanged: (callback: (snapshot: AigwSessionSnapshot) => void) => () => void;
    onExpired: (callback: (snapshot: AigwSessionSnapshot) => void) => () => void;
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
