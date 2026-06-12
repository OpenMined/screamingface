// apps/desktop/src/renderer/src/components/eval/AddEvalRunDialog.tsx
//
// "+ Add url4" popup for Eval Studio (SF-248): name + url4 expression (edited in
// the Monaco url4 field). On create it hands a RunPayload to the parent (same
// path as "Run Locally"); the run itself is the source of truth for url4 errors
// — we intentionally don't gate on /ensemble/highlight, which false-errors on
// the ensemble fan-out shape that /ensemble runs fine (SF-249).
import { useState } from 'react';
import { X, Play, ListChecks } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Url4Field } from '@/components/Url4Field';
import { Url4SpecPickerDialog } from './Url4SpecPickerDialog';
import { useServerStatus } from '@/hooks/use-server-status';
import type { RunPayload } from '@/components/run/types';

interface Props {
  onClose: () => void;
  onCreate: (payload: RunPayload) => void;
}

export function AddEvalRunDialog({ onClose, onCreate }: Props) {
  const { info } = useServerStatus();
  const serverUrl = info
    ? `${info.scheme}://${info.host === '0.0.0.0' ? 'localhost' : info.host}:${info.port}`
    : '';

  const [name, setName] = useState('');
  const [expression, setExpression] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);

  const canCreate = name.trim().length > 0 && expression.trim().length > 0;

  const handleCreate = (): void => {
    if (!canCreate) return;
    onCreate({ spec: name.trim(), expression: expression.trim() });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-none border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">New eval run</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">
              Name <span className="text-destructive">*</span>
            </span>
            <input
              autoFocus
              className="w-full rounded-none border border-input bg-background px-3 py-2 text-sm"
              placeholder="e.g. my-ensemble"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">
                URL4 expression <span className="text-destructive">*</span>
              </span>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                <ListChecks className="h-3.5 w-3.5" /> Choose from saved specs
              </button>
            </div>
            <div className="rounded-none border border-border">
              <Url4Field value={expression} onChange={setExpression} serverUrl={serverUrl} />
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={!canCreate}>
            <Play className="h-4 w-4" /> Create &amp; run
          </Button>
        </div>
      </div>

      {pickerOpen && (
        <Url4SpecPickerDialog
          onClose={() => setPickerOpen(false)}
          onPick={(spec) => {
            setName(spec.name);
            setExpression(spec.expression);
            setPickerOpen(false);
          }}
        />
      )}
    </div>
  );
}
