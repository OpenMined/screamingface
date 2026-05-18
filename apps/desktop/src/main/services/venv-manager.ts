import { spawn, execFile, execFileSync } from 'child_process';
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'fs';
import { join } from 'path';
import { EventEmitter } from 'events';
import { app } from 'electron';
import { is } from '@electron-toolkit/utils';
import { resolveUv } from './uv-resolver';
import { configService } from './config-service';
import { log } from '../debug-log';

export interface DiscoveredPlugin {
  state: 'enabled' | 'available';
  version: string | null;
  description: string | null;
}

export type VenvStatus = 'unknown' | 'checking' | 'missing' | 'creating' | 'ready' | 'error';

class VenvManager extends EventEmitter {
  private status: VenvStatus = 'unknown';
  private uvBin: string | null = null;
  private syncing = false;

  private get serverDir(): string {
    return configService.serverDir;
  }

  /** In production, uv commands run from userData (writable) instead of the read-only bundle. */
  private get projectDir(): string {
    if (!is.dev) {
      return app.getPath('userData');
    }
    return this.serverDir;
  }

  private get venvDir(): string {
    return join(this.projectDir, '.venv');
  }

  private get pythonBin(): string {
    return join(this.venvDir, 'bin', 'python');
  }

  private get bundledPythonBin(): string | null {
    if (is.dev) return null;
    const bundledPython = join(process.resourcesPath, 'server', 'python', 'bin', 'python3.12');
    return existsSync(bundledPython) ? bundledPython : null;
  }

  private get gatewayProjectDir(): string {
    return join(app.getPath('userData'), 'aigateway');
  }

  private get gatewayVenvDir(): string {
    return join(this.gatewayProjectDir, '.venv');
  }

  private get gatewayPythonBin(): string {
    return join(this.gatewayVenvDir, 'bin', 'python');
  }

  private setStatus(s: VenvStatus): void {
    log(`[venv] status: ${this.status} -> ${s}`);
    this.status = s;
    this.emit('status', s);
  }

  getStatus(): VenvStatus {
    return this.status;
  }

  async detect(): Promise<{
    status: VenvStatus;
    uvFound: boolean;
    needsSync: boolean;
    autoBootstrap: boolean;
  }> {
    log(`[venv] detect() called`);
    log(`[venv] serverDir=${this.serverDir} projectDir=${this.projectDir} venvDir=${this.venvDir}`);
    this.setStatus('checking');
    this.uvBin = resolveUv();
    log(`[venv] uvBin=${this.uvBin}`);

    if (!this.uvBin) {
      this.setStatus('error');
      return { status: 'error', uvFound: false, needsSync: false, autoBootstrap: false };
    }

    log(`[venv] pythonBin=${this.pythonBin} exists=${existsSync(this.pythonBin)}`);
    if (existsSync(this.pythonBin)) {
      try {
        const pyVer = execFileSync(this.pythonBin, ['--version'], { encoding: 'utf-8' });
        log(`[venv] python --version: ${pyVer.trim()}`);
        this.setStatus('ready');
        const needsSync = this.needsResync() || (!is.dev && !existsSync(this.gatewayPythonBin));
        log(`[venv] needsResync=${needsSync}`);
        return { status: 'ready', uvFound: true, needsSync, autoBootstrap: false };
      } catch {
        this.setStatus('error');
        return { status: 'error', uvFound: true, needsSync: false, autoBootstrap: false };
      }
    }

    this.setStatus('missing');
    log(`[venv] detect result: missing, autoBootstrap=${!is.dev}`);
    return { status: 'missing', uvFound: true, needsSync: false, autoBootstrap: !is.dev };
  }

  async create(): Promise<boolean> {
    log(`[venv] create() called`);
    if (!this.uvBin) {
      this.setStatus('error');
      return false;
    }

    this.setStatus('creating');
    const args = [this.uvBin, 'venv', this.venvDir];

    // Use bundled Python interpreter in production
    if (!is.dev) {
      const bundledPython = this.bundledPythonBin;
      if (bundledPython) {
        args.push('--python', bundledPython);
      }
    }

    log(`[venv] create() spawning: ${args.join(' ')}`);
    // Suppress ready status — sync() still needs to run to install the sf entry point
    const ok = await this.runUvCommand(args, undefined, { suppressReady: true });
    log(`[venv] create() result=${ok}`);
    return ok;
  }

