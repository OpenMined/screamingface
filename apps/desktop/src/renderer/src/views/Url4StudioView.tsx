import { useRef, useState } from 'react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Plus } from 'lucide-react';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Button } from '@/components/ui/button';
import { Url4SpecsList } from '@/components/url4/Url4SpecsList';
import { Url4SpecDetail } from '@/components/url4/Url4SpecDetail';
import { AddUrl4SpecDialog } from '@/components/url4/AddUrl4SpecDialog';
import { useUrl4Specs } from '@/hooks/use-url4-specs';

export function Url4StudioView() {
  const { specs, loading, error, createSpec, renameSpec, deleteSpec, saveExpression } =
    useUrl4Specs();
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const selected = specs.find((s) => s.name === selectedName) ?? null;

  const handleCreate = async (name: string): Promise<void> => {
    if (await createSpec(name)) setSelectedName(name);
  };
  const handleRename = async (oldName: string, newName: string): Promise<void> => {
    if (await renameSpec(oldName, newName)) setSelectedName(newName);
  };
  const handleDelete = async (name: string): Promise<void> => {
    if (await deleteSpec(name)) {
      setSelectedName((current) => (current === name ? null : current));
    }
  };

  const toggleLeft = () => {
    const panel = leftPanelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) panel.expand();
    else panel.collapse();
  };
  const toggleRight = () => {
    const panel = rightPanelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) panel.expand();
    else panel.collapse();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-[1.6875rem] font-semibold text-foreground">URL4 Studio</h1>
          <p className="text-xs text-muted-foreground">
            Named URL4 expressions you can run in Eval Studio and share
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" className="mr-1" onClick={() => setCreating(true)}>
            <Plus className="h-3.5 w-3.5" /> New spec
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={leftCollapsed ? 'Show specs list' : 'Hide specs list'}
            aria-pressed={leftCollapsed}
            onClick={toggleLeft}
          >
            {leftCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={rightCollapsed ? 'Show spec details' : 'Hide spec details'}
            aria-pressed={rightCollapsed}
            onClick={toggleRight}
          >
            {rightCollapsed ? <PanelRightOpen /> : <PanelRightClose />}
          </Button>
        </div>
      </div>

      <ResizablePanelGroup
        direction="horizontal"
        autoSaveId="url4-studio-split"
        className="min-h-0 flex-1"
      >
        <ResizablePanel
          ref={leftPanelRef}
          id="url4-specs-list"
          order={1}
          collapsible
          collapsedSize={0}
          minSize={20}
          defaultSize={50}
          onCollapse={() => setLeftCollapsed(true)}
          onExpand={() => setLeftCollapsed(false)}
          className="overflow-auto"
        >
          <Url4SpecsList
            specs={specs}
            selectedName={selectedName}
            onSelect={setSelectedName}
            loading={loading}
            error={error}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel
          ref={rightPanelRef}
          id="url4-spec-detail"
          order={2}
          collapsible
          collapsedSize={0}
          minSize={20}
          defaultSize={50}
          onCollapse={() => setRightCollapsed(true)}
          onExpand={() => setRightCollapsed(false)}
          className="flex overflow-hidden"
        >
          {selected ? (
            <Url4SpecDetail
              spec={selected}
              onRename={(o, n) => void handleRename(o, n)}
              onDelete={(n) => void handleDelete(n)}
              onSaveExpression={(n, e) => void saveExpression(n, e)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Select a spec to see details
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>

      {creating && (
        <AddUrl4SpecDialog
          existingNames={specs.map((s) => s.name)}
          onClose={() => setCreating(false)}
          onCreate={(name) => void handleCreate(name)}
        />
      )}
    </div>
  );
}
