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
    onSessionsChanged: (callback: (sessions: SessionInfo[]) => void) => () => void;
    onLog: (callback: (id: string, line: string) => void) => () => void;
  };
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