  async sync(extra?: string): Promise<boolean> {
    log(`[venv] sync() called, extra=${extra}`);
    if (this.syncing) {
      log(`[venv] sync already in progress`);
      return false;
    }
    if (!this.uvBin) {
      this.setStatus('error');
      return false;
    }

    this.syncing = true;
    try {
      let extraEnv: Record<string, string> | undefined;

      // In production, copy pyproject.toml + uv.lock to the writable projectDir
      // so uv sync can run from there (the bundle is read-only)
      if (!is.dev) {
        log(`[venv] sync: copying project files...`);
        this.copyProjectFiles();

        // Extract bundled wheel cache (async) and set up offline env vars
        const cacheDir = join(app.getPath('userData'), 'uv-cache');
        log(`[venv] sync: extracting cache to ${cacheDir}`);
        try {
          await this.extractCacheIfNeeded(cacheDir);
          log(`[venv] sync: cache extraction done`);
        } catch (err) {
          log(`[venv] sync: cache extraction failed: ${err}`);
          // Non-fatal: uv will fall back to downloading
        }
        extraEnv = { UV_CACHE_DIR: cacheDir, UV_OFFLINE: '1' };
      }

      const args = [this.uvBin, 'sync'];
      if (!is.dev) {
        const bundledPython = this.bundledPythonBin;
        if (bundledPython) args.push('--python', bundledPython);
        args.push('--no-install-project');
      }
      if (extra) args.push('--extra', extra);

      log(`[venv] sync: spawning ${args.join(' ')}`);
      // In production, suppress ready until the project install completes
      const ok = await this.runUvCommand(args, extraEnv, { suppressReady: !is.dev });
      log(`[venv] sync() result=${ok}`);

      // Install the project package (sf entry point) from the bundled source.
      // Don't pass extraEnv here — UV_OFFLINE blocks hatchling download needed for build.
      // This runUvCommand WILL emit ready (no suppressReady) — the final signal.
      if (ok && !is.dev) {
        const serverSrc = join(process.resourcesPath, 'server');
        const installArgs = [this.uvBin, 'pip', 'install', '--no-deps', serverSrc];
        log(`[venv] installing project from ${serverSrc}`);
        const installOk = await this.runUvCommand(installArgs, undefined, { suppressReady: true });
        log(`[venv] project install result=${installOk}`);
        if (!installOk) return false;

        const gatewayOk = await this.syncGatewayProject(extraEnv);
        log(`[venv] gateway project sync result=${gatewayOk}`);
        if (!gatewayOk) return false;

        this.writeVersionStamp();
        this.setStatus('ready');
      }

      return ok;
    } finally {
      this.syncing = false;
    }
  }

  async listPackages(): Promise<Array<{ name: string; version: string }>> {
    if (!this.uvBin) return [];

    try {
      const output = execFileSync(this.uvBin, ['pip', 'list', '--format', 'json'], {
        cwd: this.projectDir,
        encoding: 'utf-8',
        env: { ...process.env, VIRTUAL_ENV: this.venvDir },
      });
      return JSON.parse(output);
    } catch {
      return [];
    }
  }

  async discoverPlugins(): Promise<Record<string, DiscoveredPlugin>> {
    const sfBin = join(this.venvDir, 'bin', 'sf');
    if (!existsSync(sfBin)) return {};

    return new Promise((resolve) => {
      execFile(
        sfBin,
        ['plugin', 'list', '--json'],
        {
          cwd: this.projectDir,
          encoding: 'utf-8',
          timeout: 10_000,
          env: { ...process.env, VIRTUAL_ENV: this.venvDir },
        },
        (error, stdout) => {
          if (error) {
            resolve({});
            return;
          }
          try {
            resolve(JSON.parse(stdout));
          } catch {
            resolve({});
          }
        },
      );
    });
  }

