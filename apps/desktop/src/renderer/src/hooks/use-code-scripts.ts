// apps/desktop/src/renderer/src/hooks/use-code-scripts.ts
//
// Read + CRUD for python-runner scripts (Code Studio). Scripts live in the app
// config under plugin_config['python-runner'].scripts ({ [name]: source }). The
// durable source of truth is sf.json (window.electronAPI.config.write, the path
// the Settings page uses); we also best-effort POST the new settings to the
// running server's in-memory endpoint. The config:changed broadcast keeps this
// and the Settings page in sync. Mirrors use-url4-specs.ts.
import { useCallback, useEffect, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import { useToast } from '@/hooks/use-toast';
import { isValidScriptName, SCRIPT_NAME_HINT } from '@/lib/script-name';

export interface CodeScript {
  name: string;
  source: string;
}

interface AppConfig {
  version: string;
  server: Record<string, unknown>;
  plugins: string[];
  plugin_config: Record<string, Record<string, unknown>>;
}

type ScriptMap = Record<string, string>;

const PLUGIN = 'python-runner';

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

function scriptMapOf(config: AppConfig | null): ScriptMap {
  const raw = (config?.plugin_config?.[PLUGIN]?.scripts ?? {}) as Record<string, unknown>;
  return Object.fromEntries(
    Object.entries(raw).map(([name, src]) => [name, typeof src === 'string' ? src : '']),
  );
}

export function useCodeScripts() {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const { toast } = useToast();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    window.electronAPI.config
      .read()
      .then((c) => {
        if (!cancelled) {
          setConfig(c as unknown as AppConfig);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e as Error);
          setLoading(false);
        }
      });
    const unsub = window.electronAPI.config.onChanged((c) => setConfig(c as unknown as AppConfig));
    return () => {
      cancelled = true;
      unsub();
    };
  }, []);

  const scriptMap = scriptMapOf(config);
  const scripts: CodeScript[] = Object.entries(scriptMap).map(([name, source]) => ({
    name,
    source,
  }));

  const persist = useCallback(
    async (nextScripts: ScriptMap, errTitle: string): Promise<boolean> => {
      if (!config) return false;
      const settings = { ...(config.plugin_config[PLUGIN] ?? {}), scripts: nextScripts };
      const next: AppConfig = {
        ...config,
        plugin_config: { ...config.plugin_config, [PLUGIN]: settings },
      };
      try {
        if (base) {
          try {
            const res = await window.electronAPI.server.fetch(
              `${base}/plugins/${PLUGIN}/settings/validate`,
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
              },
            );
            if (!res.ok) {
              let detail = `HTTP ${res.status}`;
              try {
                detail = (JSON.parse(res.body) as { detail?: string }).detail ?? detail;
              } catch {
                /* non-JSON body */
              }
              toast({ variant: 'error', title: errTitle, description: detail });
              return false;
            }
            void window.electronAPI.server.fetch(`${base}/plugins/${PLUGIN}/settings`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(settings),
            });
          } catch {
            /* server unreachable — persist to disk anyway */
          }
        }
        await window.electronAPI.config.write(next as unknown as Record<string, unknown>);
        setConfig(next);
        return true;
      } catch (e) {
        toast({ variant: 'error', title: errTitle, description: (e as Error).message });
        return false;
      }
    },
    [config, base, toast],
  );

  const rejectName = useCallback(
    (name: string): boolean => {
      if (!isValidScriptName(name)) {
        toast({ variant: 'error', title: 'Invalid name', description: SCRIPT_NAME_HINT });
        return true;
      }
      if (name in scriptMap) {
        toast({
          variant: 'error',
          title: 'Name in use',
          description: `A script named "${name}" already exists.`,
        });
        return true;
      }
      return false;
    },
    [scriptMap, toast],
  );

  const createScript = useCallback(
    async (name: string): Promise<boolean> => {
      const trimmed = name.trim();
      if (rejectName(trimmed)) return false;
      return persist({ ...scriptMap, [trimmed]: '' }, 'Could not create script');
    },
    [scriptMap, persist, rejectName],
  );

  const renameScript = useCallback(
    async (oldName: string, newName: string): Promise<boolean> => {
      const trimmed = newName.trim();
      if (trimmed === oldName) return false;
      if (rejectName(trimmed)) return false;
      const next: ScriptMap = Object.fromEntries(
        Object.entries(scriptMap).map(([k, v]) => (k === oldName ? [trimmed, v] : [k, v])),
      );
      return persist(next, 'Could not rename script');
    },
    [scriptMap, persist, rejectName],
  );

  const deleteScript = useCallback(
    async (name: string): Promise<boolean> => {
      if (!(name in scriptMap)) return false;
      const next = { ...scriptMap };
      delete next[name];
      return persist(next, 'Could not delete script');
    },
    [scriptMap, persist],
  );

  const saveSource = useCallback(
    async (name: string, source: string): Promise<boolean> => {
      if (!(name in scriptMap)) return false;
      return persist({ ...scriptMap, [name]: source }, 'Could not save script');
    },
    [scriptMap, persist],
  );

  return { scripts, loading, error, createScript, renameScript, deleteScript, saveSource };
}
