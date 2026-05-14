import {
  readFileSync,
  writeFileSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  watchFile,
  unwatchFile,
} from 'fs';
import { join, resolve } from 'path';
import { EventEmitter } from 'events';
import { app } from 'electron';
import { is } from '@electron-toolkit/utils';
import { getUserDataPath } from '../user-data-path';

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
    const userDataDir = getUserDataPath();
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

class ConfigService extends EventEmitter {
  private configPath: string;

  constructor() {
    super();
    // Defer resolution until app is ready
    SERVER_DIR = resolveServerDir();
    CONFIG_PATH = resolveConfigPath(SERVER_DIR);
    this.configPath = CONFIG_PATH;
    if (!is.dev) {
      this.migrateDesktopGatewayCodexConfig();
    }
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

  private migrateDesktopGatewayCodexConfig(): void {
    const config = this.read();
    const plugins = Array.isArray(config.plugins) ? [...config.plugins] : [];
    const nextPlugins = plugins
      .filter((plugin): plugin is string => typeof plugin === 'string')
      .filter((plugin) => plugin !== 'codex-backend-api');

    for (const required of ['aigw-runner', 'aigw-base', 'aigw-codex-backend']) {
      if (!nextPlugins.includes(required)) nextPlugins.push(required);
    }

    const pluginConfig =
      config.plugin_config && typeof config.plugin_config === 'object'
        ? { ...(config.plugin_config as Record<string, Record<string, unknown>>) }
        : {};
    const gatewayDir = join(getUserDataPath(), 'aigateway');
    const runnerConfig = pluginConfig['aigw-runner'] ?? {};
    const startupTimeout = runnerConfig.startup_timeout_seconds;
    pluginConfig['aigw-runner'] = {
      ...runnerConfig,
      aigateway_dir: gatewayDir,
      database_path: join(gatewayDir, 'aigateway.db'),
      auth_enabled: false,
      startup_timeout_seconds:
        typeof startupTimeout === 'number' && startupTimeout >= 60 ? startupTimeout : 60,
    };

    const migrated = {
      ...config,
      plugins: nextPlugins,
      plugin_config: pluginConfig,
    };

    if (JSON.stringify(migrated) !== JSON.stringify(config)) {
      this.write(migrated);
    }
  }
}

export const configService = new ConfigService();
