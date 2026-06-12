import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface Props {
  onCancel: () => void;
  onCreate: (label?: string) => void;
}

export function AddPrivateDataDialog({ onCancel, onCreate }: Props) {
  const [label, setLabel] = useState('');
  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-background/80">
      <div className="w-80 border border-border bg-card p-4">
        <h2 className="mb-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          New private data
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          A uuid7 is assigned automatically. The label is optional and only used for navigation.
        </p>
        <Input
          autoFocus
          placeholder="Label (optional)"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onCreate(label.trim() || undefined)}
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => onCreate(label.trim() || undefined)}>
            Create
          </Button>
        </div>
      </div>
    </div>
  );
}
