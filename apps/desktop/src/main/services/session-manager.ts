import { ChildProcess, spawn, execFile } from 'child_process';
import { join } from 'path';
import { writeFileSync, readFileSync, unlinkSync, chmodSync, existsSync, mkdirSync } from 'fs';
import { tmpdir } from 'os';
import net from 'net';
import { randomUUID } from 'crypto';
import { EventEmitter } from 'events';
import { app, dialog, BrowserWindow } from 'electron';
import { is } from '@electron-toolkit/utils';
import { configService } from './config-service';

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

interface ReadyEvent {
  event: 'ready';
  host: string;
  port: number;
  pid: number;
  scheme: string;
}

interface ActiveSession {
  id: string;
  type: SessionType;
  port: number;
  status: SessionStatus;
  createdAt: Date;
  workingDir: string;
  pluginConfig: Record<string, Record<string, unknown>>;
  proxy: ChildProcess | null;
  proxyReady: ReadyEvent | null;
  scriptPath: string | null;
}

const PORT_RANGE_START = 9101;
const PORT_RANGE_SIZE = 100;
const PROXY_READY_TIMEOUT_MS = 15_000;

class SessionManager extends EventEmitter {
  private sessions: Map<string, ActiveSession> = new Map();

  private get sfBin(): string {
    if (!is.dev) {
      return join(app.getPath('userData'), '.venv', 'bin', 'sf');
    }
    return join(configService.serverDir, '.venv', 'bin', 'sf');
  }

  private get serverCwd(): string {
    if (!is.dev) {
      return app.getPath('userData');
    }
    return configService.serverDir;
  }

  // --- Port allocation ---

  private usedPorts(): Set<number> {
    const ports = new Set<number>();
    for (const s of this.sessions.values()) {
      ports.add(s.port);
    }
    return ports;
  }

  private async isPortFree(port: number): Promise<boolean> {
    return new Promise((resolve) => {
      const sock = new net.Socket();
      sock.once('connect', () => {
        sock.destroy();
        resolve(false);
      });
      sock.once('error', () => {
        sock.destroy();
        resolve(true);
      });
      sock.connect(port, '127.0.0.1');
    });
  }

  private async allocatePort(): Promise<number> {
    const used = this.usedPorts();
    for (let i = 0; i < PORT_RANGE_SIZE; i++) {
      const candidate = PORT_RANGE_START + i;
      if (used.has(candidate)) continue;
      if (await this.isPortFree(candidate)) return candidate;
    }
    throw new Error('No free ports available in session range');
  }

  /** Find a random free port by binding to port 0 and reading the assigned port. */
  private async allocateRandomPort(): Promise<number> {
    return new Promise((resolve, reject) => {
      const srv = net.createServer();
      srv.listen(0, '127.0.0.1', () => {
        const addr = srv.address();
        if (addr && typeof addr === 'object') {
          const port = addr.port;
          srv.close(() => resolve(port));
        } else {
          srv.close(() => reject(new Error('Failed to allocate random port')));
        }
      });
      srv.on('error', reject);
    });
  }

  // --- Folder picker ---

  async pickWorkingDir(): Promise<string | null> {
    const win = BrowserWindow.getFocusedWindow();
    if (!win) return null;

    const result = await dialog.showOpenDialog(win, {
      title: 'Choose working directory for Claude session',
      properties: ['openDirectory'],
      defaultPath: app.getPath('home'),
    });

    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
  }

  // --- Session lifecycle ---

  async createSession(
    type: SessionType,
    workingDir: string,
    pluginConfig?: Record<string, Record<string, unknown>>,
  ): Promise<SessionInfo> {
    const id = randomUUID();
    const port = await this.allocatePort();

    // Ensure workingDir exists (e.g. /tmp/sf-<uuid> default)
    if (!existsSync(workingDir)) {
      mkdirSync(workingDir, { recursive: true });
    }

    const session: ActiveSession = {
      id,
      type,
      port,
      status: 'starting',
      createdAt: new Date(),
      workingDir,
      pluginConfig: pluginConfig || {},
      proxy: null,
      proxyReady: null,
      scriptPath: null,
    };

    this.sessions.set(id, session);
    this.emitSessionsChanged();

    try {
      await this.spawnProxy(session, pluginConfig);
      this.openTerminal(session);
      session.status = 'running';
      this.emitSessionsChanged();
    } catch (err) {
      session.status = 'error';
      this.emitSessionsChanged();
      throw err;
    }

    return this.toSessionInfo(session);
  }

