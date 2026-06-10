// apps/desktop/src/renderer/src/components/url4/AddUrl4SpecDialog.tsx
//
// "New spec" dialog for URL4 Studio: name only. The expression starts empty and
// is edited afterwards via the CodeEditorPopup in the detail pane.
import { useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  existingNames: string[];
  onClose: () => void;
  onCreate: (name: string) => void;
}

export function AddUrl4SpecDialog({ existingNames, onClose, onCreate }: Props) {
  const [name, setName] = useState('');
  const trimmed = name.trim();
  const duplicate = existingNames.includes(trimmed);
  const canCreate = trimmed.length > 0 && !duplicate;

  const handleCreate = (): void => {
    if (!canCreate) return;
    onCreate(trimmed);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex w-full max-w-md flex-col rounded-[10px] border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">New URL4 spec</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 py-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">
              Name <span className="text-destructive">*</span>
            </span>
            <input
              autoFocus
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="e.g. my-ensemble"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreate();
              }}
            />
          </label>
          {duplicate && (
            <p className="mt-1.5 text-xs text-destructive">
              A spec named "{trimmed}" already exists.
            </p>
          )}
          <p className="mt-1.5 text-xs text-muted-foreground">
            The expression starts empty — edit it from the spec view.
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={!canCreate}>
            Create
          </Button>
        </div>
      </div>
    </div>
  );
}
