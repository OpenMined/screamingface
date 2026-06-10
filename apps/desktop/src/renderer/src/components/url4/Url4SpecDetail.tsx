// apps/desktop/src/renderer/src/components/url4/Url4SpecDetail.tsx
//
// Right pane of URL4 Studio: view form for one spec. Inline-editable name,
// read-only expression (Url4Field), and an "Edit expression" button that opens
// the same CodeEditorPopup Eval Studio uses (lazy + url4 highlighting). Delete
// lives here with a confirm, mirroring EvalRunDetail.
import { useState, lazy, Suspense } from 'react';
import { Pencil, Trash2, Save, Check, X } from 'lucide-react';
import type { OnMount } from '@monaco-editor/react';
import { useServerStatus } from '@/hooks/use-server-status';
import { registerUrl4Language } from '@/lib/url4-language';
import { Url4Field } from '@/components/Url4Field';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import type { Url4Spec } from '@/hooks/use-url4-specs';

const CodeEditorPopup = lazy(() => import('@/components/CodeEditorPopup'));

const mountUrl4Editor: OnMount = (editor, monaco) => {
  registerUrl4Language(monaco);
  const model = editor.getModel();
  if (model) monaco.editor.setModelLanguage(model, 'url4');
};

interface Props {
  spec: Url4Spec;
  onRename: (oldName: string, newName: string) => void;
  onDelete: (name: string) => void;
  onSaveExpression: (name: string, expression: string) => void;
}

export function Url4SpecDetail({ spec, onRename, onDelete, onSaveExpression }: Props) {
  const { info } = useServerStatus();
  const serverUrl = info
    ? `${info.scheme}://${info.host === '0.0.0.0' ? 'localhost' : info.host}:${info.port}`
    : '';

  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(spec.name);
  const [editingExpr, setEditingExpr] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const commitName = (): void => {
    const next = nameDraft.trim();
    setEditingName(false);
    if (next && next !== spec.name) onRename(spec.name, next);
    else setNameDraft(spec.name);
  };

  const startRename = (): void => {
    setNameDraft(spec.name);
    setEditingName(true);
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
                  aria-label="Spec name"
                  className="min-w-0 flex-1 rounded-md border border-input bg-background px-2 py-1 text-base font-semibold"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitName();
                    if (e.key === 'Escape') {
                      setNameDraft(spec.name);
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
                    setNameDraft(spec.name);
                    setEditingName(false);
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </>
            ) : (
              <>
                <h2 className="min-w-0 flex-1 truncate text-base font-semibold">{spec.name}</h2>
                <Button variant="ghost" size="sm" aria-label="Rename spec" onClick={startRename}>
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

          <span className="mb-1.5 block text-xs font-medium text-muted-foreground">
            URL4 expression
          </span>
          <div className="mb-3 rounded border border-border bg-muted/30">
            <Url4Field value={spec.expression} serverUrl={serverUrl} readOnly />
          </div>
          <Button variant="outline" size="sm" onClick={() => setEditingExpr(true)}>
            <Pencil className="h-3.5 w-3.5" /> Edit expression
          </Button>
        </header>
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title="Delete this spec?"
          message={`"${spec.name}" will be permanently removed from your URL4 specs. This can't be undone.`}
          confirmLabel="Delete"
          destructive
          onConfirm={() => {
            setConfirmingDelete(false);
            onDelete(spec.name);
          }}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
      {editingExpr && (
        <Suspense fallback={null}>
          <CodeEditorPopup
            title={`Edit URL4 expression — ${spec.name}`}
            language="url4"
            value={spec.expression}
            inset="10%"
            onEditorMount={mountUrl4Editor}
            confirmLabel="Save"
            confirmIcon={<Save className="h-4 w-4" />}
            onSave={(expr) => onSaveExpression(spec.name, expr)}
            onClose={() => setEditingExpr(false)}
          />
        </Suspense>
      )}
    </div>
  );
}
