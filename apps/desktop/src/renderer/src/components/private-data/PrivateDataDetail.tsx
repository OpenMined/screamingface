import { lazy, Suspense, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CopyButton } from '@/components/CopyButton';
import type { PrivateItem } from '@/lib/private-data-api';

// CodeEditorPopup is a default export — lazy() resolves it directly.
const CodeEditorPopup = lazy(() => import('@/components/CodeEditorPopup'));

interface Props {
  item: PrivateItem;
  getContent: (uuid: string) => Promise<string>;
  onSaveLabel: (uuid: string, label: string) => void;
  onSaveContent: (uuid: string, content: string) => void;
  onDelete: (uuid: string) => void;
}

export function PrivateDataDetail({
  item,
  getContent,
  onSaveLabel,
  onSaveContent,
  onDelete,
}: Props) {
  const [label, setLabel] = useState(item.label ?? '');
  const [content, setContent] = useState('');
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setLabel(item.label ?? '');
    void getContent(item.uuid).then(setContent);
  }, [item.uuid, item.label, getContent]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <Input
          value={label}
          placeholder="Label (optional)"
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => label !== (item.label ?? '') && onSaveLabel(item.uuid, label)}
          className="max-w-xs"
        />
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            Edit content
          </Button>
          <Button variant="destructive" size="sm" onClick={() => setConfirmDelete(true)}>
            Delete
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2 border-b border-border px-4 py-1.5 font-mono text-[11px] text-muted-foreground">
        <span>uuid7</span>
        <span className="text-foreground">{item.uuid}</span>
        <CopyButton value={item.uuid} />
        <span className="ml-1">— reference in url4 as</span>
        <span className="text-foreground">/private/{item.uuid}</span>
      </div>

      <pre className="flex-1 overflow-auto whitespace-pre-wrap p-4 font-mono text-sm">
        {content || '(empty — click “Edit content”)'}
      </pre>

      {editing && (
        <Suspense fallback={null}>
          <CodeEditorPopup
            title={`Edit ${label || item.uuid.slice(0, 8)}`}
            language="markdown"
            value={content}
            onSave={(v) => {
              setContent(v);
              onSaveContent(item.uuid, v);
              setEditing(false);
            }}
            onClose={() => setEditing(false)}
          />
        </Suspense>
      )}

      {confirmDelete && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/80">
          <div className="border border-border bg-card p-4 text-sm">
            <p className="mb-3">Delete this entry? This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  setConfirmDelete(false);
                  onDelete(item.uuid);
                }}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
