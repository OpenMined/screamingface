import { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useServerStatus } from '../hooks/use-server-status';
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
  server: { host: '0.0.0.0', port: 8000, reload: false, ssl: true, ssl_certfile: null, ssl_keyfile: null },
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

export function SettingsView() {
  const [config, setConfig] = useState<AppConfig>(defaultConfig);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [serverPlugins, setServerPlugins] = useState<Record<string, ServerPluginInfo> | null>(null);
  const [discoveredPlugins, setDiscoveredPlugins] = useState<Record<string, DiscoveredPlugin> | null>(null);
  const [newPluginName, setNewPluginName] = useState('');
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null);
  const [pluginSchemas, setPluginSchemas] = useState<Record<string, PluginSchema>>({});
  const [pluginLiveSettings, setPluginLiveSettings] = useState<Record<string, Record<string, unknown>>>({});
  const [schemaLoading, setSchemaLoading] = useState<Record<string, boolean>>({});
  const [schemaErrors, setSchemaErrors] = useState<Record<string, boolean>>({});

  const { status: serverStatus, info: serverInfo } = useServerStatus();

  const serverUrl = serverInfo ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}` : null;

  // Discover available plugins via CLI (works without server)
  useEffect(() => {
    window.electronAPI.plugins.discover().then((result) => {
      if (Object.keys(result).length > 0) {
        setDiscoveredPlugins(result);
      }
    });
  }, []);

  // Fetch active plugin metadata from server when running
  const fetchServerPlugins = useCallback(async () => {
    if (!serverUrl) return;
    try {
      const res = await fetch(`${serverUrl}/plugins`);
      if (res.ok) {
        setServerPlugins(await res.json());
      }
    } catch {
      setServerPlugins(null);
    }
  }, [serverUrl]);

  useEffect(() => {
    if (serverStatus === 'ready') {
      fetchServerPlugins();
    } else {
      setServerPlugins(null);
      setExpandedPlugin(null);
      setPluginSchemas({});
      setPluginLiveSettings({});
      setSchemaErrors({});
    }
  }, [serverStatus, fetchServerPlugins]);

  // Clear schema caches when server plugins re-fetch (stale guard)
  useEffect(() => {
    setPluginSchemas({});
    setPluginLiveSettings({});
    setSchemaErrors({});
  }, [serverPlugins]);

  // Fetch schema + live settings when a plugin is expanded
  useEffect(() => {
    if (!expandedPlugin || !serverUrl || pluginSchemas[expandedPlugin]) return;
    setSchemaLoading((prev) => ({ ...prev, [expandedPlugin]: true }));
    const name = expandedPlugin;
    Promise.all([
      fetch(`${serverUrl}/plugins/${name}/schema`).then((r) => r.ok ? r.json() : null),
      fetch(`${serverUrl}/plugins/${name}/settings`).then((r) => r.ok ? r.json() : null),
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
  }, [expandedPlugin, serverUrl, pluginSchemas]);

  useEffect(() => {
    window.electronAPI.config.read().then((c) => setConfig(c as AppConfig));
    const unsub = window.electronAPI.config.onChanged((c) => {
      setConfig(c as AppConfig);
      setDirty(false);
    });
    return unsub;
  }, []);

  const update = (patch: Partial<ServerConfig>) => {
    setConfig((prev) => ({ ...prev, server: { ...prev.server, ...patch } }));
    setDirty(true);
    setSaved(false);
  };

  const updatePlugins = (plugins: string[]) => {
    setConfig((prev) => ({ ...prev, plugins }));
    setDirty(true);
    setSaved(false);
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

  // Plugins that are discovered but not yet enabled
  const availableToAdd = discoveredPlugins
    ? Object.entries(discoveredPlugins)
        .filter(([name]) => !config.plugins.includes(name))
        .map(([name, info]) => ({ name, ...info }))
    : [];

  // Get metadata: prefer server data (live), fall back to discovered data (CLI)
  const getPluginMeta = (name: string) => {
    if (serverPlugins?.[name]) {
      return { version: serverPlugins[name].version, description: serverPlugins[name].description };
    }
    if (discoveredPlugins?.[name]) {
      return { version: discoveredPlugins[name].version, description: discoveredPlugins[name].description };
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
    setDirty(true);
    setSaved(false);
  };

  const getFieldValue = (pluginName: string, field: string, schemaProp: SchemaProperty): unknown => {
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

  const save = async () => {
    await window.electronAPI.config.write(config as unknown as Record<string, unknown>);
    setDirty(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-lg font-semibold text-foreground">Settings</h1>
        {dirty && (
          <button
            onClick={save}
            className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Save
          </button>
        )}
        {saved && <span className="text-xs text-chart-3">Saved</span>}
      </div>

      {/* Server settings */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium text-foreground">Server</h2>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <span className="text-xs text-muted-foreground">Host</span>
            <input
              type="text"
              value={config.server.host}
              onChange={(e) => update({ host: e.target.value })}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-muted-foreground">Port</span>
            <input
              type="number"
              value={config.server.port}
              onChange={(e) => update({ port: parseInt(e.target.value) || 8000 })}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </label>
        </div>
        <div className="mt-4 flex gap-6">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={config.server.ssl}
              onChange={(e) => update({ ssl: e.target.checked })}
              className="rounded border-input"
            />
            SSL
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={config.server.reload}
              onChange={(e) => update({ reload: e.target.checked })}
              className="rounded border-input"
            />
            Auto-reload
          </label>
        </div>
      </section>

      {/* url4 context enrichment */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium text-foreground">Context Enrichment</h2>
        <p className="mt-1 text-[10px] text-muted-foreground">
          A url4 URL that resolves to a prompt injected into every Claude API request.
        </p>
        <div className="mt-3">
          <input
            type="text"
            value={config.url4config ?? ''}
            onChange={(e) => {
              const val = e.target.value.trim() || null;
              setConfig((prev) => ({ ...prev, url4config: val }));
              setDirty(true);
              setSaved(false);
            }}
            placeholder="url4://project/context (leave empty to disable)"
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
              const isExpanded = expandedPlugin === name;
              const schema = pluginSchemas[name];
              return (
                <div key={name} className="rounded-md bg-secondary">
                  <div className="flex items-center justify-between px-3 py-2">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <StatusDot status={pluginStatus} />
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
                        <button
                          onClick={() => setExpandedPlugin(isExpanded ? null : name)}
                          className="p-1 text-muted-foreground transition-colors hover:text-foreground"
                          title={isExpanded ? 'Collapse settings' : 'Expand settings'}
                        >
                          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </button>
                      )}
                      <button
                        onClick={() => {
                          if (expandedPlugin === name) setExpandedPlugin(null);
                          updatePlugins(config.plugins.filter((_, j) => j !== i));
                        }}
                        className="text-xs text-muted-foreground transition-colors hover:text-destructive"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                  {isExpanded && hasSettings && (
                    <div className="border-t border-border/50 px-3 py-3">
                      {schemaLoading[name] && (
                        <p className="text-xs text-muted-foreground">Loading settings...</p>
                      )}
                      {schemaErrors[name] && !schemaLoading[name] && (
                        <p className="text-xs text-destructive">Could not load settings schema</p>
                      )}
                      {schema && !schemaLoading[name] && (
                        <div className="space-y-3">
                          {Object.entries(schema.properties).map(([field, prop]) => {
                            const value = getFieldValue(name, field, prop);
                            const label = fieldLabel(field, prop);

                            if (prop.type === 'boolean') {
                              return (
                                <label key={field} className="flex items-center gap-2 text-xs text-muted-foreground">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(value)}
                                    onChange={(e) => updatePluginConfig(name, field, e.target.checked)}
                                    className="rounded border-input"
                                  />
                                  <span>{label}</span>
                                  {prop.description && (
                                    <span className="text-[10px] text-muted-foreground/60">— {prop.description}</span>
                                  )}
                                </label>
                              );
                            }

                            if (prop.type === 'integer' || prop.type === 'number') {
                              return (
                                <label key={field} className="space-y-1">
                                  <span className="text-xs text-muted-foreground">{label}</span>
                                  {prop.description && (
                                    <span className="ml-2 text-[10px] text-muted-foreground/60">{prop.description}</span>
                                  )}
                                  <input
                                    type="number"
                                    value={value != null ? String(value) : ''}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      updatePluginConfig(name, field, v === '' ? null : prop.type === 'integer' ? parseInt(v) : parseFloat(v));
                                    }}
                                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                                  />
                                </label>
                              );
                            }

                            if (prop.type === 'array' && prop.items?.type === 'string') {
                              const arrValue = Array.isArray(value) ? (value as string[]).join(', ') : '';
                              return (
                                <label key={field} className="space-y-1">
                                  <span className="text-xs text-muted-foreground">{label}</span>
                                  {prop.description && (
                                    <span className="ml-2 text-[10px] text-muted-foreground/60">{prop.description}</span>
                                  )}
                                  <input
                                    type="text"
                                    value={arrValue}
                                    onChange={(e) => {
                                      const parts = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
                                      updatePluginConfig(name, field, parts);
                                    }}
                                    placeholder="Comma-separated values"
                                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
                                  />
                                </label>
                              );
                            }

                            // Default: string or unknown type
                            return (
                              <label key={field} className="space-y-1">
                                <span className="text-xs text-muted-foreground">{label}</span>
                                {prop.description && (
                                  <span className="ml-2 text-[10px] text-muted-foreground/60">{prop.description}</span>
                                )}
                                <input
                                  type="text"
                                  value={value != null ? String(value) : ''}
                                  onChange={(e) => updatePluginConfig(name, field, e.target.value)}
                                  className="w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                                />
                              </label>
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
              <option value="" disabled>Add a plugin...</option>
              {availableToAdd.map(({ name, description }) => (
                <option key={name} value={name}>
                  {name}{description ? ` — ${description}` : ''}
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
