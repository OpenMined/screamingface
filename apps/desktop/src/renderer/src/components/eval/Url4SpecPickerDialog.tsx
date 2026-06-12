// apps/desktop/src/renderer/src/components/eval/Url4SpecPickerDialog.tsx
//
// SF-259: a modal picker of saved URL4 specs for the "New eval run" dialog.
// Fetches the same endpoint as SpecSelector (GET {serverUrl}/plugins/url4-specs/
// settings, response { specs: { [name]: { expression } } }) but, unlike
// SpecSelector, hands back BOTH the name and the expression so the caller can
// copy them into its Name + URL4-expression fields. Reuses SpecSelector's
// list/preview/search styling. Picking calls onPick({ name, expression });
// cancelling/closing changes nothing.
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Search, X } from 'lucide-react';
import { useServerStatus } from '@/hooks/use-server-status';

interface Spec {
  name: string;
  expression: string;
}

interface Props {
  onClose: () => void;
  onPick: (spec: Spec) => void;
}

async function fetchFromServer(url: string): Promise<{ ok: boolean; json: () => unknown }> {
  const res = await window.electronAPI.server.fetch(url);
  return { ok: res.ok, json: () => JSON.parse(res.body) };
}

export function Url4SpecPickerDialog({ onClose, onPick }: Props) {
  const [specs, setSpecs] = useState<Spec[]>([]);
  const [filter, setFilter] = useState('');
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const hasFetched = useRef(false);

  const { info: serverInfo } = useServerStatus();
  const serverUrl = serverInfo
    ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}`
    : '';

  const loadSpecs = useCallback(() => {
    if (!serverUrl) return;
    if (!hasFetched.current) setLoading(true);
    setFetchError(null);
    fetchFromServer(`${serverUrl}/plugins/url4-specs/settings`)
      .then((res) => {
        if (!res.ok) {
          setFetchError('Server returned error');
          return;
        }
        const data = res.json() as { specs?: Record<string, { expression: string }> };
        if (data.specs) {
          setSpecs(
            Object.entries(data.specs).map(([name, s]) => ({
              name,
              expression: s.expression,
            })),
          );
          hasFetched.current = true;
        }
      })
      .catch((err) => {
        setFetchError(String(err));
      })
      .finally(() => setLoading(false));
  }, [serverUrl]);

  useEffect(() => {
    loadSpecs();
  }, [loadSpecs]);

  const filtered = useMemo(() => {
    if (!filter) return specs;
    const q = filter.toLowerCase();
    return specs.filter(
      (s) => s.name.toLowerCase().includes(q) || s.expression.toLowerCase().includes(q),
    );
  }, [specs, filter]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-none border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">Choose a saved spec</h2>
          <button
            type="button"
            aria-label="Close spec picker"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {/* Search */}
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              autoFocus
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter specs..."
              className="w-full rounded-none border border-input bg-background py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Spec list */}
          <div className="space-y-1">
            {loading && (
              <p className="py-3 text-center text-xs text-muted-foreground">Loading specs...</p>
            )}
            {fetchError && (
              <div className="py-3 text-center">
                <p className="text-xs text-destructive">{fetchError}</p>
                <button
                  onClick={loadSpecs}
                  className="mt-1 text-[10px] text-muted-foreground hover:text-foreground underline"
                >
                  Retry
                </button>
              </div>
            )}
            {!loading && !fetchError && filtered.length === 0 && (
              <p className="py-3 text-center text-xs text-muted-foreground">
                {specs.length === 0 ? 'No specs configured' : 'No matches'}
              </p>
            )}
            {filtered.map((spec) => (
              <button
                key={spec.name}
                type="button"
                className="group flex w-full items-center gap-2 rounded-none border border-border bg-background px-3 py-2 text-left transition-colors hover:border-foreground/20"
                onClick={() => onPick(spec)}
              >
                <div className="min-w-0 flex-1 flex items-center gap-2">
                  <span className="text-xs font-medium text-foreground whitespace-nowrap">
                    {spec.name}
                  </span>
                  {spec.expression && (
                    <span className="truncate text-[10px] text-muted-foreground font-mono">
                      {spec.expression}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
