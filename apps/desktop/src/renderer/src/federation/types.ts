import type { ComponentType } from 'react';

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  remoteEntryUrl: string;
  exposedModule: string;
  description?: string;
  iconUrl?: string;
  active: boolean;
}

export interface PluginHostProps {
  serverUrl: string;
  config: Record<string, unknown>;
  onConfigChange: (patch: Partial<Record<string, unknown>>) => void;
}

export type PluginComponent = ComponentType<PluginHostProps>;

export interface PluginModule {
  default: PluginComponent;
}
