import { join } from 'path';

const DIRECT_CODEX_BACKEND = 'codex-backend-api';
const GATEWAY_CODEX_BACKEND = 'aigw-codex-backend';
const DEFAULT_CODEX_MODEL = 'codex/gpt-5.4-mini';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function migratePluginList(plugins: string[]): string[] {
  const nextPlugins: string[] = [];

  for (const plugin of plugins) {
    if (plugin === DIRECT_CODEX_BACKEND) {
      if (!nextPlugins.includes(GATEWAY_CODEX_BACKEND)) {
        nextPlugins.push(GATEWAY_CODEX_BACKEND);
      }
      continue;
    }
    if (plugin === GATEWAY_CODEX_BACKEND && nextPlugins.includes(GATEWAY_CODEX_BACKEND)) {
      continue;
    }
    nextPlugins.push(plugin);
  }

  for (const required of ['aigw-runner', 'aigw-base']) {
    if (!nextPlugins.includes(required)) nextPlugins.push(required);
  }

  return nextPlugins;
}

function migrateCodexBackendConfig(value: unknown): Record<string, unknown> {
  const migrated = isRecord(value) ? { ...value } : {};
  const model = migrated.default_model;
  if (typeof model !== 'string' || !model.startsWith('codex/')) {
    migrated.default_model = DEFAULT_CODEX_MODEL;
  }
  if (typeof migrated.gateway_url !== 'string') {
    migrated.gateway_url = 'http://127.0.0.1:9105';
  }
  if (typeof migrated.auth_profile !== 'string') {
    migrated.auth_profile = 'default';
  }
  return migrated;
}

export function migrateDesktopRuntimeConfig(
  config: Record<string, unknown>,
  userDataDir: string,
): Record<string, unknown> {
  const plugins = Array.isArray(config.plugins)
    ? config.plugins.filter((plugin): plugin is string => typeof plugin === 'string')
    : [];
  const hadDirectCodexBackend = plugins.includes(DIRECT_CODEX_BACKEND);
  const nextPlugins = migratePluginList(plugins);

  const serverConfig = isRecord(config.server) ? { ...config.server } : {};
  serverConfig.host = '127.0.0.1';

  const pluginConfig = isRecord(config.plugin_config) ? { ...config.plugin_config } : {};
  const gatewayDir = join(userDataDir, 'aigateway');
  const runnerConfig = isRecord(pluginConfig['aigw-runner']) ? pluginConfig['aigw-runner'] : {};
  const startupTimeout = runnerConfig.startup_timeout_seconds;
  pluginConfig['aigw-runner'] = {
    ...runnerConfig,
    aigateway_dir: gatewayDir,
    database_path: join(gatewayDir, 'aigateway.db'),
    auth_enabled: false,
    startup_timeout_seconds:
      typeof startupTimeout === 'number' && startupTimeout >= 60 ? startupTimeout : 60,
  };

  if (
    hadDirectCodexBackend &&
    Object.prototype.hasOwnProperty.call(pluginConfig, DIRECT_CODEX_BACKEND)
  ) {
    if (!isRecord(pluginConfig[GATEWAY_CODEX_BACKEND])) {
      pluginConfig[GATEWAY_CODEX_BACKEND] = migrateCodexBackendConfig(
        pluginConfig[DIRECT_CODEX_BACKEND],
      );
    }
    delete pluginConfig[DIRECT_CODEX_BACKEND];
  }

  return {
    ...config,
    server: serverConfig,
    plugins: nextPlugins,
    plugin_config: pluginConfig,
  };
}
