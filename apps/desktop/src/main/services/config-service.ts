import { readFileSync, writeFileSync, watchFile, unwatchFile } from 'fs';
import { join, resolve } from 'path';
import { EventEmitter } from 'events';
import { app } from 'electron';

function resolveServerDir(): string {
  // In dev, app.getAppPath() points to apps/desktop/
  // In production, it points to the asar archive
  const appPath = app.getAppPath();
  return resolve(appPath, '..', 'server');
}

let SERVER_DIR: string;
let CONFIG_PATH: string;

class ConfigService extends EventEmitter {
  private configPath: string;

  constructor() {
    super();
    // Defer resolution until app is ready
    SERVER_DIR = resolveServerDir();
    CONFIG_PATH = join(SERVER_DIR, 'sf.json');
    this.configPath = CONFIG_PATH;
  }

  get serverDir(): string {
    return SERVER_DIR;
  }

  setConfigPath(path: string): void {
    unwatchFile(this.configPath);
    this.configPath = path;
    this.watch();
  }

  read(): Record<string, unknown> {
    try {
      const raw = readFileSync(this.configPath, 'utf-8');
      return JSON.parse(raw);
    } catch {
      return {
        version: '0.1.0',
        server: { host: '0.0.0.0', port: 8000, reload: false, ssl: true },
        plugins: [],
        plugin_config: {},
      };
    }
  }

  write(config: Record<string, unknown>): void {
    writeFileSync(this.configPath, JSON.stringify(config, null, 2) + '\n', 'utf-8');
    this.emit('changed', config);
  }

  watch(): void {
    watchFile(this.configPath, { interval: 1000 }, () => {
      const config = this.read();
      this.emit('changed', config);
    });
  }

  getConfigPath(): string {
    return this.configPath;
  }
}

export const configService = new ConfigService();
