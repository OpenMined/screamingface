import { useState, useEffect, useCallback, useRef } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import validator from '@rjsf/validator-ajv8';
import type { RJSFSchema } from '@rjsf/utils';
import { useServerStatus } from '../hooks/use-server-status';
import { useToast } from '../hooks/use-toast';
import { ThemedForm } from '../components/rjsf-theme';
import { inlineRefs } from '../components/rjsf-utils';
import type { DiscoveredPlugin } from '../../../preload/types';

interface ServerConfig {
  host: string;
  port: number;
  reload: boolean;
  ssl: boolean;
  ssl_certfile: string | null;
  ssl_keyfile: string | null;
}

interface AppConfig {
  version: string;
  server: ServerConfig;
  plugins: string[];
  plugin_config: Record<string, Record<string, unknown>>;
}

interface ServerPluginInfo {
  version: string;
  description: string;
  has_settings: boolean;
  requires_root?: boolean;
  depends?: string[];
  conflicts?: string[];
}

const defaultConfig: AppConfig = {
  version: '0.1.0',
  server: {
    host: '0.0.0.0',
    port: 8000,
    reload: false,
    ssl: true,
    ssl_certfile: null,
    ssl_keyfile: null,
  },
  plugins: [],
  plugin_config: {},
};

type PluginStatus = 'active' | 'configured' | 'missing';

function StatusDot({ status }: { status: PluginStatus }) {
  const color = {
    active: 'bg-green-500',
    configured: 'bg-muted-foreground/40',
    missing: 'bg-red-500',
  }[status];

  const title = {
    active: 'Active on server',
    configured: 'Server not running',
    missing: 'Not found on server',
  }[status];

  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${color}`} title={title} />;
}

function buildServerUrl(config: AppConfig): string {
  const scheme = config.server.ssl ? 'https' : 'http';
  const host = config.server.host === '0.0.0.0' ? 'localhost' : config.server.host;
  return `${scheme}://${host}:${config.server.port}`;
}

const AUTO_SAVE_DELAY = 800;

