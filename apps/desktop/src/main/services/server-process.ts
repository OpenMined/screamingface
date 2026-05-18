import { ChildProcess, spawn, execFileSync, execFile as execFileCb } from 'child_process';
import { join } from 'path';
import { EventEmitter } from 'events';
import { promisify } from 'util';
import https from 'https';
import http from 'http';
import { app } from 'electron';
import { is } from '@electron-toolkit/utils';
import { configService } from './config-service';
import { resolveUv } from './uv-resolver';

const execFileAsync = promisify(execFileCb);

export type ServerStatus = 'stopped' | 'starting' | 'ready' | 'error' | 'restarting';

interface ReadyEvent {
  event: 'ready';
  host: string;
  port: number;
  pid: number;
  scheme: string;
}

class ServerProcess extends EventEmitter {
  private child: ChildProcess | null = null;
  private status: ServerStatus = 'stopped';
  private healthTimer: ReturnType<typeof setInterval> | null = null;
  private healthFailures = 0;
  private restartCount = 0;
  private readyInfo: ReadyEvent | null = null;
  private stopping = false;

  private static MAX_HEALTH_FAILURES = 3;
  private static MAX_RESTARTS = 3;
  private static HEALTH_INTERVAL_MS = 10_000;
  private static RESTART_DELAY_MS = 2_000;

  private get serverDir(): string {
    return configService.serverDir;
  }

  private get sfBin(): string {
    if (!is.dev) {
      return join(app.getPath('userData'), '.venv', 'bin', 'sf');
    }
    return join(this.serverDir, '.venv', 'bin', 'sf');
  }

  /** Writable directory used as cwd when spawning the server. */
  private get serverCwd(): string {
    if (!is.dev) {
      return app.getPath('userData');
    }
    return this.serverDir;
  }

  private get gatewayProjectDir(): string {
    if (!is.dev) {
      return join(app.getPath('userData'), 'aigateway');
    }
    return join(this.serverDir, '..', 'aigateway');
  }

  private get gatewayDatabasePath(): string {
    return join(app.getPath('userData'), 'aigateway', 'aigateway.db');
  }

  private serverEnv(): NodeJS.ProcessEnv {
    const env: NodeJS.ProcessEnv = (({ VIRTUAL_ENV: _drop, ...inherited }) => inherited)(
      process.env,
    );
    env.SF_AIGW_RUNNER__AIGATEWAY_DIR = this.gatewayProjectDir;
    env.SF_AIGW_RUNNER__DATABASE_PATH = this.gatewayDatabasePath;
    env.SF_AIGW_RUNNER__AUTH_ENABLED = 'false';
    const uvBin = resolveUv();
    if (uvBin) env.SF_AIGW_RUNNER__UV_BIN = uvBin;
    return env;
  }

  private setStatus(s: ServerStatus): void {
    this.status = s;
    this.emit('status', s);
  }

  getStatus(): { status: ServerStatus; info: ReadyEvent | null } {
    return { status: this.status, info: this.readyInfo };
  }

  /**
   * Check if any enabled plugin requires root privileges by querying
   * the `sf plugin list --json` CLI output.
   */
  private needsRoot(): boolean {
    try {
      const raw = execFileSync(this.sfBin, ['plugin', 'list', '--json'], {
        cwd: this.serverCwd,
        timeout: 10_000,
      }).toString();
      const plugins = JSON.parse(raw) as Record<string, { requires_root?: boolean }>;
      const config = configService.read();
      const enabled = (config.plugins ?? []) as string[];
      return enabled.some((name) => plugins[name]?.requires_root === true);
    } catch {
      return false;
    }
  }

  /**
   * Prompt for the admin password via a native macOS dialog.
   * Returns null if the user cancels.
   */
  private async promptForPassword(): Promise<string | null> {
    try {
      const { stdout } = await execFileAsync('osascript', [
        '-e',
        'display dialog "ScreamingFace needs administrator privileges for an enabled plugin." default answer "" with hidden answer with title "ScreamingFace" buttons {"Cancel", "OK"} default button "OK"',
        '-e',
        'text returned of result',
      ]);
      return stdout.trim() || null;
    } catch {
      return null; // User pressed Cancel
    }
  }

