// apps/desktop/src/renderer/src/components/code/AddCodeScriptDialog.tsx
//
// "New script" dialog for Code Studio: name only (a Python identifier). The
// source starts empty and is edited afterwards via the CodeEditorPopup.
import { useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { isValidScriptName, SCRIPT_NAME_HINT } from '@/lib/script-name';

interface Props {
  existingNames: string[];
  onClose: () => void;
  onCreate: (name: string) => void;
}

export function AddCodeScriptDialog({ existingNames, onClose, onCreate }: Props) {
  const [name, setName] = useState('');
  const trimmed = name.trim();
  const duplicate = existingNames.includes(trimmed);
  const invalid = trimmed.length > 0 && !isValidScriptName(trimmed);
  const canCreate = trimmed.length > 0 && !duplicate && !invalid;

  const handleCreate = (): void => {
    if (!canCreate) return;
    onCreate(trimmed);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex w-full max-w-md flex-col rounded-[10px] border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">New python script</h2>
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
              placeholder="e.g. check_correct"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreate();
              }}
            />
          </label>
          {duplicate && (
            <p className="mt-1.5 text-xs text-destructive">
              A script named "{trimmed}" already exists.
            </p>
          )}
          {invalid && <p className="mt-1.5 text-xs text-destructive">{SCRIPT_NAME_HINT}</p>}
          <p className="mt-1.5 text-xs text-muted-foreground">
            Servable at <code>/data/code/{trimmed || '<name>'}.py</code>. The code starts empty —
            edit it from the script view.
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
