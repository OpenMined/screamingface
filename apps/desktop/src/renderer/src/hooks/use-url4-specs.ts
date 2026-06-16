// apps/desktop/src/renderer/src/hooks/use-url4-specs.ts
//
// Read + CRUD for url4 specs (URL4 Studio). Specs live in the local app config
// under plugin_config['url4-specs'].specs ({ [name]: { expression } }). The
// durable source of truth is sf.json, written via window.electronAPI.config.write
// (same path the Settings page uses); we also best-effort POST the new settings to
// the running server's in-memory endpoint so spec resolution sees them without a
// disk re-read. The config:changed broadcast keeps this and the Settings page in sync.
import { useCallback, useEffect, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import { useToast } from '@/hooks/use-toast';

export interface Url4Spec {
  name: string;
  expression: string;
}

interface AppConfig {
  version: string;
  server: Record<string, unknown>;
  plugins: string[];
  plugin_config: Record<string, Record<string, unknown>>;
}

type SpecMap = Record<string, { expression: string }>;

const PLUGIN = 'url4-specs';

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

function specMapOf(config: AppConfig | null): SpecMap {
  const raw = (config?.plugin_config?.[PLUGIN]?.specs ?? {}) as Record<
    string,
    { expression?: string }
  >;
  return Object.fromEntries(
    Object.entries(raw).map(([name, v]) => [name, { expression: v?.expression ?? '' }]),
  );
}

export function useUrl4Specs() {
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
    // External edits (e.g. the Settings page) re-broadcast the whole config.
    const unsub = window.electronAPI.config.onChanged((c) => setConfig(c as unknown as AppConfig));
    return () => {
      cancelled = true;
      unsub();
    };
  }, []);

  const specMap = specMapOf(config);
  const specs: Url4Spec[] = Object.entries(specMap).map(([name, v]) => ({
    name,
    expression: v.expression,
  }));

  // Persist a new spec map: validate (best-effort) → durable config.write → dual-write in-memory.
  const persist = useCallback(
    async (nextSpecs: SpecMap, errTitle: string): Promise<boolean> => {
      if (!config) return false;
      const settings = { ...(config.plugin_config[PLUGIN] ?? {}), specs: nextSpecs };
      const next: AppConfig = {
        ...config,
        plugin_config: { ...config.plugin_config, [PLUGIN]: settings },
      };
      try {
        if (base) {
          // Server validation blocks the save only on an explicit invalid response;
          // if the server is unreachable we save anyway (config read/write is local).
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
            // Best-effort: push to the running server's in-memory settings too.
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
        setConfig(next); // optimistic; the config:changed broadcast reconciles
        return true;
      } catch (e) {
        toast({ variant: 'error', title: errTitle, description: (e as Error).message });
        return false;
      }
    },
    [config, base, toast],
  );

  const createSpec = useCallback(
    async (name: string): Promise<boolean> => {
      const trimmed = name.trim();
      if (!trimmed) return false;
      if (trimmed in specMap) {
        toast({
          variant: 'error',
          title: 'Name in use',
          description: `A spec named "${trimmed}" already exists.`,
        });
        return false;
      }
      return persist({ ...specMap, [trimmed]: { expression: '' } }, 'Could not create spec');
    },
    [specMap, persist, toast],
  );

  const renameSpec = useCallback(
    async (oldName: string, newName: string): Promise<boolean> => {
      const trimmed = newName.trim();
      if (!trimmed || trimmed === oldName) return false;
      if (trimmed in specMap) {
        toast({
          variant: 'error',
          title: 'Name in use',
          description: `A spec named "${trimmed}" already exists.`,
        });
        return false;
      }
      // Rebuild preserving order, swapping the key in place.
      const next: SpecMap = Object.fromEntries(
        Object.entries(specMap).map(([k, v]) => (k === oldName ? [trimmed, v] : [k, v])),
      );
      return persist(next, 'Could not rename spec');
    },
    [specMap, persist, toast],
  );

  const deleteSpec = useCallback(
    async (name: string): Promise<boolean> => {
      if (!(name in specMap)) return false;
      const next = { ...specMap };
      delete next[name];
      return persist(next, 'Could not delete spec');
    },
    [specMap, persist],
  );

  const saveExpression = useCallback(
    async (name: string, expression: string): Promise<boolean> => {
      if (!(name in specMap)) return false;
      return persist(
        { ...specMap, [name]: { ...specMap[name], expression } },
        'Could not save expression',
      );
    },
    [specMap, persist],
  );

  return { specs, loading, error, createSpec, renameSpec, deleteSpec, saveExpression };
}
