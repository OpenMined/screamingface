import { EventEmitter } from 'events';
import http from 'http';
import https from 'https';
import { isIP } from 'net';
import { safeStorage } from 'electron';
import { configService } from './config-service';
import { desktopSecretHeader } from './desktop-secret';

const AIGW_BASE_PLUGIN = 'aigw-base';
const DEFAULT_GATEWAY_URL = 'http://127.0.0.1:9105';
const JWT_REFRESH_BUFFER_MS = 30_000;
const REQUEST_TIMEOUT_MS = 25_000;

const USERNAME_KEY = 'aigw_credentials_username';
const ENCRYPTED_PASSWORD_KEY = 'aigw_credentials_enc';
const PLAINTEXT_PASSWORD_KEY = 'aigw_credentials_plaintext';
const STORAGE_KEY = 'aigw_credentials_storage';

export interface AigwCredentials {
  username: string;
  password: string;
}

export interface AigwSessionSnapshot {
  hasValidJwt: boolean;
  jwtExpiresAt: string | null;
  isLoggedIn: boolean;
  username: string | null;
  gatewayUrl: string;
  rememberAvailable: boolean;
  storedInPlaintext: boolean;
  lastError: string | null;
}

export type AigwLoginResult =
  | { ok: true; snapshot: AigwSessionSnapshot; warning?: string }
  | { ok: false; message: string; snapshot: AigwSessionSnapshot };

export interface AigwLoginOptions {
  silent?: boolean;
  persist?: boolean;
}

interface ConfigStore {
  read(): Record<string, unknown>;
  write(config: Record<string, unknown>): void;
}

type SafeStorageLike = Pick<
  Electron.SafeStorage,
  'decryptString' | 'encryptString' | 'isEncryptionAvailable'
>;

interface JsonResponse {
  status: number;
  body: string;
  json: unknown;
}

interface JsonRequestInit {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}

interface AigwSessionServiceDependencies {
  config?: ConfigStore;
  safeStorage?: SafeStorageLike;
  requestJson?: (url: string, init?: JsonRequestInit) => Promise<JsonResponse>;
  desktopSecretHeader?: () => Record<string, string>;
  now?: () => Date;
}

export class AigwSessionService extends EventEmitter {
  private readonly config: ConfigStore;
  private readonly storage: SafeStorageLike;
  private readonly requestJson: (url: string, init?: JsonRequestInit) => Promise<JsonResponse>;
  private readonly secretHeader: () => Record<string, string>;
  private readonly now: () => Date;
  private initialized = false;
  private serverUrl: string | null = null;
  private jwt: string | null = null;
  private jwtExpiresAt: Date | null = null;
  private credentials: AigwCredentials | null = null;
  private credentialsPersisted = false;
  private storedInPlaintext = false;
  private lastError: string | null = null;

  constructor(dependencies: AigwSessionServiceDependencies = {}) {
    super();
    this.config = dependencies.config ?? configService;
    this.storage = dependencies.safeStorage ?? safeStorage;
    this.requestJson = dependencies.requestJson ?? nodeRequestJson;
    this.secretHeader = dependencies.desktopSecretHeader ?? desktopSecretHeader;
    this.now = dependencies.now ?? (() => new Date());
  }

  async init(): Promise<AigwSessionSnapshot> {
    if (this.initialized) return this.snapshot();
    this.initialized = true;
    this.credentials = this.loadCredentials();
    this.credentialsPersisted = this.credentials !== null;
    this.emitChanged();
    if (this.serverUrl && this.credentials) {
      await this.login(this.credentials, { persist: this.credentialsPersisted, silent: true });
    }
    return this.snapshot();
  }

  async setServerUrl(serverUrl: string | null): Promise<AigwSessionSnapshot> {
    const nextUrl = serverUrl ? normalizeBaseUrl(serverUrl) : null;
    if (this.serverUrl === nextUrl) return this.snapshot();

    this.serverUrl = nextUrl;
    this.clearJwtOnly();
    this.emitChanged();
    if (this.initialized && this.serverUrl && this.credentials) {
      await this.login(this.credentials, { persist: this.credentialsPersisted, silent: true });
    }
    return this.snapshot();
  }

