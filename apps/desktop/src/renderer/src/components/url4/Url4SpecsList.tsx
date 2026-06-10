// apps/desktop/src/renderer/src/components/url4/Url4SpecsList.tsx
//
// Left pane of URL4 Studio: searchable list of url4 specs. Mirrors EvalRunsList's
// row styling; delete/rename live in the detail pane (like Eval Studio).
import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Url4Spec } from '@/hooks/use-url4-specs';

interface Props {
  specs: Url4Spec[];
  selectedName: string | null;
  onSelect: (name: string) => void;
  loading?: boolean;
  error?: Error | null;
}

export function Url4SpecsList({ specs, selectedName, onSelect, loading, error }: Props) {
  const [filter, setFilter] = useState('');

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return specs;
    return specs.filter(
      (s) => s.name.toLowerCase().includes(q) || s.expression.toLowerCase().includes(q),
    );
  }, [specs, filter]);

  if (loading && specs.length === 0) {
    return <div className="p-6 text-sm text-muted-foreground">Loading specs…</div>;
  }
  if (error) {
    return (
      <div className="p-6 text-sm text-destructive">Failed to load specs: {error.message}</div>
    );
  }
  if (specs.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <p className="mb-2 font-medium">No URL4 specs yet.</p>
        <p className="text-xs">Use "New spec" above to create one.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="border-b border-border/50 p-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            aria-label="Filter specs"
            className="w-full rounded-md border border-input bg-background py-1.5 pr-2 pl-7 text-sm"
            placeholder="Filter specs…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="p-6 text-center text-xs text-muted-foreground">
          No specs match "{filter}".
        </div>
      ) : (
        filtered.map((spec) => {
          const active = spec.name === selectedName;
          return (
            <div
              key={spec.name}
              onClick={() => onSelect(spec.name)}
              className={cn(
                'cursor-pointer border-b border-border/50 px-6 py-3 transition-colors hover:bg-accent/40',
                active && 'bg-accent/60',
              )}
            >
              <div className="truncate font-medium text-foreground">{spec.name}</div>
              <div className="truncate font-mono text-xs text-muted-foreground">
                {spec.expression || '(empty)'}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
