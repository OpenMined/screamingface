import { contextBridge, ipcRenderer } from 'electron';
import type { ElectronAPI } from './types';

function onEvent<T extends unknown[]>(channel: string, callback: (...args: T) => void): () => void {
  const handler = (_event: Electron.IpcRendererEvent, ...args: unknown[]): void => {
    callback(...(args as T));
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
    fetch: (url, init?) => ipcRenderer.invoke('server:fetch', url, init),
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
  publish: {
    getContext: () => ipcRenderer.invoke('publish:getContext'),
    openExternal: (url) => ipcRenderer.invoke('publish:openExternal', url),
  },
  backends: {
    getStatus: () => ipcRenderer.invoke('backends:getStatus'),
    getPollingError: () => ipcRenderer.invoke('backends:getPollingError'),
    refresh: () => ipcRenderer.invoke('backends:refresh'),
    authenticate: (backend) => ipcRenderer.invoke('backends:authenticate', backend),
    loginGateway: (username, password) =>
      ipcRenderer.invoke('backends:loginGateway', username, password),
    logoutGateway: () => ipcRenderer.invoke('backends:logoutGateway'),
    authenticateOAuth: (backend, profileName?) =>
      ipcRenderer.invoke('backends:authenticateOAuth', backend, profileName),
    authenticateOAuthConnection: (backend, label?) =>
      ipcRenderer.invoke('backends:authenticateOAuthConnection', backend, label),
    getPendingAuthState: (backend, profileName?) =>
      ipcRenderer.invoke('backends:getPendingAuthState', backend, profileName),
    getPendingConnectionAuthState: (backend, connectionId?) =>
      ipcRenderer.invoke('backends:getPendingConnectionAuthState', backend, connectionId),
    exchangeOAuthCode: (backend, code, profileName?) =>
      ipcRenderer.invoke('backends:exchangeOAuthCode', backend, code, profileName),
    exchangeOAuthConnectionCode: (backend, connectionId, code) =>
      ipcRenderer.invoke('backends:exchangeOAuthConnectionCode', backend, connectionId, code),
    listProfiles: (backend) => ipcRenderer.invoke('backends:listProfiles', backend),
    deleteProfile: (backend, profileName) =>
      ipcRenderer.invoke('backends:deleteProfile', backend, profileName),
    listConnections: (backend) => ipcRenderer.invoke('backends:listConnections', backend),
    deleteConnection: (backend, connectionId) =>
      ipcRenderer.invoke('backends:deleteConnection', backend, connectionId),
    refreshConnection: (backend, connectionId) =>
      ipcRenderer.invoke('backends:refreshConnection', backend, connectionId),
    onStatusChanged: (cb) => onEvent('backends:statusChanged', cb),
    onPollingError: (cb) => onEvent('backends:pollingError', cb),
    onAlert: (cb) => onEvent('backends:alert', cb),
  },
  aigwSession: {
    getState: () => ipcRenderer.invoke('aigw-session:get-state'),
    getJwt: () => ipcRenderer.invoke('aigw-session:get-jwt'),
    isLoggedIn: () => ipcRenderer.invoke('aigw-session:is-logged-in'),
    login: (username, password, options?) =>
      ipcRenderer.invoke('aigw-session:login', username, password, options),
    logout: () => ipcRenderer.invoke('aigw-session:logout'),
    setGatewayUrl: (gatewayUrl) => ipcRenderer.invoke('aigw-session:set-gateway-url', gatewayUrl),
    onChanged: (cb) => onEvent('aigw-session:changed', cb),
    onExpired: (cb) => onEvent('aigw-session:expired', cb),
  },
  session: {
    pickDir: () => ipcRenderer.invoke('session:pickDir'),
    create: (type, workingDir, pluginConfig?) =>
      ipcRenderer.invoke('session:create', type, workingDir, pluginConfig),
    list: () => ipcRenderer.invoke('session:list'),
    terminate: (id) => ipcRenderer.invoke('session:terminate', id),
    terminateAll: () => ipcRenderer.invoke('session:terminateAll'),
    remove: (id) => ipcRenderer.invoke('session:remove', id),
    update: (id, workingDir, pluginConfig?) =>
      ipcRenderer.invoke('session:update', id, workingDir, pluginConfig),
    restart: (id) => ipcRenderer.invoke('session:restart', id),
    onSessionsChanged: (cb) => onEvent('session:sessionsChanged', cb),
    onLog: (cb) => {
      const handler = (_event: Electron.IpcRendererEvent, id: string, line: string): void => {
        cb(id, line);
      };
      ipcRenderer.on('session:log', handler);
      return () => ipcRenderer.removeListener('session:log', handler);
    },
  },
};

contextBridge.exposeInMainWorld('electronAPI', api);
