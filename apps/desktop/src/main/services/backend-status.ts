/**
 * BackendStatusService — polls /backends/status and broadcasts changes.
 *
 * Runs in the Electron main process. Polls the SF server every 30s,
 * detects state transitions (healthy → reauth, reauth → healthy),
 * and emits events that the IPC layer forwards to the renderer.
 */

import { EventEmitter } from 'events';
import { execFile } from 'child_process';
import https from 'https';
import http from 'http';
import { Notification } from 'electron';
import { configService } from './config-service';
import { desktopSecretHeader } from './desktop-secret';

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
}

export type BackendStatusMap = Record<string, BackendHealth>;

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

const POLL_INTERVAL_MS = 30_000;
const POLL_TIMEOUT_MS = 25_000;

class BackendStatusService extends EventEmitter {
  private timer: ReturnType<typeof setInterval> | null = null;
  private serverUrl: string | null = null;
  private previous: BackendStatusResponse = {};

  /** Start polling. Call after the server is ready. */
  start(serverUrl: string): void {
    this.serverUrl = serverUrl;
    this.poll(); // immediate first poll
    this.timer = setInterval(() => this.poll(), POLL_INTERVAL_MS);
  }

  /** Stop polling. */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.serverUrl = null;
    this.previous = {};
  }

  /** Get current status (last polled). */
  getStatus(): BackendStatusResponse {
    return this.previous;
  }

  /** Get the SF server base URL the service is currently polling, if any. */
  getServerUrl(): string | null {
    return this.serverUrl;
  }

  /** Force an immediate poll. */
  async refresh(): Promise<BackendStatusResponse> {
    return this.poll();
  }

  /** Open a terminal with the re-auth command for a backend. */
  authenticate(backend: string): void {
    const health = backendMap(this.previous)[backend];
    const command = health?.cli_command;
    if (!command) return;

    if (process.platform === 'darwin') {
      // macOS: use osascript to open Terminal.app with the command
      execFile('osascript', [
        '-e',
        `tell application "Terminal" to do script "${escapeAppleScriptString(command)}"`,
        '-e',
        'tell application "Terminal" to activate',
      ]);
    } else if (process.platform === 'linux') {
      // Linux: try x-terminal-emulator
      execFile('x-terminal-emulator', ['-e', command]);
    }
  }

  private async poll(): Promise<BackendStatusResponse> {
    if (!this.serverUrl) return {};

    try {
      const data = await this.fetchStatus();
      this.detectTransitions(data);
      this.previous = data;
      this.emit('statusChanged', data);
      return data;
    } catch {
      // Server not reachable — keep previous state
      return this.previous;
    }
  }

  private detectTransitions(current: BackendStatusResponse): void {
    if (
      isStatusV2(current) &&
      current.gateway.mode === 'external' &&
      !current.gateway.authenticated
    ) {
      this.previous = current;
      return;
    }

    const currentBackends = backendMap(current);
    const previousBackends = backendMap(this.previous);
    for (const [name, health] of Object.entries(currentBackends)) {
      const prev = previousBackends[name];
      if (!prev) continue;

      // healthy → reauth: show native notification
      if (prev.action === 'healthy' && health.action === 'reauth') {
        this.showNotification(
          `${name} needs re-authentication`,
          health.help_text || health.error || `Run: ${health.cli_command}`,
        );
        this.emit('alert', { backend: name, type: 'reauth', health });
      }

      // healthy → rate_limited
      if (prev.action === 'healthy' && health.action === 'rate_limited') {
        this.emit('alert', { backend: name, type: 'rate_limited', health });
      }

      // reauth/rate_limited → healthy: recovery
      if (
        (prev.action === 'reauth' || prev.action === 'rate_limited') &&
        health.action === 'healthy'
      ) {
        this.emit('alert', { backend: name, type: 'recovered', health });
      }
    }
  }

  private showNotification(title: string, body: string): void {
    if (Notification.isSupported()) {
      new Notification({ title, body }).show();
    }
  }

  async loginGateway(
    username: string,
    password: string,
  ): Promise<{ ok: boolean; message?: string }> {
    if (!this.serverUrl) return { ok: false, message: 'SF server is not running' };
    try {
      const result = await nodeFetch(`${this.serverUrl}/aigateway/session/login`, {
        method: 'POST',
        headers: { ...desktopSecretHeader(), 'content-type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (result.status >= 200 && result.status < 300) {
        await this.refresh();
        return { ok: true };
      }
      return { ok: false, message: extractErrorMessage(result.body) ?? `HTTP ${result.status}` };
    } catch (e) {
      return { ok: false, message: e instanceof Error ? e.message : String(e) };
    }
  }

  async logoutGateway(): Promise<void> {
    if (!this.serverUrl) return;
    await nodeFetch(`${this.serverUrl}/aigateway/session/logout`, {
      method: 'POST',
      headers: desktopSecretHeader(),
    });
    await this.refresh();
  }

  private fetchStatus(): Promise<BackendStatusResponse> {
    return new Promise((resolve, reject) => {
      const url = `${this.serverUrl}/backends/status`;
      const parsed = new URL(url);
      const mod = parsed.protocol === 'https:' ? https : http;

      const req = mod.get(
        {
          hostname: parsed.hostname,
          port: parsed.port,
          path: parsed.pathname,
          timeout: POLL_TIMEOUT_MS,
          rejectUnauthorized: false,
          headers: {
            Accept: 'application/vnd.screamingface.backends-status+json;version=2',
            ...desktopSecretHeader(),
          },
        },
        (res) => {
          let data = '';
          res.on('data', (chunk: Buffer) => {
            data += chunk.toString();
          });
          res.on('end', () => {
            try {
              resolve(parseBackendStatus(JSON.parse(data)));
            } catch {
              reject(new Error(`Invalid JSON from /backends/status`));
            }
          });
        },
      );

      req.on('timeout', () => {
        req.destroy();
        reject(new Error('timeout'));
      });
      req.on('error', reject);
    });
  }
}

export const backendStatusService = new BackendStatusService();

export function isStatusV2(value: unknown): value is BackendStatusV2 {
  if (!isRecord(value) || value.version !== 2) return false;
  return isGatewayStatus(value.gateway);
}

export function backendMap(value: BackendStatusResponse): BackendStatusMap {
  if (isStatusV2(value)) return value.backends ?? {};
  return value;
}

export function parseBackendStatus(
  value: unknown,
  desktopGatewayConfig?: Record<string, unknown>,
): BackendStatusResponse {
  if (isStatusV2(value as BackendStatusResponse)) return value as BackendStatusV2;
  if (isLegacyStatusMap(value)) {
    if (desktopConfigGatewayMode(desktopGatewayConfig) === 'external') {
      return {
        version: 2,
        gateway: {
          mode: 'external',
          managed_by_runner: false,
          reachable: false,
          authenticated: false,
          auth_required: true,
          url: desktopConfigGatewayUrl(desktopGatewayConfig),
        },
        action: 'gateway_misconfigured',
        message: 'SF server is out of date — update required to use external gateway mode',
      };
    }
    return value;
  }
  throw new Error('Unsupported /backends/status response');
}

function isLegacyStatusMap(value: unknown): value is BackendStatusMap {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  return !Object.prototype.hasOwnProperty.call(value, 'version');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isGatewayStatus(value: unknown): value is BackendStatusV2['gateway'] {
  if (!isRecord(value)) return false;
  return (
    (value.mode === 'local_managed' || value.mode === 'external') &&
    typeof value.managed_by_runner === 'boolean' &&
    typeof value.reachable === 'boolean' &&
    typeof value.authenticated === 'boolean' &&
    typeof value.auth_required === 'boolean' &&
    typeof value.url === 'string'
  );
}

function desktopConfigGatewayMode(
  desktopGatewayConfig?: Record<string, unknown>,
): 'local_managed' | 'external' {
  const base = desktopGatewayConfig ?? desktopConfigAigwBase();
  return base.mode === 'external' ? 'external' : 'local_managed';
}

function desktopConfigGatewayUrl(desktopGatewayConfig?: Record<string, unknown>): string {
  const base = desktopGatewayConfig ?? desktopConfigAigwBase();
  return typeof base.gateway_url === 'string' ? base.gateway_url : 'http://127.0.0.1:9105';
}

function desktopConfigAigwBase(): Record<string, unknown> {
  const config = configService.read();
  const pluginConfig = config.plugin_config;
  if (typeof pluginConfig !== 'object' || pluginConfig === null || Array.isArray(pluginConfig))
    return {};
  const base = (pluginConfig as Record<string, unknown>)['aigw-base'];
  if (typeof base !== 'object' || base === null || Array.isArray(base)) return {};
  return base as Record<string, unknown>;
}

interface NodeFetchInit {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}

function nodeFetch(url: string, init?: NodeFetchInit): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const mod = parsed.protocol === 'https:' ? https : http;
    const req = mod.request(
      url,
      {
        method: init?.method ?? 'GET',
        headers: init?.headers,
        timeout: POLL_TIMEOUT_MS,
        rejectUnauthorized: false,
      },
      (res) => {
        let data = '';
        res.on('data', (chunk: Buffer) => {
          data += chunk.toString();
        });
        res.on('end', () => resolve({ status: res.statusCode ?? 0, body: data }));
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

function extractErrorMessage(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown; message?: unknown };
    if (typeof parsed.message === 'string') return parsed.message;
    const detail = unwrapFastApiDetail(parsed.detail);
    if (Array.isArray(detail)) {
      const first = detail.find((entry) => typeof entry === 'object' && entry !== null);
      if (first) {
        const record = first as { loc?: unknown; msg?: unknown };
        const msg = typeof record.msg === 'string' ? record.msg : undefined;
        if (!msg) return undefined;
        const loc = Array.isArray(record.loc)
          ? record.loc
              .filter((part) => typeof part === 'string')
              .slice(1)
              .join('.')
          : '';
        return loc ? `${loc}: ${msg}` : msg;
      }
      return undefined;
    }
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail !== null) {
      const message = (detail as { message?: unknown; code?: unknown }).message;
      if (typeof message === 'string') return message;
      const code = (detail as { code?: unknown }).code;
      if (typeof code === 'string') return code;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

function unwrapFastApiDetail(detail: unknown): unknown {
  if (typeof detail === 'object' && detail !== null && 'detail' in detail) {
    return (detail as { detail?: unknown }).detail;
  }
  return detail;
}

export const __testing = { extractErrorMessage };

export function escapeAppleScriptString(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\r/g, '\\r')
    .replace(/\n/g, '\\n');
}
