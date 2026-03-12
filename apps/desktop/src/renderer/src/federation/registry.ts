import type { PluginManifest } from './types';

const STORAGE_KEY = 'sf-plugin-registry';

export function loadPluginManifests(): PluginManifest[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function savePluginManifests(manifests: PluginManifest[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(manifests));
}
