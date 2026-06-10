// apps/desktop/src/renderer/src/components/CodeEditorPopup.tsx
//
// Full-screen-ish (5% inset) Monaco editor popup for editing a single code
// blob. Default export so it can be React.lazy()'d — that keeps the heavy
// monaco bundle out of the settings form until the user opens an editor.
import { useState, type ReactNode } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import { X, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
// Side-effect: configure monaco to run bundled (no CDN) before it mounts.
import '@/lib/monaco-setup';

interface Props {
  title: string;
  language: string;
  value: string;
  onSave: (value: string) => void;
  onClose: () => void;
  /** Inset from every app border (CSS length). Defaults to 5%. */
  inset?: string;
  /** Monaco onMount hook — e.g. to register a custom language like url4. */
  onEditorMount?: OnMount;
  confirmLabel?: string;
  confirmIcon?: ReactNode;
}

export default function CodeEditorPopup({
  title,
  language,
  value,
  onSave,
  onClose,
  inset = '5%',
  onEditorMount,
  confirmLabel = 'Save',
  confirmIcon = <Save className="h-4 w-4" />,
}: Props) {
  const [draft, setDraft] = useState(value);

  return (
    <div className="fixed inset-0 z-50 bg-black/50">
      {/* Inset from every app border (default 5%). */}
      <div
        style={{ inset }}
        className="absolute flex flex-col overflow-hidden rounded-[10px] border border-border bg-card shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1">
          <Editor
            language={language}
            value={draft}
            onChange={(v) => setDraft(v ?? '')}
            onMount={onEditorMount}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 4,
            }}
          />
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onSave(draft);
              onClose();
            }}
          >
            {confirmIcon} {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
