// apps/desktop/src/renderer/src/components/rjsf-CodeDictField.tsx
//
// Custom RJSF field for a `dict[str, str]` of code, routed via the
// `x-code-editor` schema hint. Renders a file list with add/delete and opens a
// Monaco editor popup (lazy-loaded) to edit each entry's source. Used for
// python-runner `scripts` (SF-247).
import { Suspense, lazy, useState } from 'react';
import type { FieldProps } from '@rjsf/utils';
import { FileCode, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { isValidScriptName, SCRIPT_NAME_HINT } from '@/lib/script-name';

const CodeEditorPopup = lazy(() => import('@/components/CodeEditorPopup'));

function languageOf(uiSchema: FieldProps['uiSchema']): string {
  const opts = (uiSchema?.['ui:options'] ?? {}) as Record<string, unknown>;
  return typeof opts.language === 'string' ? opts.language : 'plaintext';
}

export function CodeDictField(props: FieldProps) {
  const data = (props.formData ?? {}) as Record<string, string>;
  const language = languageOf(props.uiSchema);

  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);

  const names = Object.keys(data);

  const handleAdd = (): void => {
    const name = newName.trim();
    if (!isValidScriptName(name)) {
      setNameError(SCRIPT_NAME_HINT);
      return;
    }
    if (name in data) {
      setNameError('A script with that name already exists.');
      return;
    }
    props.onChange({ ...data, [name]: '' });
    setNewName('');
    setAdding(false);
    setNameError(null);
    setEditing(name);
  };

  const handleDelete = (name: string): void => {
    const next = { ...data };
    delete next[name];
    props.onChange(next);
  };

  return (
    <div className="space-y-2">
      <ul className="divide-y divide-border rounded-md border border-border">
        {names.length === 0 && (
          <li className="px-3 py-2 text-xs text-muted-foreground">No scripts yet.</li>
        )}
        {names.map((name) => (
          <li key={name} className="flex items-center gap-2 px-3 py-2">
            <button
              type="button"
              className="flex flex-1 items-center gap-2 text-left text-sm hover:text-primary"
              onClick={() => setEditing(name)}
            >
              <FileCode className="h-4 w-4 text-muted-foreground" />
              {name}.py
            </button>
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => handleDelete(name)}
              aria-label={`Delete ${name}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </li>
        ))}
      </ul>

      {adding ? (
        <div className="flex items-start gap-2">
          <div className="flex-1">
            <input
              autoFocus
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              placeholder="script_name"
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value);
                setNameError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAdd();
              }}
            />
            {nameError && <p className="mt-1 text-[11px] text-destructive">{nameError}</p>}
          </div>
          <Button size="sm" onClick={handleAdd}>
            Add
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setAdding(false);
              setNewName('');
              setNameError(null);
            }}
          >
            Cancel
          </Button>
        </div>
      ) : (
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
          <Plus className="h-3.5 w-3.5" /> Add script
        </Button>
      )}

      {editing !== null && (
        <Suspense fallback={null}>
          <CodeEditorPopup
            title={`${editing}.py`}
            language={language}
            value={data[editing] ?? ''}
            onSave={(val) => props.onChange({ ...data, [editing]: val })}
            onClose={() => setEditing(null)}
          />
        </Suspense>
      )}
    </div>
  );
}