  private runUvCommand(
    args: string[],
    extraEnv?: Record<string, string>,
    opts?: { suppressReady?: boolean; cwd?: string; venvDir?: string },
  ): Promise<boolean> {
    return new Promise((resolve) => {
      const [cmd, ...rest] = args;
      const env: Record<string, string | undefined> = {
        ...process.env,
        VIRTUAL_ENV: opts?.venvDir ?? this.venvDir,
        ...extraEnv,
      };

      const child = spawn(cmd, rest, {
        cwd: opts?.cwd ?? this.projectDir,
        env,
      });

      child.stdout.on('data', (data: Buffer) => {
        this.emit('progress', data.toString());
      });

      child.stderr.on('data', (data: Buffer) => {
        this.emit('progress', data.toString());
      });

      child.on('close', (code) => {
        if (code === 0) {
          if (!opts?.suppressReady) this.setStatus('ready');
          resolve(true);
        } else {
          log(`[venv] command failed (${code}): ${cmd} ${rest.join(' ')}`);
          this.setStatus('error');
          resolve(false);
        }
      });

      child.on('error', (err) => {
        log(`[venv] command error: ${err.message}`);
        this.setStatus('error');
        resolve(false);
      });
    });
  }

  /** Copy pyproject.toml and uv.lock from the read-only bundle to writable userData. */
  private copyProjectFiles(): void {
    const dest = app.getPath('userData');
    for (const file of ['pyproject.toml', 'uv.lock']) {
      const src = join(process.resourcesPath, 'server', file);
      const dst = join(dest, file);
      if (existsSync(src)) {
        copyFileSync(src, dst);
      }
    }
  }

  private async syncGatewayProject(extraEnv?: Record<string, string>): Promise<boolean> {
    if (!this.uvBin) return false;
    this.copyGatewayProjectFiles();

    const syncArgs = [this.uvBin, 'sync'];
    const bundledPython = this.bundledPythonBin;
    if (bundledPython) syncArgs.push('--python', bundledPython);
    syncArgs.push('--no-install-project');

    const syncOk = await this.runUvCommand(syncArgs, extraEnv, {
      suppressReady: true,
      cwd: this.gatewayProjectDir,
      venvDir: this.gatewayVenvDir,
    });
    if (!syncOk) return false;

    return this.runUvCommand(
      [this.uvBin, 'pip', 'install', '--no-deps', this.gatewayProjectDir],
      undefined,
      {
        suppressReady: true,
        cwd: this.gatewayProjectDir,
        venvDir: this.gatewayVenvDir,
      },
    );
  }

  private copyGatewayProjectFiles(): void {
    mkdirSync(this.gatewayProjectDir, { recursive: true });
    const srcRoot = join(process.resourcesPath, 'aigateway');
    for (const file of ['pyproject.toml', 'uv.lock']) {
      const src = join(srcRoot, file);
      const dst = join(this.gatewayProjectDir, file);
      if (existsSync(src)) copyFileSync(src, dst);
    }
    const src = join(srcRoot, 'src');
    const dst = join(this.gatewayProjectDir, 'src');
    if (existsSync(src)) cpSync(src, dst, { recursive: true, force: true });
  }

  private extractCacheIfNeeded(cacheDir: string): Promise<void> {
    const completeSentinel = join(cacheDir, '.cache-complete');
    if (existsSync(completeSentinel)) return Promise.resolve();
    const tarball = join(process.resourcesPath, 'server', 'cache.tar.gz');
    if (!existsSync(tarball)) return Promise.resolve();
    if (existsSync(cacheDir)) rmSync(cacheDir, { recursive: true, force: true });

    return new Promise((resolve, reject) => {
      mkdirSync(cacheDir, { recursive: true });
      this.emit('progress', 'Extracting package cache...\n');
      const child = spawn('tar', ['xzf', tarball, '-C', cacheDir]);
      child.on('close', (code) => {
        if (code === 0) {
          writeFileSync(completeSentinel, 'ok\n', 'utf-8');
          resolve();
        } else {
          reject(new Error(`tar exited ${code}`));
        }
      });
      child.on('error', reject);
    });
  }

  private get versionStampPath(): string {
    return join(app.getPath('userData'), '.sf-version');
  }

  private writeVersionStamp(): void {
    try {
      writeFileSync(this.versionStampPath, app.getVersion(), 'utf-8');
    } catch {
      // ignore write errors
    }
  }

  private needsResync(): boolean {
    if (is.dev) return false;
    try {
      const stamp = readFileSync(this.versionStampPath, 'utf-8').trim();
      return stamp !== app.getVersion();
    } catch {
      return true; // no stamp file = needs sync
    }
  }
}

export const venvManager = new VenvManager();
