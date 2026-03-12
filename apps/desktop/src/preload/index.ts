import { contextBridge, ipcRenderer } from 'electron';
import type { ElectronAPI } from './types';

function onEvent(channel: string, callback: (...args: unknown[]) => void): () => void {
  const handler = (_event: Electron.IpcRendererEvent, ...args: unknown[]): void => {
    callback(...args);
  };
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

const api: ElectronAPI = {
  popup: {
    open: (url, title?) => ipcRenderer.invoke('popup:open', url, title),
    close: () => ipcRenderer.invoke('popup:close'),
  },
  server: {
    start: () => ipcRenderer.invoke('server:start'),
    stop: () => ipcRenderer.invoke('server:stop'),
    restart: () => ipcRenderer.invoke('server:restart'),
    getStatus: () => ipcRenderer.invoke('server:getStatus'),
    onStatusChanged: (cb) => onEvent('server:statusChanged', cb),
    onLog: (cb) => onEvent('server:log', cb),
  },
  venv: {
    detect: () => ipcRenderer.invoke('venv:detect'),
    create: () => ipcRenderer.invoke('venv:create'),
    sync: (extra?) => ipcRenderer.invoke('venv:sync', extra),
    listPackages: () => ipcRenderer.invoke('venv:listPackages'),
    onStatusChanged: (cb) => onEvent('venv:statusChanged', cb),
    onProgress: (cb) => onEvent('venv:progress', cb),
  },
  plugins: {
    list: () => ipcRenderer.invoke('plugins:list'),
    install: (url) => ipcRenderer.invoke('plugins:install', url),
    uninstall: (id) => ipcRenderer.invoke('plugins:uninstall', id),
    activate: (id) => ipcRenderer.invoke('plugins:activate', id),
    deactivate: (id) => ipcRenderer.invoke('plugins:deactivate', id),
    getCatalog: () => ipcRenderer.invoke('plugins:getCatalog'),
    discover: () => ipcRenderer.invoke('plugins:discover'),
    onChanged: (cb) => onEvent('plugins:changed', cb),
  },
  config: {
    read: () => ipcRenderer.invoke('config:read'),
    write: (config) => ipcRenderer.invoke('config:write', config),
    onChanged: (cb) => onEvent('config:changed', cb),
  },
};

contextBridge.exposeInMainWorld('electronAPI', api);