  private async spawnProxy(
    session: ActiveSession,
    pluginConfig?: Record<string, Record<string, unknown>>,
  ): Promise<void> {
    // SF server needs its own port (internal only), separate from the
    // claude-frontend proxy port that the CLI connects to.
    const serverPort = await this.allocateRandomPort();
    const config = configService.read();
    const defaults = (config.plugin_config as Record<string, Record<string, unknown>>) || {};

    const proxyConfig = {
      version: config.version || '0.1.0',
      server: {
        host: '127.0.0.1',
        port: serverPort,
        reload: false,
        ssl: false,
      },
      plugins: [
        'tracing',
        'claude-frontend',
        'url4-specs',
      ],
      plugin_config: {
        'tracing': {
          ...(defaults['tracing'] || {}),
          phoenix_launch: false, // connect to shared Phoenix, don't spawn per-session
        },
        'claude-frontend': {
          ...(defaults['claude-frontend'] || {}),
          // User overrides from dialog:
          ...(pluginConfig?.['claude-frontend'] || {}),
          // Forced by session-manager (cannot be overridden):
          listen_host: '127.0.0.1',
          listen_port: session.port,
          session_service_url: 'http://127.0.0.1:9200',
          // All url4/data/backend calls go to the main server
          backend_url: `${(config.server as Record<string, unknown>).ssl ? 'https' : 'http'}://127.0.0.1:${(config.server as Record<string, unknown>).port || 8000}`,
        },
        'url4-specs': defaults['url4-specs'] || {},
      },
    };

    const args = [
      'run',
      '--subprocess',
      '--session-id', session.id,
      '--config-json', JSON.stringify(proxyConfig),
    ];

    return new Promise<void>((resolve, reject) => {
      const child = spawn(this.sfBin, args, {
        cwd: this.serverCwd,
        env: { ...process.env },
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      session.proxy = child;

      const timeout = setTimeout(() => {
        reject(new Error('Proxy ready timeout'));
      }, PROXY_READY_TIMEOUT_MS);

      child.stdout!.on('data', (data: Buffer) => {
        const lines = data.toString().split('\n').filter(Boolean);
        for (const line of lines) {
          try {
            const parsed = JSON.parse(line);
            if (parsed.event === 'ready') {
              clearTimeout(timeout);
              session.proxyReady = parsed as ReadyEvent;
              resolve();
              return;
            }
          } catch {
            // Regular log line
          }
          this.emit('log', session.id, line);
        }
      });

      child.stderr!.on('data', (data: Buffer) => {
        this.emit('log', session.id, data.toString());
      });

      child.on('close', (code, signal) => {
        clearTimeout(timeout);
        this.emit('log', session.id, `Proxy process exited (code=${code}, signal=${signal})`);
        if (session.status !== 'stopping' && session.status !== 'stopped') {
          session.status = 'error';
          session.proxy = null;
          this.emitSessionsChanged();
        }
      });

      child.on('error', (err) => {
        clearTimeout(timeout);
        session.proxy = null;
        session.status = 'error';
        this.emitSessionsChanged();
        reject(err);
      });
    });
  }

  private cliCommand(type: SessionType): string {
    switch (type) {
      case 'claude': return 'claude';
      case 'codex': return 'codex';
      case 'gemini': return 'gemini';
      case 'claude-desktop': return 'claude';
      default: return 'claude';
    }
  }

  private envVarName(type: SessionType): string {
    switch (type) {
      case 'claude':
      case 'claude-desktop':
        return 'ANTHROPIC_BASE_URL';
      case 'codex':
        return 'OPENAI_BASE_URL';
      case 'gemini':
        return 'GEMINI_BASE_URL';
      default:
        return 'ANTHROPIC_BASE_URL';
    }
  }

  private openTerminal(session: ActiveSession): void {
    const baseUrl = `http://127.0.0.1:${session.port}`;
    const cmd = this.cliCommand(session.type);
    const envVar = this.envVarName(session.type);

    // Write a temp script that records its PID before exec'ing the CLI.
    // exec replaces the shell but keeps the same PID, so we can kill it later.
    //
    // Ink (the TUI library Claude Code/Codex/Gemini use) detects color
    // support via COLORTERM / FORCE_COLOR / COLORFGBG. AppleScript's
    // `do script` launches a fresh login shell whose env may not have
    // these set; without them, Ink/chalk emits highlighted regions
    // using ANSI codes that render as solid white blocks on a dark
    // terminal profile (the visible-cell-background effect users see).
    //
    // Setting these explicitly tells Ink:
    //   - COLORTERM=truecolor     → 24-bit color path; cleaner highlights
    //   - FORCE_COLOR=3           → never auto-disable color (truecolor)
    //   - COLORFGBG="15;0"        → "light foreground, dark background"
    //                                 — Ink uses this to pick a palette
    //                                 that doesn't paint white cells
    //   - TERM defaults to xterm-256color if Terminal.app didn't set it
    const scriptPath = join(tmpdir(), `sf-session-${session.id}.sh`);
    const pidPath = join(tmpdir(), `sf-session-${session.id}.pid`);
    const scriptContent = [
      '#!/bin/bash',
      `echo $$ > ${this.shellEscape(pidPath)}`,
      `cd ${this.shellEscape(session.workingDir)}`,
      // Terminal color environment (must be set BEFORE exec so the CLI inherits)
      'export TERM="${TERM:-xterm-256color}"',
      'export COLORTERM="${COLORTERM:-truecolor}"',
      'export FORCE_COLOR="${FORCE_COLOR:-3}"',
      'export COLORFGBG="${COLORFGBG:-15;0}"',
      // Proxy routing
      `export ${envVar}=${this.shellEscape(baseUrl)}`,
      // Terminal-buffer hygiene before launching the TUI.
      //
      // Diagnosis (PTY capture analysis at /tmp/capture-claude-output.py):
      //   - Claude Code does NOT emit \e[?1049h (alternate screen buffer)
      //     on startup, so it runs in INLINE mode.
      //   - Inline-mode redraws use CUF (\e[NC, "cursor right N") to space
      //     between words instead of writing literal characters.
      //   - CUF moves the cursor over cells WITHOUT erasing them, so any
      //     pre-existing content (shell prompt PS1 segments, scrollback,
      //     and crucially the previous frame of Claude's own UI) leaks
      //     through the gaps as visible blocks.
      //   - The single reverse-video cursor cell (\e[7m \e[27m) accumulates
      //     a trail across redraws because old cursor positions are never
      //     overwritten.
      //
      // Mitigations applied here:
      //   1. \ec (RIS) — full terminal reset before anything starts;
      //      wipes screen, scrollback, modes, character sets.
      //   2. \e[?1049h — manually enter the alternate screen buffer.
      //      Cells in alt-screen are guaranteed clear on entry, and the
      //      original screen is restored verbatim when the CLI exits.
      //      Even though Claude itself doesn't request this, the shell
      //      can request it on Claude's behalf — Claude is happy to
      //      draw into whichever buffer is active.
      //   3. \e[2J\e[H — belt-and-suspenders explicit clear inside the
      //      alt-screen so the very first frame draws over a known-clean
      //      canvas (some terminals enter alt-screen with leftover content).
      "printf '\\ec\\e[?1049h\\e[2J\\e[H'",
      `exec ${cmd}`,
    ].join('\n');
    writeFileSync(scriptPath, scriptContent, 'utf-8');
    chmodSync(scriptPath, 0o755);
    session.scriptPath = scriptPath;

    // Open Terminal.app and run the script.
    //
    // The default Terminal.app profile inherits whatever the user has set
    // in Preferences. When that profile uses a swapped/light palette, our
    // CLI tools emit codes that render every cell with a white block —
    // even on a window that "looks" dark — because reverse-video and
    // default-bg interactions break in that profile.
    //
    // Force a known-good dark profile ("Pro" ships with macOS Terminal
    // and has bg=black/fg=light by default, which is what every TUI we
    // care about expects).
    //
    // AppleScript strings use double quotes, so escape any double quotes in the path
    const escapedPath = scriptPath.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    const appleScript = `tell application "Terminal"
  activate
  set newTab to do script "${escapedPath}"
  delay 0.05
  try
    set current settings of newTab to settings set "Pro"
  end try
end tell`;

    this.emit('log', session.id, `Opening terminal: ${scriptPath}`);
    execFile('osascript', ['-e', appleScript], (err, _stdout, stderr) => {
      if (err) {
        this.emit('log', session.id, `ERROR: Failed to open terminal: ${err.message}`);
        if (stderr) this.emit('log', session.id, `osascript stderr: ${stderr}`);
        session.status = 'error';
        this.emitSessionsChanged();
      }
    });
  }

  private shellEscape(s: string): string {
    return `'${s.replace(/'/g, "'\\''")}'`;
  }

  /**
   * Kill the CLI process via its PID file, then close the Terminal window.
   */
  private async killTerminalProcess(session: ActiveSession): Promise<void> {
    const pidPath = join(tmpdir(), `sf-session-${session.id}.pid`);

    // 1. Read PID file and kill the process
    if (existsSync(pidPath)) {
      try {
        const pid = parseInt(readFileSync(pidPath, 'utf-8').trim(), 10);
        if (!isNaN(pid)) {
          this.emit('log', session.id, `Killing CLI process (PID ${pid})`);
          try { process.kill(pid, 'SIGTERM'); } catch { /* already dead */ }

          // Wait then force-kill
          await new Promise((r) => setTimeout(r, 2000));
          try { process.kill(pid, 'SIGKILL'); } catch { /* already dead */ }
        }
      } catch { /* read/parse failed */ }
      try { unlinkSync(pidPath); } catch { /* */ }
    } else {
      this.emit('log', session.id, 'No PID file found — CLI may need manual close');
    }

    // 2. Close Terminal.app windows with no busy tabs
    await new Promise<void>((resolve) => {
      const closeScript = `tell application "Terminal"
  set windowsToClose to {}
  repeat with w in (every window)
    set allDone to true
    repeat with t in (every tab of w)
      if busy of t is true then
        set allDone to false
        exit repeat
      end if
    end repeat
    if allDone then set end of windowsToClose to w
  end repeat
  repeat with w in windowsToClose
    close w
  end repeat
end tell`;
      execFile('osascript', ['-e', closeScript], () => resolve());
    });

    // 3. Clean up temp script
    if (session.scriptPath) {
      try { unlinkSync(session.scriptPath); } catch { /* */ }
      session.scriptPath = null;
    }
  }

  async terminateSession(id: string): Promise<void> {
    const session = this.sessions.get(id);
    if (!session) return;

    session.status = 'stopping';
    this.emitSessionsChanged();

    // Kill the CLI process in the terminal first
    await this.killTerminalProcess(session);

    // Then kill the proxy
    if (session.proxy) {
      session.proxy.kill('SIGTERM');
      await new Promise<void>((resolve) => {
        const timer = setTimeout(() => {
          try { session.proxy?.kill('SIGKILL'); } catch { /* */ }
          resolve();
        }, 5000);
        session.proxy!.once('close', () => {
          clearTimeout(timer);
          resolve();
        });
      });
      session.proxy = null;
    }

    session.status = 'stopped';
    this.emitSessionsChanged();
  }

  async terminateAll(): Promise<void> {
    const ids = [...this.sessions.keys()];
    await Promise.all(ids.map((id) => this.terminateSession(id)));
  }

  listSessions(): SessionInfo[] {
    return [...this.sessions.values()].map((s) => this.toSessionInfo(s));
  }

  removeSession(id: string): void {
    this.sessions.delete(id);
    this.emitSessionsChanged();
  }

  updateSession(
    id: string,
    workingDir: string,
    pluginConfig?: Record<string, Record<string, unknown>>,
  ): SessionInfo {
    const session = this.sessions.get(id);
    if (!session) throw new Error(`Session ${id} not found`);
    if (session.status !== 'stopped' && session.status !== 'error') {
      throw new Error('Can only edit stopped or error sessions');
    }
    session.workingDir = workingDir;
    session.pluginConfig = pluginConfig || {};
    if (!existsSync(workingDir)) {
      mkdirSync(workingDir, { recursive: true });
    }
    this.emitSessionsChanged();
    return this.toSessionInfo(session);
  }

  async restartSession(id: string): Promise<SessionInfo> {
    const session = this.sessions.get(id);
    if (!session) throw new Error(`Session ${id} not found`);
    if (session.status !== 'stopped' && session.status !== 'error') {
      throw new Error('Can only restart stopped or error sessions');
    }
    session.port = await this.allocatePort();
    session.status = 'starting';
    session.createdAt = new Date();
    this.emitSessionsChanged();

    try {
      await this.spawnProxy(session, session.pluginConfig);
      this.openTerminal(session);
      session.status = 'running';
      this.emitSessionsChanged();
    } catch (err) {
      session.status = 'error';
      this.emitSessionsChanged();
      throw err;
    }

    return this.toSessionInfo(session);
  }

  private toSessionInfo(s: ActiveSession): SessionInfo {
    return {
      id: s.id,
      type: s.type,
      port: s.port,
      status: s.status,
      createdAt: s.createdAt.toISOString(),
      workingDir: s.workingDir,
      pluginConfig: s.pluginConfig,
    };
  }

  private emitSessionsChanged(): void {
    this.emit('sessionsChanged', this.listSessions());
  }
}

export const sessionManager = new SessionManager();