  getState(): AigwSessionSnapshot {
    return this.snapshot();
  }

  isLoggedIn(): boolean {
    return this.hasValidJwt();
  }

  async getJwt(): Promise<string | null> {
    if (this.hasValidJwt(JWT_REFRESH_BUFFER_MS)) return this.jwt;
    const hadJwt = this.jwt !== null;
    this.clearJwtOnly();
    if (this.credentials) {
      const result = await this.login(this.credentials, {
        persist: this.credentialsPersisted,
        silent: true,
      });
      if (result.ok && this.hasValidJwt(JWT_REFRESH_BUFFER_MS)) return this.jwt;
    }
    if (hadJwt) this.emitExpired('AIGateway session expired');
    return null;
  }

  async ensureLoggedIn(): Promise<string | null> {
    if (!this.credentials) {
      this.emitExpired('AIGateway login required');
      return null;
    }
    const result = await this.login(this.credentials, {
      persist: this.credentialsPersisted,
      silent: true,
    });
    if (result.ok) return this.jwt;
    this.emitExpired(result.message);
    return null;
  }

  async login(
    credentials: AigwCredentials,
    options: AigwLoginOptions = {},
  ): Promise<AigwLoginResult> {
    const persist = options.persist ?? true;
    if (!this.serverUrl) {
      return this.loginFailure('SF server is not running', options.silent === true);
    }

    try {
      const response = await this.requestJson(`${this.serverUrl}/aigateway/session/login`, {
        method: 'POST',
        headers: { ...this.secretHeader(), 'content-type': 'application/json' },
        body: JSON.stringify({ ...credentials, gateway_url: this.gatewayUrl() }),
      });
      if (response.status < 200 || response.status >= 300) {
        return this.loginFailure(extractErrorMessage(response) ?? `HTTP ${response.status}`, false);
      }

      const token = readStringField(response.json, 'token');
      const expiresAt = parseExpiresAt(readStringField(response.json, 'expires_at'));
      if (!token || !expiresAt) {
        return this.loginFailure('Gateway login returned an invalid session', false);
      }

      this.jwt = token;
      this.jwtExpiresAt = expiresAt;
      this.credentials = { ...credentials };
      this.credentialsPersisted = persist;
      this.lastError = null;
      const warning = persist
        ? this.saveCredentials(credentials)
        : this.clearPersistedCredentials();
      this.emitChanged();
      const snapshot = this.snapshot();
      return warning ? { ok: true, snapshot, warning } : { ok: true, snapshot };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return this.loginFailure(message, options.silent === true);
    }
  }

  async logout(): Promise<AigwSessionSnapshot> {
    if (this.serverUrl) {
      try {
        await this.requestJson(`${this.serverUrl}/aigateway/session/logout`, {
          method: 'POST',
          headers: this.secretHeader(),
        });
      } catch {
        // Local cleanup is more important than surfacing a stale SF process failure.
      }
    }

    this.clearJwtOnly();
    this.credentials = null;
    this.credentialsPersisted = false;
    this.lastError = null;
    this.clearPersistedCredentials();
    this.emitChanged();
    return this.snapshot();
  }

  notifyExpired(message = 'AIGateway session expired'): void {
    this.emitExpired(message);
  }

  setGatewayUrl(gatewayUrl: string): AigwSessionSnapshot {
    const normalized = validateGatewayUrl(gatewayUrl);
    const config = this.config.read();
    const pluginConfig = readPluginConfig(config);
    const baseConfig = readAigwBaseConfig(config);
    baseConfig.gateway_url = normalized;
    baseConfig.mode = 'external';
    pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
    config.plugin_config = pluginConfig;
    this.config.write(config);
    this.clearJwtOnly();
    this.emitChanged();
    return this.snapshot();
  }

