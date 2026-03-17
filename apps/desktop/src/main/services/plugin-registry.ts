import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';
import { app } from 'electron';
import { EventEmitter } from 'events';
import { net } from 'electron';

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

class PluginRegistryService extends EventEmitter {
  private pluginsPath: string;

  constructor() {
    super();
    // During dev, app.getPath may not be ready yet — lazy init
    this.pluginsPath = '';
  }

  private getPath(): string {
    if (!this.pluginsPath) {
      try {
        this.pluginsPath = join(app.getPath('userData'), 'plugins.json');
      } catch {
        this.pluginsPath = join(process.cwd(), 'plugins.json');
      }
    }
    return this.pluginsPath;
  }

  private readStore(): PluginManifest[] {
    const p = this.getPath();
    if (!existsSync(p)) return [];
    try {
      return JSON.parse(readFileSync(p, 'utf-8'));
    } catch {
      return [];
    }
  }

  private writeStore(plugins: PluginManifest[]): void {
    writeFileSync(this.getPath(), JSON.stringify(plugins, null, 2), 'utf-8');
    this.emit('changed');
  }

  list(): PluginManifest[] {
    return this.readStore();
  }

  async install(remoteEntryUrl: string): Promise<PluginManifest> {
    // Fetch and validate the remoteEntry.json
    const manifest = await this.fetchRemoteEntry(remoteEntryUrl);
    const plugins = this.readStore();

    const existing = plugins.findIndex((p) => p.id === manifest.id);
    if (existing >= 0) {
      plugins[existing] = { ...manifest, active: true };
    } else {
      plugins.push({ ...manifest, active: true });
    }

    this.writeStore(plugins);
    return manifest;
  }

  uninstall(id: string): void {
    const plugins = this.readStore().filter((p) => p.id !== id);
    this.writeStore(plugins);
  }

  activate(id: string): void {
    const plugins = this.readStore();
    const plugin = plugins.find((p) => p.id === id);
    if (plugin) {
      plugin.active = true;
      this.writeStore(plugins);
    }
  }

  deactivate(id: string): void {
    const plugins = this.readStore();
    const plugin = plugins.find((p) => p.id === id);
    if (plugin) {
      plugin.active = false;
      this.writeStore(plugins);
    }
  }

  getCatalog(): PluginManifest[] {
    // Placeholder — could fetch from a remote catalog URL later
    return [];
  }

  private async fetchRemoteEntry(url: string): Promise<PluginManifest> {
    const response = await net.fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch remote entry: ${response.status}`);
    }

    const data = await response.json();

    // Validate minimum required fields
    if (!data.id || !data.name || !data.version || !data.exposedModule) {
      throw new Error('Invalid remote entry: missing required fields (id, name, version, exposedModule)');
    }

    return {
      id: data.id,
      name: data.name,
      version: data.version,
      remoteEntryUrl: url,
      exposedModule: data.exposedModule,
      description: data.description || '',
      iconUrl: data.iconUrl || '',
      active: true,
    };
  }
}

export const pluginRegistry = new PluginRegistryService();
