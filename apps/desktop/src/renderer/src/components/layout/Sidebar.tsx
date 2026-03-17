import {
  LayoutDashboard,
  Settings,
  Puzzle,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PluginManifest } from '../../../../preload/types';

export type View = 'dashboard' | 'settings' | `plugin:${string}`;

interface NavItem {
  id: View;
  label: string;
  icon: LucideIcon;
}

const coreItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'settings', label: 'Settings', icon: Settings },
];

interface SidebarProps {
  currentView: View;
  onNavigate: (view: View) => void;
  plugins: PluginManifest[];
}

export function Sidebar({ currentView, onNavigate, plugins }: SidebarProps) {
  return (
    <aside className="flex w-52 flex-col border-r border-sidebar-border bg-sidebar">
      {/* App title — draggable region for macOS title bar */}
      <div className="flex items-center gap-2 px-4 pb-3 pt-8" style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}>
        <span className="text-lg">&#x1F631;</span>
        <span className="font-heading text-sm font-semibold text-sidebar-foreground">
          screamingface
        </span>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2">
        {coreItems.map((item) => {
          const active = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={cn(
                'flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm transition-colors',
                active
                  ? 'bg-sidebar-accent text-sidebar-primary'
                  : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}

        {plugins.length > 0 && (
          <>
            <div className="mb-1 mt-4 px-3 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Plugins
            </div>
            {plugins.map((plugin) => {
              const viewId: View = `plugin:${plugin.id}`;
              const active = currentView === viewId;
              return (
                <button
                  key={plugin.id}
                  onClick={() => onNavigate(viewId)}
                  className={cn(
                    'flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm transition-colors',
                    active
                      ? 'bg-sidebar-accent text-sidebar-primary'
                      : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
                  )}
                >
                  <Puzzle className="h-4 w-4" />
                  {plugin.name}
                </button>
              );
            })}
          </>
        )}
      </nav>
    </aside>
  );
}
