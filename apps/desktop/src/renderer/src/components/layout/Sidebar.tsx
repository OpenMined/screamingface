import {
  FlaskConical,
  LayoutDashboard,
  Settings,
  Puzzle,
  Terminal,
  Workflow,
  FileCode2,
  FileText,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { BrandMark } from '@/components/layout/BrandMark';
import type { BackendPollingError, PluginManifest } from '../../../../preload/types';
import { GatewayStatusPanel } from '@/components/server/GatewayStatusPanel';
import { isBackendStatusV2, useBackendStatus } from '@/hooks/use-backend-status';

export type View =
  | 'dashboard'
  | 'sessions'
  | 'eval-studio'
  | 'url4-studio'
  | 'code-studio'
  | 'private-data'
  | 'settings'
  | `plugin:${string}`;

interface NavItem {
  id: View;
  label: string;
  icon: LucideIcon;
}

const coreItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'sessions', label: 'Sessions', icon: Terminal },
  { id: 'eval-studio', label: 'Eval Studio', icon: FlaskConical },
  { id: 'url4-studio', label: 'URL4 Studio', icon: Workflow },
  { id: 'code-studio', label: 'Code Studio', icon: FileCode2 },
  { id: 'private-data', label: 'Private Data', icon: FileText },
];

// Settings is pinned to the bottom of the sidebar, separate from the main nav.
const settingsItem: NavItem = { id: 'settings', label: 'Settings', icon: Settings };

interface SidebarProps {
  currentView: View;
  onNavigate: (view: View) => void;
  plugins: PluginManifest[];
  onAigwLoginRequest?: () => void;
}

export function Sidebar({ currentView, onNavigate, plugins, onAigwLoginRequest }: SidebarProps) {
  const { statuses, pollingError, refresh } = useBackendStatus();
  const gatewayStatus = isBackendStatusV2(statuses) ? statuses : null;
  const showPollingError = pollingError !== null && pollingError.consecutiveFailures >= 2;

  return (
    <aside className="flex w-52 flex-col border-r border-sidebar-border bg-sidebar">
      {/* App title — draggable region for macOS title bar */}
      <div
        className="flex items-center gap-2 px-4 pb-3 pt-8"
        style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
      >
        <BrandMark />
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2">
        {coreItems.map((item) => {
          const active = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={cn(
                'flex items-center gap-2.5 rounded-none px-3 py-1.5 text-sm transition-colors',
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
                    'flex items-center gap-2.5 rounded-none px-3 py-1.5 text-sm transition-colors',
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
      {showPollingError && (
        <div
          role="status"
          aria-label="Backend polling error"
          className="mx-2 mb-2 rounded-none border border-destructive/30 bg-destructive/10 px-2.5 py-2 text-xs text-destructive"
        >
          <div className="font-medium">SF status unavailable</div>
          <div className="mt-0.5 text-destructive/80">{formatPollingError(pollingError)}</div>
        </div>
      )}
      {gatewayStatus?.gateway.mode === 'external' && (
        <div className="px-2 pb-3">
          <GatewayStatusPanel
            status={gatewayStatus}
            compact
            onLoginRequest={onAigwLoginRequest}
            onChanged={() => {
              void refresh();
            }}
          />
        </div>
      )}

      {/* Settings pinned to the bottom */}
      <nav className="border-t border-sidebar-border px-2 py-2">
        <button
          onClick={() => onNavigate(settingsItem.id)}
          className={cn(
            'flex w-full items-center gap-2.5 rounded-none px-3 py-1.5 text-sm transition-colors',
            currentView === settingsItem.id
              ? 'bg-sidebar-accent text-sidebar-primary'
              : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
          )}
        >
          <settingsItem.icon className="h-4 w-4" />
          {settingsItem.label}
        </button>
      </nav>
    </aside>
  );
}

function formatPollingError(error: BackendPollingError): string {
  const prefix = error.status ? `HTTP ${error.status}` : 'Network error';
  const detail = error.code ?? error.message;
  return detail ? `${prefix}: ${detail}` : prefix;
}
