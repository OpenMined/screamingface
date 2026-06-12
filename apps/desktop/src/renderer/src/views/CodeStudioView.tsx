import { useRef, useState } from 'react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Plus } from 'lucide-react';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Button } from '@/components/ui/button';
import { CodeScriptsList } from '@/components/code/CodeScriptsList';
import { CodeScriptDetail } from '@/components/code/CodeScriptDetail';
import { AddCodeScriptDialog } from '@/components/code/AddCodeScriptDialog';
import { useCodeScripts } from '@/hooks/use-code-scripts';

export function CodeStudioView() {
  const { scripts, loading, error, createScript, renameScript, deleteScript, saveSource } =
    useCodeScripts();
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const selected = scripts.find((s) => s.name === selectedName) ?? null;

  const handleCreate = async (name: string): Promise<void> => {
    if (await createScript(name)) setSelectedName(name);
  };
  const handleRename = async (oldName: string, newName: string): Promise<void> => {
    if (await renameScript(oldName, newName)) setSelectedName(newName);
  };
  const handleDelete = async (name: string): Promise<void> => {
    if (await deleteScript(name)) {
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
          <h1 className="text-[1.6875rem] font-semibold text-foreground">Code Studio</h1>
          <p className="text-xs text-muted-foreground">
            Python scripts referenced by URL4 expressions (/data/code/&lt;name&gt;.py)
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" className="mr-1" onClick={() => setCreating(true)}>
            <Plus className="h-3.5 w-3.5" /> New script
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={leftCollapsed ? 'Show scripts list' : 'Hide scripts list'}
            aria-pressed={leftCollapsed}
            onClick={toggleLeft}
          >
            {leftCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={rightCollapsed ? 'Show script details' : 'Hide script details'}
            aria-pressed={rightCollapsed}
            onClick={toggleRight}
          >
            {rightCollapsed ? <PanelRightOpen /> : <PanelRightClose />}
          </Button>
        </div>
      </div>

      <ResizablePanelGroup
        direction="horizontal"
        autoSaveId="code-studio-split"
        className="min-h-0 flex-1"
      >
        <ResizablePanel
          ref={leftPanelRef}
          id="code-scripts-list"
          order={1}
          collapsible
          collapsedSize={0}
          minSize={20}
          defaultSize={50}
          onCollapse={() => setLeftCollapsed(true)}
          onExpand={() => setLeftCollapsed(false)}
          className="overflow-auto"
        >
          <CodeScriptsList
            scripts={scripts}
            selectedName={selectedName}
            onSelect={setSelectedName}
            loading={loading}
            error={error}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel
          ref={rightPanelRef}
          id="code-script-detail"
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
            <CodeScriptDetail
              script={selected}
              onRename={(o, n) => void handleRename(o, n)}
              onDelete={(n) => void handleDelete(n)}
              onSaveSource={(n, s) => void saveSource(n, s)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Select a script to see details
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>

      {creating && (
        <AddCodeScriptDialog
          existingNames={scripts.map((s) => s.name)}
          onClose={() => setCreating(false)}
          onCreate={(name) => void handleCreate(name)}
        />
      )}
    </div>
  );
}