  private snapshot(): AigwSessionSnapshot {
    const username =
      this.credentials?.username ??
      readStringField(readAigwBaseConfig(this.config.read()), USERNAME_KEY);
    return {
      hasValidJwt: this.hasValidJwt(),
      jwtExpiresAt: this.jwtExpiresAt ? this.jwtExpiresAt.toISOString() : null,
      isLoggedIn: this.hasValidJwt(),
      username: username ?? null,
      gatewayUrl: this.gatewayUrl(),
      rememberAvailable: true,
      storedInPlaintext: this.storedInPlaintext,
      lastError: this.lastError,
    };
  }

  private hasValidJwt(bufferMs = 0): boolean {
    if (!this.jwt || !this.jwtExpiresAt) return false;
    return this.jwtExpiresAt.getTime() > this.now().getTime() + bufferMs;
  }

  private clearJwtOnly(): void {
    this.jwt = null;
    this.jwtExpiresAt = null;
  }

  private emitChanged(): void {
    this.emit('changed', this.snapshot());
  }

  private emitExpired(message: string): void {
    this.clearJwtOnly();
    this.lastError = message;
    const snapshot = this.snapshot();
    this.emit('expired', snapshot);
    this.emit('changed', snapshot);
  }

  private loginFailure(message: string, silent: boolean): AigwLoginResult {
    this.clearJwtOnly();
    this.lastError = message;
    if (!silent) this.emitChanged();
    return { ok: false, message, snapshot: this.snapshot() };
  }

  private loadCredentials(): AigwCredentials | null {
    const baseConfig = readAigwBaseConfig(this.config.read());
    const username = readStringField(baseConfig, USERNAME_KEY);
    if (!username) return null;

    const encrypted = readStringField(baseConfig, ENCRYPTED_PASSWORD_KEY);
    if (encrypted) {
      try {
        this.storedInPlaintext = false;
        return { username, password: this.storage.decryptString(Buffer.from(encrypted, 'base64')) };
      } catch {
        this.lastError = 'Stored AIGateway credentials could not be decrypted';
        this.clearPersistedCredentials();
        return null;
      }
    }

    const plaintext = readStringField(baseConfig, PLAINTEXT_PASSWORD_KEY);
    if (!plaintext) return null;
    this.storedInPlaintext = true;
    return { username, password: plaintext };
  }

  private saveCredentials(credentials: AigwCredentials): string | undefined {
    const config = this.config.read();
    const pluginConfig = readPluginConfig(config);
    const baseConfig = readAigwBaseConfig(config);
    baseConfig[USERNAME_KEY] = credentials.username;
    delete baseConfig[ENCRYPTED_PASSWORD_KEY];
    delete baseConfig[PLAINTEXT_PASSWORD_KEY];
    delete baseConfig[STORAGE_KEY];

    if (this.encryptionAvailable()) {
      try {
        baseConfig[ENCRYPTED_PASSWORD_KEY] = this.storage
          .encryptString(credentials.password)
          .toString('base64');
        baseConfig[STORAGE_KEY] = 'safeStorage';
        this.storedInPlaintext = false;
        pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
        config.plugin_config = pluginConfig;
        this.config.write(config);
        return undefined;
      } catch {
        // Fall through to plaintext with an explicit renderer warning.
      }
    }

    baseConfig[PLAINTEXT_PASSWORD_KEY] = credentials.password;
    baseConfig[STORAGE_KEY] = 'plaintext';
    this.storedInPlaintext = true;
    pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
    config.plugin_config = pluginConfig;
    this.config.write(config);
    return 'AIGateway password was saved in plaintext because OS keychain encryption is unavailable.';
  }

