import { useState, useEffect, useCallback } from 'react';
import validator from '@rjsf/validator-ajv8';
import type { RJSFSchema } from '@rjsf/utils';
import { FolderOpen, X, Rocket, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemedForm } from '@/components/rjsf-theme';
import { inlineRefs } from '@/components/rjsf-utils';
import { useServerStatus } from '@/hooks/use-server-status';
import type { SessionInfo, SessionType } from '../../../../preload/types';

/** Fields managed by session-manager — removed entirely from the schema. */
const REMOVED_FIELDS = [
  'listen_host',
  'listen_port',
  'session_service_url',
  'backend_url',
  'resolve_timeout',
];

/** Fields to show first, in this order. */
const TOP_FIELDS = ['embed_target', 'embed_mode', 'system_prompt'];

interface Props {
  type: SessionType;
  editSession?: SessionInfo;
  onLaunch: (
    type: SessionType,
    workingDir: string,
    pluginConfig: Record<string, Record<string, unknown>>,
  ) => void;
  onClose: () => void;
}

function typeLabel(type: SessionType): string {
  switch (type) {
    case 'claude':
      return 'Claude Code';
    case 'codex':
      return 'Codex';
    case 'gemini':
      return 'Gemini CLI';
    case 'claude-desktop':
      return 'Claude Desktop';
  }
}

function frontendPluginFor(type: SessionType): string {
  switch (type) {
    case 'codex':
      return 'codex-frontend';
    case 'gemini':
      return 'gemini-frontend';
    case 'claude':
    case 'claude-desktop':
      return 'claude-frontend';
  }
}

/** Remove fields from JSON schema and reorder so TOP_FIELDS come first. */
function cleanSchema(schema: RJSFSchema): RJSFSchema {
  const props = { ...(schema.properties || {}) };
  for (const f of REMOVED_FIELDS) {
    delete props[f];
  }

  // Reorder: TOP_FIELDS first, then the rest in original order
  const ordered: Record<string, unknown> = {};
  for (const f of TOP_FIELDS) {
    if (props[f]) {
      ordered[f] = props[f];
      delete props[f];
    }
  }
  for (const [k, v] of Object.entries(props)) {
    ordered[k] = v;
  }

  return { ...schema, properties: ordered };
}

export function NewSessionDialog({ type, editSession, onLaunch, onClose }: Props) {
  const isEdit = !!editSession;

  const [workingDir, setWorkingDir] = useState<string | null>(() => {
    if (editSession) return editSession.workingDir;
    const id = crypto.randomUUID().replace(/-/g, '').slice(0, 12);
    return `/tmp/sf-${id}`;
  });

  // Plugin schemas and form data
  const [frontendSchema, setFrontendSchema] = useState<RJSFSchema | null>(null);
  const [frontendData, setFrontendData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);

  const { info: serverInfo } = useServerStatus();

  const serverUrl = serverInfo
    ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}`
    : '';
  const frontendPlugin = frontendPluginFor(type);

  const serverFetch = useCallback(async (url: string) => {
    const res = await window.electronAPI.server.fetch(url);
    return { ok: res.ok, json: () => JSON.parse(res.body) };
  }, []);

  // Load schemas and defaults from server
  useEffect(() => {
    if (!serverUrl) return;

    setLoading(true);
    Promise.all([
      serverFetch(`${serverUrl}/plugins/${frontendPlugin}/schema`),
      serverFetch(`${serverUrl}/plugins/${frontendPlugin}/settings`),
    ])
      .then(([schemaRes, settingsRes]) => {
        const feSchema = schemaRes.ok ? schemaRes.json() : null;
        const feSettings = settingsRes.ok ? settingsRes.json() : null;
        if (feSchema?.properties) setFrontendSchema(cleanSchema(inlineRefs(feSchema)));

        // For edit mode: merge saved config over server defaults
        if (editSession?.pluginConfig?.[frontendPlugin]) {
          setFrontendData({
            ...(feSettings || {}),
            ...editSession.pluginConfig[frontendPlugin],
          });
        } else if (feSettings) {
          setFrontendData(feSettings as Record<string, unknown>);
        }
      })
      .finally(() => setLoading(false));
  }, [serverUrl, serverFetch, editSession, frontendPlugin]);

  const handlePickDir = async () => {
    const dir = await window.electronAPI.session.pickDir();
    if (dir) setWorkingDir(dir);
  };

  const handleLaunch = () => {
    if (!workingDir) return;
    // Strip fields that are managed by session-manager
    const cleanedFrontend = { ...frontendData };
    for (const f of REMOVED_FIELDS) {
      delete cleanedFrontend[f];
    }
    onLaunch(type, workingDir, {
      [frontendPlugin]: cleanedFrontend,
    });
  };

  const canLaunch = !!workingDir && !loading;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-none border border-border bg-card">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">
            {isEdit ? 'Edit' : 'New'} {typeLabel(type)} Session
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body — scrollable */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {/* Working directory */}
          <div>
            <label className="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted-foreground">
              Working Directory
              <span className="text-destructive">*</span>
            </label>
            <button
              onClick={handlePickDir}
              className={`flex w-full items-center gap-2 rounded-none border px-3 py-2 text-sm transition-colors hover:border-foreground/20 ${
                workingDir
                  ? 'border-border bg-background text-foreground'
                  : 'border-destructive/30 bg-destructive/5 text-muted-foreground'
              }`}
            >
              <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate">{workingDir || 'Choose a directory...'}</span>
            </button>
            {!workingDir && (
              <p className="mt-1 text-[10px] text-destructive/70">
                Required — select the directory {typeLabel(type)} will work in
              </p>
            )}
          </div>

          {loading && <p className="text-xs text-muted-foreground">Loading plugin settings...</p>}

          {/* Frontend settings */}
          {frontendSchema && !loading && (
            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Frontend Settings
              </h3>
              <div className="rounded-none border border-border bg-background p-4">
                <ThemedForm
                  schema={frontendSchema}
                  formData={frontendData}
                  formContext={{ serverUrl, serverFetch }}
                  validator={validator}
                  onChange={({ formData }) => {
                    if (formData) setFrontendData(formData);
                  }}
                  omitExtraData
                  uiSchema={{
                    'ui:submitButtonOptions': { norender: true },
                    'ui:order': [...TOP_FIELDS, '*'],
                    active_spec: { 'ui:widget': 'SpecSelectorWidget' },
                    system_prompt: {
                      'ui:widget': 'textarea',
                      'ui:options': { rows: 4 },
                      classNames: 'w-full',
                    },
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="default" size="sm" onClick={handleLaunch} disabled={!canLaunch}>
            {isEdit ? (
              <>
                <Save className="mr-1.5 h-3.5 w-3.5" />
                Save &amp; Restart
              </>
            ) : (
              <>
                <Rocket className="mr-1.5 h-3.5 w-3.5" />
                Launch Session
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
