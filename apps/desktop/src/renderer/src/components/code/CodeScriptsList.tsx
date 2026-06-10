// apps/desktop/src/renderer/src/components/code/CodeScriptsList.tsx
//
// Left pane of Code Studio: searchable list of python-runner scripts. Mirrors
// Url4SpecsList; subtitle is the first non-blank line of the source.
import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CodeScript } from '@/hooks/use-code-scripts';

interface Props {
  scripts: CodeScript[];
  selectedName: string | null;
  onSelect: (name: string) => void;
  loading?: boolean;
  error?: Error | null;
}

function firstLine(source: string): string {
  const line = source.split('\n').find((l) => l.trim().length > 0);
  return line?.trim() ?? '(empty)';
}

export function CodeScriptsList({ scripts, selectedName, onSelect, loading, error }: Props) {
  const [filter, setFilter] = useState('');

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return scripts;
    return scripts.filter(
      (s) => s.name.toLowerCase().includes(q) || s.source.toLowerCase().includes(q),
    );
  }, [scripts, filter]);

  if (loading && scripts.length === 0) {
    return <div className="p-6 text-sm text-muted-foreground">Loading scripts…</div>;
  }
  if (error) {
    return (
      <div className="p-6 text-sm text-destructive">Failed to load scripts: {error.message}</div>
    );
  }
  if (scripts.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <p className="mb-2 font-medium">No scripts yet.</p>
        <p className="text-xs">Use "New script" above to create one.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="border-b border-border/50 p-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            aria-label="Filter scripts"
            className="w-full rounded-md border border-input bg-background py-1.5 pr-2 pl-7 text-sm"
            placeholder="Filter scripts…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="p-6 text-center text-xs text-muted-foreground">
          No scripts match "{filter}".
        </div>
      ) : (
        filtered.map((script) => {
          const active = script.name === selectedName;
          return (
            <div
              key={script.name}
              onClick={() => onSelect(script.name)}
              className={cn(
                'cursor-pointer border-b border-border/50 px-6 py-3 transition-colors hover:bg-accent/40',
                active && 'bg-accent/60',
              )}
            >
              <div className="truncate font-medium text-foreground">{script.name}.py</div>
              <div className="truncate font-mono text-xs text-muted-foreground">
                {firstLine(script.source)}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