  async start(): Promise<boolean> {
    if (this.child || this.status === 'starting') return false;

    this.setStatus('starting');
    this.readyInfo = null;
    this.stopping = false;

    const config = configService.read();
    const configJson = JSON.stringify(config);
    const args = ['run', '--subprocess', '--config-json', configJson, '--host', '127.0.0.1'];
    const env = this.serverEnv();

    // If a plugin requires root and we're not already root, elevate via sudo
    const elevate = this.needsRoot() && process.getuid?.() !== 0;
    let child: ChildProcess;

    if (elevate) {
      const password = await this.promptForPassword();
      if (!password) {
        this.setStatus('stopped');
        this.emit('log', 'Administrator authentication cancelled');
        return false;
      }

      // Use sudo -S to read password from stdin; stdout/stderr stream normally
      child = spawn('sudo', ['-S', this.sfBin, ...args], {
        cwd: this.serverCwd,
        env,
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      child.stdin!.write(password + '\n');
      child.stdin!.end();
    } else {
      child = spawn(this.sfBin, args, {
        cwd: this.serverCwd,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    }

    this.child = child;

    child.stdout!.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n').filter(Boolean);
      for (const line of lines) {
        this.handleStdoutLine(line);
      }
    });

    child.stderr!.on('data', (data: Buffer) => {
      this.emit('log', data.toString());
    });

    child.on('close', (code, signal) => {
      this.stopHealthCheck();
      this.child = null;
      this.readyInfo = null;

      // Expected shutdown — stop() or restart() initiated this kill
      if (this.stopping) return;

      if (code !== 0 && code !== null) {
        this.setStatus('error');
        this.emit('log', `Server exited with code ${code}`);
      } else if (signal) {
        this.setStatus('error');
        this.emit('log', `Server killed by signal ${signal}`);
      } else {
        this.setStatus('stopped');
      }
    });

    child.on('error', (err) => {
      this.emit('log', `Failed to start server: ${err.message}`);
      this.child = null;
      this.setStatus('error');
    });

    return true;
  }

  async stop(): Promise<void> {
    this.stopHealthCheck();
    if (!this.child) return;

    this.stopping = true;
    const wasRestarting = this.status === 'restarting';
    const child = this.child;
    this.child = null;
    this.readyInfo = null;

    // Wait for the process to actually exit after SIGTERM
    await new Promise<void>((resolve) => {
      child.once('close', () => resolve());
      child.kill('SIGTERM');
      // Fallback: force-kill after 5s if it hasn't exited
      setTimeout(() => {
        try {
          child.kill('SIGKILL');
        } catch {
          /* already dead */
        }
        resolve();
      }, 5000);
    });

    this.stopping = false;
    // Don't overwrite 'restarting' status — start() will set 'starting' next
    if (!wasRestarting) {
      this.setStatus('stopped');
    }
  }

  async restart(): Promise<void> {
    this.setStatus('restarting');
    this.restartCount = 0;
    await this.stop();
    await this.start();
  }

  private handleStdoutLine(line: string): void {
    try {
      const parsed = JSON.parse(line);
      if (parsed.event === 'ready') {
        this.readyInfo = parsed as ReadyEvent;
        this.setStatus('ready');
        this.restartCount = 0;
        this.startHealthCheck();
        this.emit('log', `Server ready at ${parsed.scheme}://${parsed.host}:${parsed.port}`);
        return;
      }
    } catch {
      // Not JSON — regular log line
    }
    this.emit('log', line);
  }

  private startHealthCheck(): void {
    this.stopHealthCheck();
    this.healthFailures = 0;

    // Delay first check — ready event fires during lifespan startup,
    // uvicorn may not be accepting connections for another moment
    this.healthTimer = setTimeout(() => {
      this.healthTimer = setInterval(async () => {
        this.runHealthCheck();
      }, ServerProcess.HEALTH_INTERVAL_MS);
      this.runHealthCheck();
    }, 2000) as ReturnType<typeof setInterval>;
  }

  private async runHealthCheck(): Promise<void> {
    if (!this.readyInfo || this.stopping) return;
    try {
      const ok = await this.pingHealth();
      if (ok) {
        this.healthFailures = 0;
      } else {
        this.onHealthFailure();
      }
    } catch {
      this.onHealthFailure();
    }
  }

  private pingHealth(): Promise<boolean> {
    return new Promise((resolve) => {
      if (!this.readyInfo) {
        resolve(false);
        return;
      }

      const { scheme, host, port } = this.readyInfo;
      const checkHost = host === '0.0.0.0' ? '127.0.0.1' : host;
      const url = `${scheme}://${checkHost}:${port}/health`;
      const mod = scheme === 'https' ? https : http;

      const req = mod.get(
        {
          hostname: checkHost,
          port,
          path: '/health',
          timeout: 5000,
          // Accept self-signed certs for local health checks
          rejectUnauthorized: false,
        },
        (res) => {
          res.resume();
          if (res.statusCode === 200) {
            resolve(true);
          } else {
            this.emit('log', `Health check ${url} returned ${res.statusCode}`);
            resolve(false);
          }
        },
      );

      req.on('timeout', () => {
        this.emit('log', `Health check ${url} timed out`);
        req.destroy();
        resolve(false);
      });
      req.on('error', (err) => {
        this.emit('log', `Health check ${url} error: ${err.message}`);
        resolve(false);
      });
    });
  }

  private stopHealthCheck(): void {
    if (this.healthTimer) {
      clearInterval(this.healthTimer);
      this.healthTimer = null;
    }
  }

  private onHealthFailure(): void {
    this.healthFailures++;
    this.emit(
      'log',
      `Health check failed (${this.healthFailures}/${ServerProcess.MAX_HEALTH_FAILURES})`,
    );

    if (this.healthFailures >= ServerProcess.MAX_HEALTH_FAILURES) {
      if (this.restartCount < ServerProcess.MAX_RESTARTS) {
        this.restartCount++;
        this.emit(
          'log',
          `Auto-restarting (attempt ${this.restartCount}/${ServerProcess.MAX_RESTARTS})...`,
        );
        setTimeout(() => this.autoRestart(), ServerProcess.RESTART_DELAY_MS);
      } else {
        this.setStatus('error');
        this.emit('log', 'Max restart attempts reached. Server is down.');
      }
    }
  }

  private async autoRestart(): Promise<void> {
    this.setStatus('restarting');
    // Don't reset restartCount here — only restart() (user-initiated) resets it
    await this.stop();
    await this.start();
  }
}

export const serverProcess = new ServerProcess();