export function SettingsView() {
  const [config, setConfig] = useState<AppConfig>(defaultConfig);
  const [serverPlugins, setServerPlugins] = useState<Record<string, ServerPluginInfo> | null>(null);
  const [discoveredPlugins, setDiscoveredPlugins] = useState<Record<
    string,
    DiscoveredPlugin
  > | null>(null);
  const [newPluginName, setNewPluginName] = useState('');
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null);
  const [pluginSchemas, setPluginSchemas] = useState<Record<string, RJSFSchema>>({});
  const [pluginLiveSettings, setPluginLiveSettings] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [schemaLoading, setSchemaLoading] = useState<Record<string, boolean>>({});
  const [schemaErrors, setSchemaErrors] = useState<Record<string, boolean>>({});

  const { status: serverStatus, info: serverInfo } = useServerStatus();
  const { toast } = useToast();

  // Server URL: prefer live info from process, fall back to config-derived URL
  const serverUrl = serverInfo
    ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}`
    : buildServerUrl(config);

  // Fetch via main process to bypass self-signed cert issues
  const serverFetch = useCallback(
    async (url: string, init?: { method?: string; body?: string }) => {
      const res = await window.electronAPI.server.fetch(url, init);
      return { ok: res.ok, status: res.status, json: () => JSON.parse(res.body) };
    },
    [],
  );

  // Auto-save: debounce writes to disk
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const configRef = useRef(config);
  configRef.current = config;
  const initialLoadRef = useRef(true);
  const serverUrlRef = useRef(serverUrl);
  serverUrlRef.current = serverUrl;

  const scheduleAutoSave = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      try {
        // Validate plugin settings with the server before saving
        const cfg = configRef.current;
        for (const [pluginName, settings] of Object.entries(cfg.plugin_config)) {
          if (!cfg.plugins.includes(pluginName)) continue;
          if (!settings || Object.keys(settings).length === 0) continue;
          try {
            const res = await serverFetch(
              `${serverUrlRef.current}/plugins/${pluginName}/settings/validate`,
              { method: 'POST', body: JSON.stringify(settings) },
            );
            if (!res.ok) {
              const err = res.json();
              toast(`${pluginName}: ${err.detail ?? 'Validation failed'}`, 'error');
              return; // abort save
            }
          } catch {
            // Server not reachable — skip server validation, save anyway
          }
        }
        await window.electronAPI.config.write(cfg as unknown as Record<string, unknown>);
        toast('Settings saved', 'success', 2000);
      } catch {
        toast('Failed to save settings', 'error');
      }
    }, AUTO_SAVE_DELAY);
  }, [toast, serverFetch]);

  // Discover available plugins via CLI (works without server)
  useEffect(() => {
    window.electronAPI.plugins.discover().then((result) => {
      if (Object.keys(result).length > 0) {
        setDiscoveredPlugins(result);
      }
    });
  }, []);

  // Fetch active plugin metadata from server
  const fetchServerPlugins = useCallback(async () => {
    try {
      const res = await serverFetch(`${serverUrl}/plugins`);
      if (res.ok) {
        setServerPlugins(res.json());
      }
    } catch {
      setServerPlugins(null);
    }
  }, [serverUrl, serverFetch]);

  useEffect(() => {
    fetchServerPlugins();
  }, [fetchServerPlugins, serverStatus]);

  // Fetch schema + live settings when a plugin is expanded
  useEffect(() => {
    if (!expandedPlugin || pluginSchemas[expandedPlugin]) return;
    setSchemaLoading((prev) => ({ ...prev, [expandedPlugin]: true }));
    setSchemaErrors((prev) => ({ ...prev, [expandedPlugin]: false }));
    const name = expandedPlugin;
    Promise.all([
      serverFetch(`${serverUrl}/plugins/${name}/schema`).then((r) => (r.ok ? r.json() : null)),
      serverFetch(`${serverUrl}/plugins/${name}/settings`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([schema, settings]) => {
        if (schema?.properties) {
          setPluginSchemas((prev) => ({ ...prev, [name]: inlineRefs(schema) }));
        } else {
          setSchemaErrors((prev) => ({ ...prev, [name]: true }));
        }
        if (settings) {
          setPluginLiveSettings((prev) => ({ ...prev, [name]: settings }));
        }
      })
      .catch(() => {
        setSchemaErrors((prev) => ({ ...prev, [name]: true }));
      })
      .finally(() => {
        setSchemaLoading((prev) => ({ ...prev, [name]: false }));
      });
  }, [expandedPlugin, serverUrl, pluginSchemas, serverFetch]);

  // Load config from disk and subscribe to external changes
  useEffect(() => {
    window.electronAPI.config.read().then((c) => {
      setConfig(c as AppConfig);
      // Mark initial load complete after state settles
      setTimeout(() => {
        initialLoadRef.current = false;
      }, 100);
    });
    const unsub = window.electronAPI.config.onChanged((c) => {
      setConfig(c as AppConfig);
    });
    return unsub;
  }, []);

  const markDirty = useCallback(() => {
    if (!initialLoadRef.current) {
      scheduleAutoSave();
    }
  }, [scheduleAutoSave]);

  const update = (patch: Partial<ServerConfig>) => {
    setConfig((prev) => ({ ...prev, server: { ...prev.server, ...patch } }));
    markDirty();
  };

  const updatePlugins = async (plugins: string[]) => {
    if (initialLoadRef.current) {
      setConfig((prev) => ({ ...prev, plugins }));
      return;
    }

    // Validate via server before saving (preflight checks, conflict detection)
    if (serverStatus === 'ready') {
      try {
        const res = await serverFetch(`${serverUrlRef.current}/config/validate`, {
          method: 'POST',
          body: JSON.stringify({ plugins, current_plugins: configRef.current.plugins }),
        });
        const data = res.json();
        if (!data.valid && data.errors?.length) {
          const msgs = data.errors.map(
            (e: { plugin: string; error: string }) => `${e.plugin}: ${e.error}`,
          );
          toast(msgs.join('\n'), 'error', 5000);
          return; // Don't save — validation failed
        }
      } catch {
        // Server unreachable — skip validation, allow save
      }
    }

    setConfig((prev) => ({ ...prev, plugins }));

    // Plugin changes require a server restart — save immediately (skip debounce)
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    const configToSave = { ...configRef.current, plugins };
    window.electronAPI.config
      .write(configToSave as unknown as Record<string, unknown>)
      .then(() => {
        if (serverStatus === 'ready') {
          toast('Restarting server with updated plugins...', 'success', 3000);
          return window.electronAPI.server.restart();
        }
        toast('Settings saved', 'success', 2000);
      })
      .catch(() => {
        toast('Failed to save settings', 'error');
      });
  };

  const addPlugin = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed || config.plugins.includes(trimmed)) return;
    updatePlugins([...config.plugins, trimmed]);
    setNewPluginName('');
  };

  const getPluginStatus = (name: string): PluginStatus => {
    if (serverStatus !== 'ready' || !serverPlugins) return 'configured';
    return serverPlugins[name] ? 'active' : 'missing';
  };

  const availableToAdd = discoveredPlugins
    ? Object.entries(discoveredPlugins)
        .filter(([name]) => !config.plugins.includes(name))
        .map(([name, info]) => {
          const conflicts = info.conflicts ?? [];
          const conflictsWith = conflicts.filter((c) => config.plugins.includes(c));
          return { name, ...info, conflictsWith };
        })
    : [];

  const getPluginMeta = (name: string) => {
    if (serverPlugins?.[name]) {
      return {
        version: serverPlugins[name].version,
        description: serverPlugins[name].description,
        requires_root: serverPlugins[name].requires_root,
        depends: serverPlugins[name].depends,
        conflicts: serverPlugins[name].conflicts,
        tags: serverPlugins[name].tags,
      };
    }
    if (discoveredPlugins?.[name]) {
      return {
        version: discoveredPlugins[name].version,
        description: discoveredPlugins[name].description,
        requires_root: discoveredPlugins[name].requires_root,
        depends: discoveredPlugins[name].depends,
        conflicts: discoveredPlugins[name].conflicts,
        tags: discoveredPlugins[name].tags,
      };
    }
    return null;
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="font-heading text-lg font-semibold text-foreground">Settings</h1>

      {/* Server settings */}
      <section className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-foreground">Server</h2>
          {serverStatus === 'ready' && <span className="text-[10px] text-chart-3">Running</span>}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <span className="text-xs text-muted-foreground">Host</span>
            <input
              type="text"
              value={serverInfo?.host ?? config.server.host}
              onChange={(e) => update({ host: e.target.value })}
              disabled={serverStatus === 'ready'}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-muted-foreground">Port</span>
            <input
              type="number"
              value={serverInfo?.port ?? config.server.port}
              onChange={(e) => update({ port: parseInt(e.target.value) || 8000 })}
              disabled={serverStatus === 'ready'}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </label>
        </div>
        <div className="mt-4 flex gap-6">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={serverInfo ? serverInfo.scheme === 'https' : config.server.ssl}
              onChange={(e) => update({ ssl: e.target.checked })}
              disabled={serverStatus === 'ready'}
              className="rounded border-input disabled:opacity-50 disabled:cursor-not-allowed"
            />
            SSL
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={config.server.reload}
              onChange={(e) => update({ reload: e.target.checked })}
              disabled={serverStatus === 'ready'}
              className="rounded border-input disabled:opacity-50 disabled:cursor-not-allowed"
            />
            Auto-reload
          </label>
        </div>
      </section>

      {/* Plugins list */}
      <section className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-foreground">Enabled Plugins</h2>
          {serverStatus !== 'ready' && config.plugins.length > 0 && (
            <span className="text-[10px] text-muted-foreground">Server not running</span>
          )}
        </div>
        <div className="mt-3 space-y-1">
          {config.plugins.length === 0 ? (
            <p className="text-xs italic text-muted-foreground">No plugins enabled</p>
          ) : (
            (() => {
              // Group plugins by product tag
              const getProductTag = (pluginName: string): string => {
                const meta = getPluginMeta(pluginName);
                const tags: string[] = (meta?.tags as string[]) || [];
                const productTag = tags.find((t: string) => t.startsWith('product:'));
                return productTag ? productTag.replace('product:', '') : 'etc';
              };

              const groups: Record<string, string[]> = {};
              for (const name of config.plugins) {
                const group = getProductTag(name);
                if (!groups[group]) groups[group] = [];
                groups[group].push(name);
              }

              // Sort plugins within each group
              for (const g of Object.keys(groups)) {
                groups[g].sort((a, b) => a.localeCompare(b));
              }

              // Sort groups: alphabetically, but 'system' and 'etc' go last
              const groupOrder = Object.keys(groups).sort((a, b) => {
                if (a === 'etc') return 1;
                if (b === 'etc') return -1;
                if (a === 'system') return 1;
                if (b === 'system') return -1;
                return a.localeCompare(b);
              });

              const GROUP_COLORS: Record<string, string> = {
                claude: 'from-orange-500/20 to-orange-500/5 text-orange-300',
                openai: 'from-green-500/20 to-green-500/5 text-green-300',
                gemini: 'from-blue-500/20 to-blue-500/5 text-blue-300',
                url4: 'from-purple-500/20 to-purple-500/5 text-purple-300',
                system: 'from-zinc-500/20 to-zinc-500/5 text-zinc-400',
                etc: 'from-zinc-500/20 to-zinc-500/5 text-zinc-400',
              };

              return groupOrder.map((group) => (
                <div key={group} className="mb-4">
                  <div className="flex items-center gap-2 mb-2 px-1">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-widest ${GROUP_COLORS[group]?.split(' ').pop() || 'text-muted-foreground/50'}`}
                    >
                      {group}
                    </span>
                    <span className="text-[9px] text-muted-foreground/30">
                      {groups[group].length}
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {groups[group].map((name) => {
                      const i = config.plugins.indexOf(name);
                      const pluginStatus = getPluginStatus(name);
                      const meta = getPluginMeta(name);
                      const hasSettings = serverPlugins?.[name]?.has_settings === true;
                      const isExpanded = hasSettings && expandedPlugin === name;
                      const schema = pluginSchemas[name];
                      return (
                        <div key={name}>
                          <div className="rounded-md bg-secondary">
                            <div
                              className={`flex items-center justify-between px-3 py-2 select-none ${hasSettings ? 'cursor-pointer' : ''}`}
                              onClick={
                                hasSettings
                                  ? () => setExpandedPlugin(isExpanded ? null : name)
                                  : undefined
                              }
                            >
                              <div className="flex items-center gap-2.5 min-w-0">
                                {hasSettings ? (
                                  <StatusDot status={pluginStatus} />
                                ) : (
                                  <span className="inline-block h-2 w-2" />
                                )}
                                <div className="min-w-0">
                                  <span className="font-mono text-xs text-foreground">{name}</span>
                                  {meta?.version && (
                                    <span className="ml-2 text-[10px] text-muted-foreground">
                                      v{meta.version}
                                    </span>
                                  )}
                                  {meta?.description && (
                                    <p className="text-[10px] leading-tight text-muted-foreground/70 truncate">
                                      {meta.description}
                                    </p>
                                  )}
                                  {name === 'claude-frontend' && (
                                    <p className="text-[10px] leading-tight text-chart-3/80">
                                      Settings here are defaults for new sessions — override per
                                      session in the Sessions tab
                                    </p>
                                  )}
                                  {meta?.requires_root && (
                                    <p className="text-[10px] leading-tight text-amber-500">
                                      Requires root privileges — the app will prompt for your
                                      password when starting the server
                                    </p>
                                  )}
                                  {meta?.depends &&
                                    meta.depends.length > 0 &&
                                    (() => {
                                      const unmet = meta.depends!.filter(
                                        (dep) =>
                                          !config.plugins.includes(dep) && !serverPlugins?.[dep],
                                      );
                                      return unmet.length > 0 ? (
                                        <p className="text-[10px] leading-tight text-amber-500">
                                          Depends on: {unmet.join(', ')} (will be auto-added at
                                          startup)
                                        </p>
                                      ) : null;
                                    })()}
                                </div>
                              </div>
                              <div className="flex items-center gap-1 ml-2 shrink-0">
                                {hasSettings && (
                                  <span className="p-1 text-muted-foreground">
                                    {isExpanded ? (
                                      <ChevronDown size={14} />
                                    ) : (
                                      <ChevronRight size={14} />
                                    )}
                                  </span>
                                )}
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    // Warn if other enabled plugins depend on this one
                                    const dependents = config.plugins.filter((p) => {
                                      const pMeta = getPluginMeta(p);
                                      return pMeta?.depends?.includes(name);
                                    });
                                    if (dependents.length > 0) {
                                      const ok = window.confirm(
                                        `${dependents.join(', ')} depend${dependents.length === 1 ? 's' : ''} on ${name}. Remove anyway?`,
                                      );
                                      if (!ok) return;
                                    }
                                    if (expandedPlugin === name) setExpandedPlugin(null);
                                    updatePlugins(config.plugins.filter((_, j) => j !== i));
                                  }}
                                  className="text-xs text-muted-foreground transition-colors hover:text-destructive"
                                >
                                  Remove
                                </button>
                              </div>
                            </div>
                            {isExpanded && (
                              <div className="border-t border-border/50 px-4 py-4">
                                {/* Dependency map */}
                                {(() => {
                                  const deps = meta?.depends || [];
                                  const conflicts = meta?.conflicts || [];
                                  const dependents = config.plugins.filter((p) => {
                                    const pMeta = getPluginMeta(p);
                                    return pMeta?.depends?.includes(name);
                                  });
                                  if (
                                    deps.length === 0 &&
                                    conflicts.length === 0 &&
                                    dependents.length === 0
                                  )
                                    return null;
                                  return (
                                    <div className="mb-4 rounded-lg bg-background/80 ring-1 ring-border/40 p-3">
                                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                                        Dependencies
                                      </p>
                                      <div className="flex items-center gap-3 flex-wrap">
                                        {deps.length > 0 && (
                                          <div className="flex items-center gap-1.5">
                                            <span className="text-[10px] text-muted-foreground/50">
                                              needs
                                            </span>
                                            {deps.map((d) => (
                                              <span
                                                key={d}
                                                className={`inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[10px] ${
                                                  config.plugins.includes(d)
                                                    ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20'
                                                    : 'bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20'
                                                }`}
                                              >
                                                <span
                                                  className={`mr-1 inline-block h-1.5 w-1.5 rounded-full ${
                                                    config.plugins.includes(d)
                                                      ? 'bg-emerald-400'
                                                      : 'bg-amber-400'
                                                  }`}
                                                />
                                                {d}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                        {dependents.length > 0 && (
                                          <div className="flex items-center gap-1.5">
                                            <span className="text-[10px] text-muted-foreground/50">
                                              used by
                                            </span>
                                            {dependents.map((d) => (
                                              <span
                                                key={d}
                                                className="inline-flex items-center rounded-full bg-blue-500/10 px-2 py-0.5 font-mono text-[10px] text-blue-400 ring-1 ring-blue-500/20"
                                              >
                                                <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-blue-400" />
                                                {d}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                        {conflicts.length > 0 && (
                                          <div className="flex items-center gap-1.5">
                                            <span className="text-[10px] text-muted-foreground/50">
                                              conflicts
                                            </span>
                                            {conflicts.map((c) => (
                                              <span
                                                key={c}
                                                className="inline-flex items-center rounded-full bg-red-500/10 px-2 py-0.5 font-mono text-[10px] text-red-400 ring-1 ring-red-500/20"
                                              >
                                                <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-red-400" />
                                                {c}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })()}
                                {schemaLoading[name] && (
                                  <p className="text-xs text-muted-foreground">
                                    Loading settings...
                                  </p>
                                )}
                                {schemaErrors[name] && !schemaLoading[name] && (
                                  <p className="text-xs text-muted-foreground/60 italic">
                                    No configurable settings or server not reachable
                                  </p>
                                )}
                                {schema && !schemaLoading[name] && (
                                  <ThemedForm
                                    schema={schema}
                                    formData={{
                                      ...pluginLiveSettings[name],
                                      ...config.plugin_config[name],
                                    }}
                                    formContext={{
                                      serverUrl,
                                      serverFetch,
                                      addDictEntry: (path: string[], entryName: string) => {
                                        setConfig((prev) => {
                                          const base = {
                                            ...pluginLiveSettings[name],
                                            ...prev.plugin_config[name],
                                          };
                                          let target: Record<string, unknown> = base;
                                          for (const key of path) {
                                            target[key] = {
                                              ...(target[key] as Record<string, unknown>),
                                            };
                                            target = target[key] as Record<string, unknown>;
                                          }
                                          target[entryName] = {};
                                          return {
                                            ...prev,
                                            plugin_config: { ...prev.plugin_config, [name]: base },
                                          };
                                        });
                                        markDirty();
                                      },
                                    }}
                                    validator={validator}
                                    liveValidate
                                    onChange={({ formData, errors }) => {
                                      setConfig((prev) => ({
                                        ...prev,
                                        plugin_config: {
                                          ...prev.plugin_config,
                                          [name]: formData,
                                        },
                                      }));
                                      if (!errors || errors.length === 0) {
                                        markDirty();
                                      }
                                    }}
                                    omitExtraData
                                    uiSchema={{
                                      'ui:submitButtonOptions': { norender: true },
                                      ...([
                                        'claude-frontend',
                                        'codex-frontend',
                                        'gemini-frontend',
                                      ].includes(name)
                                        ? {
                                            active_spec: { 'ui:widget': 'SpecSelectorWidget' },
                                          }
                                        : {}),
                                    }}
                                  />
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ));
            })()
          )}
        </div>

        {/* Add plugin */}
        <div className="mt-3 flex gap-2">
          {availableToAdd.length > 0 ? (
            <select
              value=""
              onChange={(e) => {
                if (e.target.value) addPlugin(e.target.value);
              }}
              className="flex-1 min-w-0 appearance-none rounded-md border border-input bg-background bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23888%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px_16px] bg-[position:right_8px_center] bg-no-repeat pl-3 pr-8 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="" disabled>
                Add a plugin...
              </option>
              {availableToAdd.map(({ name, description, requires_root, conflictsWith }) => (
                <option key={name} value={name} disabled={conflictsWith.length > 0}>
                  {name}
                  {description ? ` — ${description}` : ''}
                  {requires_root ? ' (requires root)' : ''}
                  {conflictsWith.length > 0 ? ` [conflicts with ${conflictsWith.join(', ')}]` : ''}
                </option>
              ))}
            </select>
          ) : (
            <>
              <input
                type="text"
                value={newPluginName}
                onChange={(e) => setNewPluginName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addPlugin(newPluginName)}
                placeholder="Plugin name"
                className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <button
                onClick={() => addPlugin(newPluginName)}
                disabled={!newPluginName.trim() || config.plugins.includes(newPluginName.trim())}
                className="rounded-md border border-input px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-secondary disabled:opacity-40 disabled:pointer-events-none"
              >
                Add
              </button>
            </>
          )}
        </div>
      </section>

      {/* Raw JSON preview */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium text-muted-foreground">sf.json</h2>
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-background p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {JSON.stringify(config, null, 2)}
        </pre>
      </section>
    </div>
  );
}
