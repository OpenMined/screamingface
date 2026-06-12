import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { usePrivateData } from '@/hooks/use-private-data';
import { PrivateDataList } from '@/components/private-data/PrivateDataList';
import { PrivateDataDetail } from '@/components/private-data/PrivateDataDetail';
import { AddPrivateDataDialog } from '@/components/private-data/AddPrivateDataDialog';

export function PrivateDataView() {
  const { items, ready, create, update, remove, getContent } = usePrivateData();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const selected = items.find((i) => i.uuid === selectedId) ?? null;

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-[1.6875rem]">Private Data</h1>
          <p className="text-sm text-muted-foreground">
            Editable markdown entities. Reference any entry in url4 as{' '}
            <code>/private/&lt;uuid7&gt;</code>.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} disabled={!ready}>
          <Plus className="h-4 w-4" /> New entry
        </Button>
      </div>

      <ResizablePanelGroup
        direction="horizontal"
        autoSaveId="private-data-split"
        className="flex-1"
      >
        <ResizablePanel id="private-data-list" defaultSize={40}>
          <PrivateDataList items={items} selectedId={selectedId} onSelect={setSelectedId} />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="private-data-detail" defaultSize={60}>
          {selected ? (
            <PrivateDataDetail
              item={selected}
              getContent={getContent}
              onSaveLabel={(uuid, label) => void update(uuid, { label: label || null })}
              onSaveContent={(uuid, content) => void update(uuid, { content })}
              onDelete={(uuid) => {
                void remove(uuid);
                setSelectedId(null);
              }}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Select an entry, or create one.
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>

      {creating && (
        <AddPrivateDataDialog
          onCancel={() => setCreating(false)}
          onCreate={async (label) => {
            const uuid = await create(label);
            setCreating(false);
            if (uuid) setSelectedId(uuid);
          }}
        />
      )}
    </div>
  );
}
