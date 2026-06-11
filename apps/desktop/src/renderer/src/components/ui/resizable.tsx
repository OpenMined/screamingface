import { GripVertical } from 'lucide-react';
import type { ComponentProps } from 'react';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';

import { cn } from '@/lib/utils';

function ResizablePanelGroup({ className, ...props }: ComponentProps<typeof PanelGroup>) {
  return (
    <PanelGroup
      data-slot="resizable-panel-group"
      className={cn('flex h-full w-full data-[panel-group-direction=vertical]:flex-col', className)}
      {...props}
    />
  );
}

function ResizablePanel({ className, ...props }: ComponentProps<typeof Panel>) {
  return (
    <Panel data-slot="resizable-panel" className={cn('min-h-0 min-w-0', className)} {...props} />
  );
}

function ResizableHandle({
  withHandle,
  className,
  ...props
}: ComponentProps<typeof PanelResizeHandle> & { withHandle?: boolean }) {
  return (
    <PanelResizeHandle
      data-slot="resizable-handle"
      className={cn(
        'relative flex w-px items-center justify-center bg-border outline-none transition-colors',
        'focus-visible:ring-3 focus-visible:ring-ring/50',
        'after:absolute after:inset-y-0 after:left-1/2 after:w-2 after:-translate-x-1/2',
        'hover:bg-ring data-[resize-handle-state=drag]:bg-ring',
        'data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full',
        'data-[panel-group-direction=vertical]:after:inset-x-0 data-[panel-group-direction=vertical]:after:h-2 data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:translate-x-0 data-[panel-group-direction=vertical]:after:-translate-y-1/2',
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className="z-10 flex h-5 w-3 items-center justify-center rounded-none border border-border bg-border">
          <GripVertical className="size-2.5 text-muted-foreground" />
        </div>
      )}
    </PanelResizeHandle>
  );
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
