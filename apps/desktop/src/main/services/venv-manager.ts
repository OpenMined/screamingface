import { spawn, execFile, execFileSync } from 'child_process';
import { existsSync } from 'fs';
import { join } from 'path';
import { EventEmitter } from 'events';
import { resolveUv } from './uv-resolver';
import { configService } from './config-service';

export interface DiscoveredPlugin {
  state: 'enabled' | 'available';
  version: string | null;
  description: string | null;
}

export type VenvStatus = 'unknown' | 'checking' | 'missing' | 'creating' | 'ready' | 'error';

class VenvManager extends EventEmitter {
  private status: VenvStatus = 'unknown';
  private uvBin: string | null = null;

  private get serverDir(): string {
    return configService.serverDir;
  }

  private get venvDir(): string {
    return join(this.serverDir, '.venv');
  }

  private get pythonBin(): string {
    return join(this.venvDir, 'bin', 'python');
  }

  private setStatus(s: VenvStatus): void {
    this.status = s;
    this.emit('status', s);
  }

  getStatus(): VenvStatus {
    return this.status;
  }

  async detect(): Promise<{ status: VenvStatus; uvFound: boolean }> {
    this.setStatus('checking');
    this.uvBin = resolveUv();

    if (!this.uvBin) {
      this.setStatus('error');
      return { status: 'error', uvFound: false };
    }

    if (existsSync(this.pythonBin)) {
      try {
        execFileSync(this.pythonBin, ['--version'], { encoding: 'utf-8' });
        this.setStatus('ready');
        return { status: 'ready', uvFound: true };
      } catch {
        this.setStatus('error');
        return { status: 'error', uvFound: true };
      }
    }

    this.setStatus('missing');
    return { status: 'missing', uvFound: true };
  }

  async create(): Promise<boolean> {
    if (!this.uvBin) {
      this.setStatus('error');
      return false;
    }

    this.setStatus('creating');
    return this.runUvCommand([this.uvBin, 'venv', '.venv']);
  }

  async sync(extra?: string): Promise<boolean> {
    if (!this.uvBin) {
      this.setStatus('error');
      return false;
    }

    const args = [this.uvBin, 'sync'];
    if (extra) args.push('--extra', extra);

    return this.runUvCommand(args);
  }

  async listPackages(): Promise<Array<{ name: string; version: string }>> {
    if (!this.uvBin) return [];

    try {
      const output = execFileSync(this.uvBin, ['pip', 'list', '--format', 'json'], {
        cwd: this.serverDir,
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
          cwd: this.serverDir,
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

  private runUvCommand(args: string[]): Promise<boolean> {
    return new Promise((resolve) => {
      const [cmd, ...rest] = args;
      const child = spawn(cmd, rest, {
        cwd: this.serverDir,
        env: { ...process.env, VIRTUAL_ENV: this.venvDir },
      });

      child.stdout.on('data', (data: Buffer) => {
        this.emit('progress', data.toString());
      });

      child.stderr.on('data', (data: Buffer) => {
        this.emit('progress', data.toString());
      });

      child.on('close', (code) => {
        if (code === 0) {
          this.setStatus('ready');
          resolve(true);
        } else {
          this.setStatus('error');
          resolve(false);
        }
      });

      child.on('error', () => {
        this.setStatus('error');
        resolve(false);
      });
    });
  }
}

export const venvManager = new VenvManager();