  private clearPersistedCredentials(): string | undefined {
    const config = this.config.read();
    const pluginConfig = readPluginConfig(config);
    const baseConfig = readAigwBaseConfig(config);
    delete baseConfig[USERNAME_KEY];
    delete baseConfig[ENCRYPTED_PASSWORD_KEY];
    delete baseConfig[PLAINTEXT_PASSWORD_KEY];
    delete baseConfig[STORAGE_KEY];
    pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
    config.plugin_config = pluginConfig;
    this.config.write(config);
    this.storedInPlaintext = false;
    return undefined;
  }

  private encryptionAvailable(): boolean {
    try {
      return this.storage.isEncryptionAvailable();
    } catch {
      return false;
    }
  }

  private gatewayUrl(): string {
    const gatewayUrl = readStringField(readAigwBaseConfig(this.config.read()), 'gateway_url');
    return gatewayUrl ? normalizeBaseUrl(gatewayUrl) : DEFAULT_GATEWAY_URL;
  }
}

export const aigwSessionService = new AigwSessionService();

function readPluginConfig(config: Record<string, unknown>): Record<string, unknown> {
  return isRecord(config.plugin_config) ? { ...config.plugin_config } : {};
}

function readAigwBaseConfig(config: Record<string, unknown>): Record<string, unknown> {
  const pluginConfig = readPluginConfig(config);
  const value = pluginConfig[AIGW_BASE_PLUGIN];
  return isRecord(value) ? { ...value } : {};
}

function readStringField(value: unknown, key: string): string | undefined {
  if (!isRecord(value)) return undefined;
  const field = value[key];
  return typeof field === 'string' && field.length > 0 ? field : undefined;
}

function parseExpiresAt(value: string | undefined): Date | null {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : new Date(timestamp);
}

function validateGatewayUrl(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value.trim());
  } catch {
    throw new Error('AIGateway URL must be an absolute http or https URL');
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('AIGateway URL must use http or https');
  }
  if (parsed.username || parsed.password) {
    throw new Error('AIGateway URL must not include credentials');
  }
  if (parsed.protocol === 'http:' && !insecureGatewayUrlAllowed(parsed.hostname)) {
    throw new Error('External AIGateway URL must use HTTPS unless it is loopback');
  }
  parsed.hash = '';
  parsed.search = '';
  return normalizeBaseUrl(parsed.toString());
}

function insecureGatewayUrlAllowed(hostname: string): boolean {
  if (process.env['SF_AIGW_ALLOW_INSECURE_EXTERNAL'] === '1') return true;
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (normalized === 'localhost') return true;
  const version = isIP(normalized);
  if (version === 4) return normalized.split('.')[0] === '127';
  if (version === 6) return normalized === '::1';
  return false;
}

function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, '');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function nodeRequestJson(url: string, init?: JsonRequestInit): Promise<JsonResponse> {
  const response = await nodeRequest(url, init);
  let json: unknown = null;
  if (response.body) {
    try {
      json = JSON.parse(response.body);
    } catch {
      json = null;
    }
  }
  return { ...response, json };
}

function nodeRequest(
  url: string,
  init?: JsonRequestInit,
): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const mod = parsed.protocol === 'https:' ? https : http;
    const req = mod.request(
      url,
      {
        method: init?.method ?? 'GET',
        headers: init?.headers,
        timeout: REQUEST_TIMEOUT_MS,
        rejectUnauthorized: false,
      },
      (res) => {
        let body = '';
        res.on('data', (chunk: Buffer) => {
          body += chunk.toString();
        });
        res.on('end', () => resolve({ status: res.statusCode ?? 0, body }));
      },
    );
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('timeout'));
    });
    req.on('error', reject);
    if (init?.body) req.write(init.body);
    req.end();
  });
}

function extractErrorMessage(response: JsonResponse): string | undefined {
  if (isRecord(response.json)) {
    const message = readStringField(response.json, 'message');
    if (message) return message;
    const detail = response.json.detail;
    if (typeof detail === 'string') return detail;
    if (isRecord(detail)) {
      return readStringField(detail, 'message') ?? readStringField(detail, 'code');
    }
  }
  return response.body || undefined;
}
