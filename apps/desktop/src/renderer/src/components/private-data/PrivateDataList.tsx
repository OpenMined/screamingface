import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { PrivateItem } from '@/lib/private-data-api';

interface Props {
  items: PrivateItem[];
  selectedId: string | null;
  onSelect: (uuid: string) => void;
}

function displayName(item: PrivateItem): string {
  return item.label?.trim() || `private/${item.uuid.slice(0, 8)}`;
}

export function PrivateDataList({ items, selectedId, onSelect }: Props) {
  const [filter, setFilter] = useState('');
  const q = filter.trim().toLowerCase();
  const shown = q
    ? items.filter(
        (i) => (i.label ?? '').toLowerCase().includes(q) || i.uuid.toLowerCase().includes(q),
      )
    : items;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-2">
        <Input
          placeholder="Search private data…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className="flex-1 overflow-y-auto">
        {shown.map((item) => (
          <button
            key={item.uuid}
            onClick={() => onSelect(item.uuid)}
            className={cn(
              'flex w-full flex-col items-start gap-0.5 border-b border-border px-3 py-2 text-left text-sm transition-colors',
              item.uuid === selectedId ? 'bg-accent text-foreground' : 'hover:bg-accent/50',
            )}
          >
            <span className="font-medium">{displayName(item)}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{item.uuid}</span>
          </button>
        ))}
        {shown.length === 0 && <p className="p-3 text-sm text-muted-foreground">No entries.</p>}
      </div>
    </div>
  );
}
