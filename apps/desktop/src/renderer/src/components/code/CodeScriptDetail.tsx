// apps/desktop/src/renderer/src/components/code/CodeScriptDetail.tsx
//
// Right pane of Code Studio: view form for one python script. Inline-editable
// name (Python identifier), read-only <pre> source preview, and an "Edit code"
// button that opens the shared CodeEditorPopup with python highlighting (no
// Format — that's url4-only). Delete behind a confirm. Mirrors Url4SpecDetail.
import { useState, lazy, Suspense } from 'react';
import { Pencil, Trash2, Save, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import type { CodeScript } from '@/hooks/use-code-scripts';

const CodeEditorPopup = lazy(() => import('@/components/CodeEditorPopup'));

interface Props {
  script: CodeScript;
  onRename: (oldName: string, newName: string) => void;
  onDelete: (name: string) => void;
  onSaveSource: (name: string, source: string) => void;
}

export function CodeScriptDetail({ script, onRename, onDelete, onSaveSource }: Props) {
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(script.name);
  const [editingCode, setEditingCode] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const commitName = (): void => {
    const next = nameDraft.trim();
    setEditingName(false);
    if (next && next !== script.name) onRename(script.name, next);
    else setNameDraft(script.name);
  };

  return (
    <div className="flex h-full w-full min-w-0 flex-col">
      <div className="min-w-0 flex-1 overflow-y-auto">
        <header className="border-b border-border px-6 py-4">
          <div className="mb-3 flex items-center gap-3">
            {editingName ? (
              <>
                <input
                  autoFocus
                  aria-label="Script name"
                  className="min-w-0 flex-1 rounded-md border border-input bg-background px-2 py-1 text-base font-semibold"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitName();
                    if (e.key === 'Escape') {
                      setNameDraft(script.name);
                      setEditingName(false);
                    }
                  }}
                  onBlur={commitName}
                />
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Confirm name"
                  onClick={commitName}
                >
                  <Check className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Cancel rename"
                  onClick={() => {
                    setNameDraft(script.name);
                    setEditingName(false);
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </>
            ) : (
              <>
                <h2 className="min-w-0 flex-1 truncate text-base font-semibold">
                  {script.name}.py
                </h2>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Rename script"
                  onClick={() => {
                    setNameDraft(script.name);
                    setEditingName(true);
                  }}
                >
                  <Pencil className="h-3.5 w-3.5" /> Rename
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => setConfirmingDelete(true)}
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </Button>
              </>
            )}
          </div>

          <span className="mb-1.5 block text-xs font-medium text-muted-foreground">Source</span>
          <pre className="mb-3 max-h-[60vh] overflow-auto rounded border border-border bg-muted/30 p-3 font-mono text-xs whitespace-pre">
            {script.source || '(empty)'}
          </pre>
          <Button variant="outline" size="sm" onClick={() => setEditingCode(true)}>
            <Pencil className="h-3.5 w-3.5" /> Edit code
          </Button>
        </header>
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title="Delete this script?"
          message={`"${script.name}.py" will be permanently removed from your python scripts. This can't be undone.`}
          confirmLabel="Delete"
          destructive
          onConfirm={() => {
            setConfirmingDelete(false);
            onDelete(script.name);
          }}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
      {editingCode && (
        <Suspense fallback={null}>
          <CodeEditorPopup
            title={`Edit ${script.name}.py`}
            language="python"
            value={script.source}
            inset="10%"
            onSave={(source) => onSaveSource(script.name, source)}
            onClose={() => setEditingCode(false)}
          />
        </Suspense>
      )}
    </div>
  );
}
