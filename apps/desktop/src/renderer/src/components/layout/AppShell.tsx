import type { ReactNode } from 'react';
import { Sidebar, type View } from './Sidebar';
import { StatusBar } from './StatusBar';
import { Toaster } from '../ui/toaster';
import type { ServerStatus, PluginManifest } from '../../../../preload/types';

interface AppShellProps {
  currentView: View;
  onNavigate: (view: View) => void;
  serverStatus: ServerStatus;
  serverPort?: number;
  plugins: PluginManifest[];
  onAigwLoginRequest?: () => void;
  children: ReactNode;
}

export function AppShell({
  currentView,
  onNavigate,
  serverStatus,
  serverPort,
  plugins,
  onAigwLoginRequest,
  children,
}: AppShellProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          currentView={currentView}
          onNavigate={onNavigate}
          plugins={plugins}
          onAigwLoginRequest={onAigwLoginRequest}
        />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
      <StatusBar serverStatus={serverStatus} serverPort={serverPort} />
      <Toaster />
    </div>
  );
}
