import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Search, X, Eye, Check } from 'lucide-react';
import { useServerStatus } from '@/hooks/use-server-status';
import { Url4Viewer } from './Url4Viewer';

interface Spec {
  name: string;
  expression: string;
}

interface SpecSelectorProps {
  value: string | null;
  onChange: (value: string | null) => void;
  /** Fallback spec names (from RJSF enumOptions) when fetch hasn't completed */
  fallbackNames?: string[];
}

async function fetchFromServer(url: string): Promise<{ ok: boolean; json: () => unknown }> {
  const res = await window.electronAPI.server.fetch(url);
  return { ok: res.ok, json: () => JSON.parse(res.body) };
}

export function SpecSelector({ value, onChange, fallbackNames }: SpecSelectorProps) {
  const [fetchedSpecs, setFetchedSpecs] = useState<Spec[]>([]);
  const [filter, setFilter] = useState('');
  const [previewSpec, setPreviewSpec] = useState<Spec | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const hasFetched = useRef(false);

  const { info: serverInfo } = useServerStatus();
  const serverUrl = serverInfo
    ? `${serverInfo.scheme}://${serverInfo.host === '0.0.0.0' ? 'localhost' : serverInfo.host}:${serverInfo.port}`
    : '';

  // Use fetched specs if available, otherwise fall back to enum names from schema
  const specs =
    fetchedSpecs.length > 0
      ? fetchedSpecs
      : (fallbackNames ?? []).map((name) => ({ name, expression: '' }));

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
          setFetchedSpecs(
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
    const interval = setInterval(loadSpecs, 3000);
    return () => clearInterval(interval);
  }, [loadSpecs]);

  const filtered = useMemo(() => {
    if (!filter) return specs;
    const q = filter.toLowerCase();
    return specs.filter(
      (s) => s.name.toLowerCase().includes(q) || s.expression.toLowerCase().includes(q),
    );
  }, [specs, filter]);

  return (
    <div>
      {/* Search */}
      <div className="relative mb-2">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter specs..."
          className="w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      {/* Spec list */}
      <div className="space-y-1 max-h-48 overflow-y-auto">
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
        {filtered.map((spec) => {
          const isActive = value === spec.name;
          return (
            <div
              key={spec.name}
              className={`group flex items-center gap-2 rounded-md border px-3 py-2 transition-colors cursor-pointer ${
                isActive
                  ? 'border-chart-3/50 bg-chart-3/10'
                  : 'border-border bg-background hover:border-foreground/20'
              }`}
              onClick={() => onChange(isActive ? null : spec.name)}
            >
              {/* Selection indicator */}
              <div
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                  isActive ? 'border-chart-3 bg-chart-3 text-white' : 'border-muted-foreground/30'
                }`}
              >
                {isActive && <Check className="h-2.5 w-2.5" />}
              </div>

              {/* Spec info — row layout: name + expression side by side */}
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

              {/* Preview button — only when expression is available */}
              {spec.expression && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setPreviewSpec(previewSpec?.name === spec.name ? null : spec);
                  }}
                  className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
                  title="Preview expression"
                >
                  <Eye className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Preview popup */}
      {previewSpec && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setPreviewSpec(null)}
        >
          <div
            className="w-full max-w-lg rounded-[10px] border border-border bg-card p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm font-semibold text-foreground">{previewSpec.name}</span>
              <button
                onClick={() => setPreviewSpec(null)}
                className="rounded p-1 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="rounded-lg border border-border bg-background p-4">
              <Url4Viewer
                expression={previewSpec.expression}
                serverUrl={serverUrl}
                fetchFn={fetchFromServer}
                mode="expanded"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
