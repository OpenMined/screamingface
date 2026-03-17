import { readFileSync, writeFileSync, copyFileSync, existsSync, watchFile, unwatchFile } from 'fs';
import { join, resolve } from 'path';
import { EventEmitter } from 'events';
import { app } from 'electron';
import { is } from '@electron-toolkit/utils';

function resolveServerDir(): string {
  if (!is.dev) {
    // Production: server source is bundled as an extraResource
    return join(process.resourcesPath, 'server');
  }
  // Dev: sibling directory in the monorepo
  const appPath = app.getAppPath();
  return resolve(appPath, '..', 'server');
}

function resolveConfigPath(serverDir: string): string {
  if (!is.dev) {
    // Production: config lives in writable user data directory
    const userDataConfig = join(app.getPath('userData'), 'sf.json');
    if (!existsSync(userDataConfig)) {
      const templatePath = join(serverDir, 'sf.json');
      if (existsSync(templatePath)) {
        copyFileSync(templatePath, userDataConfig);
      }
    }
    return userDataConfig;
  }
  // Dev: config lives alongside server source
  return join(serverDir, 'sf.json');
}

let SERVER_DIR: string;
let CONFIG_PATH: string;

class ConfigService extends EventEmitter {
  private configPath: string;

  constructor() {
    super();
    // Defer resolution until app is ready
    SERVER_DIR = resolveServerDir();
    CONFIG_PATH = resolveConfigPath(SERVER_DIR);
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
