import { Puzzle, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PluginManifest } from '../../../../preload/types';

interface PluginCardProps {
  plugin: PluginManifest;
  onActivate: (id: string) => void;
  onDeactivate: (id: string) => void;
  onUninstall: (id: string) => void;
}

export function PluginCard({ plugin, onActivate, onDeactivate, onUninstall }: PluginCardProps) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-secondary">
            <Puzzle className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground">{plugin.name}</h3>
            <p className="text-xs text-muted-foreground">v{plugin.version}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => (plugin.active ? onDeactivate(plugin.id) : onActivate(plugin.id))}
            className={cn(
              'rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors',
              plugin.active
                ? 'bg-chart-3/15 text-chart-3 hover:bg-chart-3/25'
                : 'bg-secondary text-muted-foreground hover:bg-secondary/80',
            )}
          >
            {plugin.active ? 'Active' : 'Inactive'}
          </button>
          <button
            onClick={() => onUninstall(plugin.id)}
            className="text-muted-foreground transition-colors hover:text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      {plugin.description && (
        <p className="mt-2 text-xs text-muted-foreground">{plugin.description}</p>
      )}
    </div>
  );
}
