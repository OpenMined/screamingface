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
  auth_kind?: 'cli' | 'browser' | 'import';
}

export type BackendStatusMap = Record<string, BackendHealth>;

const POLL_INTERVAL_MS = 30_000;
const POLL_TIMEOUT_MS = 25_000;

class BackendStatusService extends EventEmitter {
  private timer: ReturnType<typeof setInterval> | null = null;
  private serverUrl: string | null = null;
  private previous: BackendStatusMap = {};

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
  getStatus(): BackendStatusMap {
    return this.previous;
  }

  /** Get the SF server base URL the service is currently polling, if any. */
  getServerUrl(): string | null {
    return this.serverUrl;
  }

  /** Force an immediate poll. */
  async refresh(): Promise<BackendStatusMap> {
    return this.poll();
  }

  /** Open a terminal with the re-auth command for a backend. */
  authenticate(backend: string): void {
    const health = this.previous[backend];
    const command = health?.cli_command;
    if (!command) return;

    if (process.platform === 'darwin') {
      // macOS: use osascript to open Terminal.app with the command
      execFile('osascript', [
        '-e',
        `tell application "Terminal" to do script "${command}"`,
        '-e',
        'tell application "Terminal" to activate',
      ]);
    } else if (process.platform === 'linux') {
      // Linux: try x-terminal-emulator
      execFile('x-terminal-emulator', ['-e', command]);
    }
  }

  private async poll(): Promise<BackendStatusMap> {
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

  private detectTransitions(current: BackendStatusMap): void {
    for (const [name, health] of Object.entries(current)) {
      const prev = this.previous[name];
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

  private fetchStatus(): Promise<BackendStatusMap> {
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
        },
        (res) => {
          let data = '';
          res.on('data', (chunk: Buffer) => {
            data += chunk.toString();
          });
          res.on('end', () => {
            try {
              resolve(JSON.parse(data) as BackendStatusMap);
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
