import { useState, useEffect, useCallback } from 'react';
import validator from '@rjsf/validator-ajv8';
import type { RJSFSchema } from '@rjsf/utils';
import { FolderOpen, X, Rocket } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemedForm } from '@/components/rjsf-theme';
import { inlineRefs } from '@/components/rjsf-utils';
import { useServerStatus } from '@/hooks/use-server-status';
import type { SessionType } from '../../../../preload/types';

/** Fields managed by session-manager or not applicable per-session — hidden from the user. */
const HIDDEN_FRONTEND_FIELDS = [
  'listen_host',
  'listen_port',
  'session_service_url',
];

interface Props {
  type: SessionType;
  onLaunch: (
    type: SessionType,
    workingDir: string,
    pluginConfig: Record<string, Record<string, unknown>>,
  ) => void;
  onClose: () => void;
}

function typeLabel(type: SessionType): string {
  switch (type) {
    case 'claude': return 'Claude Code';
    case 'codex': return 'Codex';
    case 'gemini': return 'Gemini CLI';
    case 'claude-desktop': return 'Claude Desktop';
  }
}

/** Build a uiSchema that hides specific fields. */
function hideFields(fields: string[]): Record<string, unknown> {
  const ui: Record<string, unknown> = {
    'ui:submitButtonOptions': { norender: true },
  };
  for (const f of fields) {
    ui[f] = { 'ui:widget': 'hidden' };
  }
  return ui;
}

export function NewSessionDialog({ type, onLaunch, onClose }: Props) {
  const [workingDir, setWorkingDir] = useState<string | null>(null);

  // Plugin schemas and form data
  const [frontendSchema, setFrontendSchema] = useState<RJSFSchema | null>(null);
  const [frontendData, setFrontendData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);

  const { info: serverInfo } = useServerStatus();

  const serverUrl = serverInfo
    ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}`
    : '';

  const serverFetch = useCallback(
    async (url: string) => {
      const res = await window.electronAPI.server.fetch(url);
      return { ok: res.ok, json: () => JSON.parse(res.body) };
    },
    [],
  );

  // Load schemas and defaults from server
  useEffect(() => {
    if (!serverUrl) return;

    setLoading(true);
    Promise.all([
      serverFetch(`${serverUrl}/plugins/claude-frontend/schema`),
      serverFetch(`${serverUrl}/plugins/claude-frontend/settings`),
    ])
      .then(([schemaRes, settingsRes]) => {
        const feSchema = schemaRes.ok ? schemaRes.json() : null;
        const feSettings = settingsRes.ok ? settingsRes.json() : null;
        if (feSchema?.properties) setFrontendSchema(inlineRefs(feSchema));
        if (feSettings) setFrontendData(feSettings as Record<string, unknown>);
      })
      .finally(() => setLoading(false));
  }, [serverUrl, serverFetch]);

  const handlePickDir = async () => {
    const dir = await window.electronAPI.session.pickDir();
    if (dir) setWorkingDir(dir);
  };

  const handleLaunch = () => {
    if (!workingDir) return;
    // Strip fields that are managed by session-manager or not applicable per-session
    const cleanedFrontend = { ...frontendData };
    for (const f of HIDDEN_FRONTEND_FIELDS) {
      delete cleanedFrontend[f];
    }
    onLaunch(type, workingDir, {
      'claude-frontend': cleanedFrontend,
    });
  };

  const canLaunch = !!workingDir && !loading;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">
            New {typeLabel(type)} Session
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
              className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors hover:border-foreground/20 ${
                workingDir
                  ? 'border-border bg-background text-foreground'
                  : 'border-destructive/30 bg-destructive/5 text-muted-foreground'
              }`}
            >
              <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate">
                {workingDir || 'Choose a directory...'}
              </span>
            </button>
            {!workingDir && (
              <p className="mt-1 text-[10px] text-destructive/70">Required — select the directory Claude will work in</p>
            )}
          </div>

          {loading && (
            <p className="text-xs text-muted-foreground">Loading plugin settings...</p>
          )}

          {/* Frontend settings */}
          {frontendSchema && !loading && (
            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Frontend Settings
              </h3>
              <div className="rounded-lg border border-border bg-background p-4">
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
                    ...hideFields(HIDDEN_FRONTEND_FIELDS),
                    active_spec: { 'ui:widget': 'SpecSelectorWidget' },
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
          <Button
            variant="default"
            size="sm"
            onClick={handleLaunch}
            disabled={!canLaunch}
          >
            <Rocket className="mr-1.5 h-3.5 w-3.5" />
            Launch Session
          </Button>
        </div>
      </div>
    </div>
  );
}
