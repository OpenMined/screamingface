import { useState, useEffect, useCallback, useRef } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useServerStatus } from '../hooks/use-server-status';
import { useToast } from '../hooks/use-toast';
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
  url4config: string | null;
}

interface ServerPluginInfo {
  version: string;
  description: string;
  has_settings: boolean;
}

interface SchemaProperty {
  type: string;
  default?: unknown;
  items?: { type: string };
  title?: string;
  description?: string;
}

interface PluginSchema {
  properties: Record<string, SchemaProperty>;
  required?: string[];
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
  url4config: null,
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

  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} title={title} />;
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
  const [pluginSchemas, setPluginSchemas] = useState<Record<string, PluginSchema>>({});
  const [pluginLiveSettings, setPluginLiveSettings] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [schemaLoading, setSchemaLoading] = useState<Record<string, boolean>>({});
  const [schemaErrors, setSchemaErrors] = useState<Record<string, boolean>>({});

  const { status: serverStatus, info: serverInfo } = useServerStatus();
  const { toast } = useToast();

  // Auto-save: debounce writes to disk
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const configRef = useRef(config);
  configRef.current = config;
  const initialLoadRef = useRef(true);

  const scheduleAutoSave = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      try {
        await window.electronAPI.config.write(
          configRef.current as unknown as Record<string, unknown>,
        );
        toast('Settings saved', 'success', 2000);
      } catch {
        toast('Failed to save settings', 'error');
      }
    }, AUTO_SAVE_DELAY);
  }, [toast]);

  // Server URL: prefer live info from process, fall back to config-derived URL
  const serverUrl = serverInfo
    ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}`
    : buildServerUrl(config);

  // Discover available plugins via CLI (works without server)
  useEffect(() => {
    window.electronAPI.plugins.discover().then((result) => {
      if (Object.keys(result).length > 0) {
        setDiscoveredPlugins(result);
      }
    });
  }, []);

  // Fetch via main process to bypass self-signed cert issues
  const serverFetch = useCallback(async (url: string) => {
    const res = await window.electronAPI.server.fetch(url);
    return { ok: res.ok, json: () => JSON.parse(res.body) };
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
          setPluginSchemas((prev) => ({ ...prev, [name]: schema }));
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

  const updatePlugins = (plugins: string[]) => {
    setConfig((prev) => ({ ...prev, plugins }));
    markDirty();
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
        .map(([name, info]) => ({ name, ...info }))
    : [];

  const getPluginMeta = (name: string) => {
    if (serverPlugins?.[name]) {
      return { version: serverPlugins[name].version, description: serverPlugins[name].description };
    }
    if (discoveredPlugins?.[name]) {
      return {
        version: discoveredPlugins[name].version,
        description: discoveredPlugins[name].description,
      };
    }
    return null;
  };

  const updatePluginConfig = (pluginName: string, field: string, value: unknown) => {
    setConfig((prev) => ({
      ...prev,
      plugin_config: {
        ...prev.plugin_config,
        [pluginName]: {
          ...prev.plugin_config[pluginName],
          [field]: value,
        },
      },
    }));
    markDirty();
  };

  const getFieldValue = (
    pluginName: string,
    field: string,
    schemaProp: SchemaProperty,
  ): unknown => {
    const localVal = config.plugin_config[pluginName]?.[field];
    if (localVal !== undefined) return localVal;
    const liveVal = pluginLiveSettings[pluginName]?.[field];
    if (liveVal !== undefined) return liveVal;
    return schemaProp.default;
  };

  const fieldLabel = (_name: string, prop: SchemaProperty): string => {
    if (prop.title) return prop.title;
    return _name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
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

      {/* url4 context template */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium text-foreground">Context URL Template</h2>
        <p className="mt-1 text-[10px] text-muted-foreground">
          A url4 template with {"{prompt}"} placeholders, resolved and injected into every Claude API request.
        </p>
        <div className="mt-3">
          <input
            type="text"
            value={config.url4config ?? ''}
            onChange={(e) => {
              const val = e.target.value.trim() || null;
              setConfig((prev) => ({ ...prev, url4config: val }));
              markDirty();
            }}
            placeholder="(http://example.com/docs, {prompt}) — leave empty to disable"
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
          />
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
        <div className="mt-3 space-y-2">
          {config.plugins.length === 0 ? (
            <p className="text-xs italic text-muted-foreground">No plugins enabled</p>
          ) : (
            config.plugins.map((name, i) => {
              const pluginStatus = getPluginStatus(name);
              const meta = getPluginMeta(name);
              const hasSettings = serverPlugins?.[name]?.has_settings === true;
              const isExpanded = hasSettings && expandedPlugin === name;
              const schema = pluginSchemas[name];
              return (
                <div key={name} className="rounded-md bg-secondary">
                  <div
                    className={`flex items-center justify-between px-3 py-2 select-none ${hasSettings ? 'cursor-pointer' : ''}`}
                    onClick={
                      hasSettings ? () => setExpandedPlugin(isExpanded ? null : name) : undefined
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
                      </div>
                    </div>
                    <div className="flex items-center gap-1 ml-2 shrink-0">
                      {hasSettings && (
                        <span className="p-1 text-muted-foreground">
                          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </span>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
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
                      {schemaLoading[name] && (
                        <p className="text-xs text-muted-foreground">Loading settings...</p>
                      )}
                      {schemaErrors[name] && !schemaLoading[name] && (
                        <p className="text-xs text-muted-foreground/60 italic">
                          No configurable settings or server not reachable
                        </p>
                      )}
                      {schema && !schemaLoading[name] && (
                        <div className="space-y-4">
                          {Object.entries(schema.properties).map(([field, prop]) => {
                            const value = getFieldValue(name, field, prop);
                            const label = fieldLabel(field, prop);

                            if (prop.type === 'boolean') {
                              return (
                                <div key={field}>
                                  <label className="flex items-center gap-2.5 text-xs text-foreground">
                                    <input
                                      type="checkbox"
                                      checked={Boolean(value)}
                                      onChange={(e) =>
                                        updatePluginConfig(name, field, e.target.checked)
                                      }
                                      className="h-3.5 w-3.5 rounded border-input"
                                    />
                                    {label}
                                  </label>
                                  {prop.description && (
                                    <p className="mt-1 pl-6 text-[10px] text-muted-foreground/60">
                                      {prop.description}
                                    </p>
                                  )}
                                </div>
                              );
                            }

                            if (prop.type === 'integer' || prop.type === 'number') {
                              return (
                                <div key={field} className="space-y-1.5">
                                  <div>
                                    <span className="text-xs text-muted-foreground">{label}</span>
                                    {prop.description && (
                                      <p className="mt-0.5 text-[10px] text-muted-foreground/60">
                                        {prop.description}
                                      </p>
                                    )}
                                  </div>
                                  <input
                                    type="number"
                                    value={value != null ? String(value) : ''}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      updatePluginConfig(
                                        name,
                                        field,
                                        v === ''
                                          ? null
                                          : prop.type === 'integer'
                                            ? parseInt(v)
                                            : parseFloat(v),
                                      );
                                    }}
                                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                                  />
                                </div>
                              );
                            }

                            if (prop.type === 'array' && prop.items?.type === 'string') {
                              const arrValue = Array.isArray(value)
                                ? (value as string[]).join(', ')
                                : '';
                              return (
                                <div key={field} className="space-y-1.5">
                                  <div>
                                    <span className="text-xs text-muted-foreground">{label}</span>
                                    {prop.description && (
                                      <p className="mt-0.5 text-[10px] text-muted-foreground/60">
                                        {prop.description}
                                      </p>
                                    )}
                                  </div>
                                  <input
                                    type="text"
                                    value={arrValue}
                                    onChange={(e) => {
                                      const parts = e.target.value
                                        .split(',')
                                        .map((s) => s.trim())
                                        .filter(Boolean);
                                      updatePluginConfig(name, field, parts);
                                    }}
                                    placeholder="Comma-separated values"
                                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
                                  />
                                </div>
                              );
                            }

                            // Default: string or unknown type
                            return (
                              <div key={field} className="space-y-1.5">
                                <div>
                                  <span className="text-xs text-muted-foreground">{label}</span>
                                  {prop.description && (
                                    <p className="mt-0.5 text-[10px] text-muted-foreground/60">
                                      {prop.description}
                                    </p>
                                  )}
                                </div>
                                <input
                                  type="text"
                                  value={value != null ? String(value) : ''}
                                  onChange={(e) => updatePluginConfig(name, field, e.target.value)}
                                  className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                                />
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
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
              className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="" disabled>
                Add a plugin...
              </option>
              {availableToAdd.map(({ name, description }) => (
                <option key={name} value={name}>
                  {name}
                  {description ? ` — ${description}` : ''}
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
