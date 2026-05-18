import { join } from 'path';

const LEGACY_DIRECT_CODEX_BACKEND = 'codex-backend-api';
const GATEWAY_CODEX_BACKEND = 'aigw-codex-backend';
const DEFAULT_CODEX_MODEL = 'codex/gpt-5.4-mini';
const DEFAULT_GATEWAY_URL = 'http://127.0.0.1:9105';

export class GatewayUrlConflictError extends Error {
  constructor(readonly urls: string[]) {
    super(
      `Multiple AIGateway backend gateway_url values found: ${urls.join(', ')}. ` +
        'Set plugin_config["aigw-base"].gateway_url to the intended URL before starting ScreamingFace.',
    );
    this.name = 'GatewayUrlConflictError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function migratePluginList(plugins: string[]): string[] {
  const nextPlugins: string[] = [];

  for (const plugin of plugins) {
    if (plugin === LEGACY_DIRECT_CODEX_BACKEND) {
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
  if (typeof migrated.auth_profile !== 'string') {
    migrated.auth_profile = 'default';
  }
  return migrated;
}

function isGatewayBackendName(name: string): boolean {
  return name.startsWith('aigw-') && name.endsWith('-backend');
}

function gatewayUrls(pluginConfig: Record<string, unknown>): string[] {
  const urls: string[] = [];
  for (const [name, value] of Object.entries(pluginConfig)) {
    if (!isGatewayBackendName(name) || !isRecord(value)) continue;
    const raw = value.gateway_url;
    if (typeof raw !== 'string' || !raw.trim()) continue;
    const normalized = raw.trim().replace(/\/+$/, '');
    if (!urls.includes(normalized)) urls.push(normalized);
  }
  return urls;
}

export function migrateDesktopRuntimeConfig(
  config: Record<string, unknown>,
  userDataDir: string,
): Record<string, unknown> {
  const plugins = Array.isArray(config.plugins)
    ? config.plugins.filter((plugin): plugin is string => typeof plugin === 'string')
    : [];
  const hadDirectCodexBackend = plugins.includes(LEGACY_DIRECT_CODEX_BACKEND);
  const nextPlugins = migratePluginList(plugins);

  const serverConfig = isRecord(config.server) ? { ...config.server } : {};
  serverConfig.host = '127.0.0.1';

  const pluginConfig = isRecord(config.plugin_config) ? { ...config.plugin_config } : {};
  const gatewayDir = join(userDataDir, 'aigateway');
  const runnerConfig = isRecord(pluginConfig['aigw-runner'])
    ? { ...pluginConfig['aigw-runner'] }
    : {};
  const startupTimeout = runnerConfig.startup_timeout_seconds;
  const legacyRunnerRequestedAuth = runnerConfig.auth_enabled === true;
  const legacyRunnerDisabled = runnerConfig.enabled === false;
  delete runnerConfig.auth_enabled;
  delete runnerConfig.enabled;
  pluginConfig['aigw-runner'] = {
    ...runnerConfig,
    aigateway_dir: gatewayDir,
    database_path: join(gatewayDir, 'aigateway.db'),
    startup_timeout_seconds:
      typeof startupTimeout === 'number' && startupTimeout >= 60 ? startupTimeout : 60,
  };

  if (
    hadDirectCodexBackend &&
    Object.prototype.hasOwnProperty.call(pluginConfig, LEGACY_DIRECT_CODEX_BACKEND)
  ) {
    if (!isRecord(pluginConfig[GATEWAY_CODEX_BACKEND])) {
      pluginConfig[GATEWAY_CODEX_BACKEND] = migrateCodexBackendConfig(
        pluginConfig[LEGACY_DIRECT_CODEX_BACKEND],
      );
    }
    delete pluginConfig[LEGACY_DIRECT_CODEX_BACKEND];
  }

  const baseConfig = isRecord(pluginConfig['aigw-base']) ? { ...pluginConfig['aigw-base'] } : {};
  const urls = gatewayUrls(pluginConfig);
  if (typeof baseConfig.gateway_url !== 'string') {
    if (urls.length > 1) throw new GatewayUrlConflictError(urls);
    const runnerPort = runnerConfig.port;
    baseConfig.gateway_url =
      urls.length === 1
        ? urls[0]
        : typeof runnerPort === 'number' && runnerPort > 0 && runnerPort !== 9105
          ? `http://127.0.0.1:${runnerPort}`
          : DEFAULT_GATEWAY_URL;
  }
  if (baseConfig.mode !== 'local_managed' && baseConfig.mode !== 'external') {
    baseConfig.mode =
      legacyRunnerRequestedAuth || legacyRunnerDisabled ? 'external' : 'local_managed';
  }
  pluginConfig['aigw-base'] = baseConfig;

  for (const [name, value] of Object.entries(pluginConfig)) {
    if (!isGatewayBackendName(name) || !isRecord(value)) continue;
    delete value.gateway_url;
  }

  return {
    ...config,
    server: serverConfig,
    plugins: nextPlugins,
    plugin_config: pluginConfig,
  };
}
