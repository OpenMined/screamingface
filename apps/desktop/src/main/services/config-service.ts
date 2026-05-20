import {
  closeSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  renameSync,
  rmSync,
  watchFile,
  unwatchFile,
} from 'fs';
import { basename, dirname, join, resolve } from 'path';
import { EventEmitter } from 'events';
import { app, dialog } from 'electron';
import { is } from '@electron-toolkit/utils';

import { GatewayUrlConflictError, migrateDesktopRuntimeConfig } from './runtime-config-migration';

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
    const userDataDir = app.getPath('userData');
    mkdirSync(userDataDir, { recursive: true });
    const userDataConfig = join(userDataDir, 'sf.json');
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

export class ConfigService extends EventEmitter {
  private configPath?: string;
  private initialized = false;

  constructor() {
    super();
  }

  private ensureInitialized(): void {
    if (this.initialized) {
      return;
    }
    SERVER_DIR = resolveServerDir();
    if (!this.configPath) {
      CONFIG_PATH = resolveConfigPath(SERVER_DIR);
      this.configPath = CONFIG_PATH;
    }
    this.initialized = true;
    if (!is.dev) {
      this.migrateDesktopRuntimeConfig();
    }
  }

  get serverDir(): string {
    this.ensureInitialized();
    return SERVER_DIR;
  }

  setConfigPath(path: string): void {
    if (this.configPath) {
      unwatchFile(this.configPath);
    }
    this.configPath = path;
    this.watch();
  }

  read(): Record<string, unknown> {
    const configPath = this.getConfigPath();
    try {
      const raw = readFileSync(configPath, 'utf-8');
      return JSON.parse(raw);
    } catch {
      return {
        version: '0.1.0',
        server: { host: '127.0.0.1', port: 8000, reload: false, ssl: true },
        plugins: [],
        plugin_config: {},
      };
    }
  }

  write(config: Record<string, unknown>): void {
    const configPath = this.getConfigPath();
    writeJsonAtomically(configPath, JSON.stringify(config, null, 2) + '\n');
    this.emit('changed', config);
  }

  watch(): void {
    const configPath = this.getConfigPath();
    watchFile(configPath, { interval: 1000, persistent: false }, () => {
      const config = this.read();
      this.emit('changed', config);
    });
  }

  getConfigPath(): string {
    this.ensureInitialized();
    if (!this.configPath) {
      throw new Error('Config path is not initialized');
    }
    return this.configPath;
  }

  private migrateDesktopRuntimeConfig(): void {
    const config = this.read();
    let migrated: Record<string, unknown>;
    try {
      migrated = migrateDesktopRuntimeConfig(config, app.getPath('userData'));
    } catch (error) {
      if (error instanceof GatewayUrlConflictError) {
        dialog.showErrorBox(
          'Choose AIGateway URL',
          `${error.message}\n\nConfig: ${this.getConfigPath()}`,
        );
      }
      throw error;
    }

    if (JSON.stringify(migrated) !== JSON.stringify(config)) {
      this.write(migrated);
    }
  }
}

function writeJsonAtomically(configPath: string, contents: string): void {
  mkdirSync(dirname(configPath), { recursive: true });
  const tempPath = join(
    dirname(configPath),
    `.${basename(configPath)}.${process.pid}.${Date.now()}.tmp`,
  );
  let fd: number | undefined;
  try {
    fd = openSync(tempPath, 'w', 0o600);
    writeFileSync(fd, contents, 'utf-8');
    fsyncSync(fd);
    closeSync(fd);
    fd = undefined;
    renameSync(tempPath, configPath);
  } catch (error) {
    if (fd !== undefined) {
      closeSync(fd);
    }
    rmSync(tempPath, { force: true });
    throw error;
  }
}

export const configService = new ConfigService();
