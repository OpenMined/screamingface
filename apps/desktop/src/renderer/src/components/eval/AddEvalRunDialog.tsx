// apps/desktop/src/renderer/src/components/eval/AddEvalRunDialog.tsx
//
// "+ Add url4" popup for Eval Studio (SF-248): name + url4 expression with live
// validation against the server's /ensemble/highlight endpoint (400 on parse
// error). On create, hands a RunPayload to the parent (same path as "Run
// Locally"). The url4 field is a textarea for now; SF-249 swaps in the Monaco
// url4 editor.
import { useEffect, useRef, useState } from 'react';
import { X, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Url4Viewer } from '@/components/Url4Viewer';
import { useServerStatus } from '@/hooks/use-server-status';
import type { RunPayload } from '@/components/run/types';

interface Props {
  onClose: () => void;
  onCreate: (payload: RunPayload) => void;
}

type Validity = 'empty' | 'validating' | 'valid' | 'invalid';

export function AddEvalRunDialog({ onClose, onCreate }: Props) {
  const { info } = useServerStatus();
  const serverUrl = info
    ? `${info.scheme}://${info.host === '0.0.0.0' ? 'localhost' : info.host}:${info.port}`
    : '';

  const [name, setName] = useState('');
  const [expression, setExpression] = useState('');
  const [validity, setValidity] = useState<Validity>('empty');
  const [validationError, setValidationError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Debounced validation via the existing /ensemble/highlight endpoint, which
  // returns 400 + a TatSu parse error for invalid url4.
  useEffect(() => {
    const expr = expression.trim();
    if (!expr) {
      setValidity('empty');
      setValidationError(null);
      return;
    }
    if (!serverUrl) return;
    setValidity('validating');
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await window.electronAPI.server.fetch(
          `${serverUrl}/ensemble/highlight?q=${encodeURIComponent(expr)}`,
        );
        if (res.ok) {
          setValidity('valid');
          setValidationError(null);
        } else {
          setValidity('invalid');
          setValidationError(res.body?.slice(0, 200) || `Invalid url4 (HTTP ${res.status})`);
        }
      } catch (e) {
        setValidity('invalid');
        setValidationError((e as Error).message);
      }
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [expression, serverUrl]);

  const canCreate = name.trim().length > 0 && validity === 'valid';

  const handleCreate = (): void => {
    if (!canCreate) return;
    onCreate({ spec: name.trim(), expression: expression.trim() });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-[10px] border border-border bg-card shadow-2xl">
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
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
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
              {validity === 'validating' && (
                <span className="text-[11px] text-muted-foreground">checking…</span>
              )}
              {validity === 'valid' && <span className="text-[11px] text-chart-3">valid ✓</span>}
              {validity === 'invalid' && (
                <span className="text-[11px] text-destructive">invalid</span>
              )}
            </div>
            <textarea
              aria-label="URL4 expression"
              spellCheck={false}
              className="min-h-[120px] w-full rounded-md border border-border bg-background p-3 font-mono text-xs"
              placeholder="(https://…)!$prompt"
              value={expression}
              onChange={(e) => setExpression(e.target.value)}
            />
            {validationError && (
              <p className="mt-1 text-[11px] text-destructive">{validationError}</p>
            )}
          </div>

          {expression.trim() && validity === 'valid' && (
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Preview</span>
              <div className="rounded-md border border-border p-3">
                <Url4Viewer expression={expression} serverUrl={serverUrl} mode="expanded" />
              </div>
            </div>
          )}
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
    </div>
  );
}
