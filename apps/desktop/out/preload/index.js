"use strict";
const electron = require("electron");
function onEvent(channel, callback) {
  const handler = (_event, ...args) => {
    callback(...args);
  };
  electron.ipcRenderer.on(channel, handler);
  return () => electron.ipcRenderer.removeListener(channel, handler);
}
const api = {
  popup: {
    open: (url, title) => electron.ipcRenderer.invoke("popup:open", url, title),
    close: () => electron.ipcRenderer.invoke("popup:close")
  },
  server: {
    start: () => electron.ipcRenderer.invoke("server:start"),
    stop: () => electron.ipcRenderer.invoke("server:stop"),
    restart: () => electron.ipcRenderer.invoke("server:restart"),
    getStatus: () => electron.ipcRenderer.invoke("server:getStatus"),
    onStatusChanged: (cb) => onEvent("server:statusChanged", cb),
    onLog: (cb) => onEvent("server:log", cb),
    fetch: (url, init) => electron.ipcRenderer.invoke("server:fetch", url, init)
  },
  venv: {
    detect: () => electron.ipcRenderer.invoke("venv:detect"),
    create: () => electron.ipcRenderer.invoke("venv:create"),
    sync: (extra) => electron.ipcRenderer.invoke("venv:sync", extra),
    listPackages: () => electron.ipcRenderer.invoke("venv:listPackages"),
    onStatusChanged: (cb) => onEvent("venv:statusChanged", cb),
    onProgress: (cb) => onEvent("venv:progress", cb)
  },
  plugins: {
    list: () => electron.ipcRenderer.invoke("plugins:list"),
    install: (url) => electron.ipcRenderer.invoke("plugins:install", url),
    uninstall: (id) => electron.ipcRenderer.invoke("plugins:uninstall", id),
    activate: (id) => electron.ipcRenderer.invoke("plugins:activate", id),
    deactivate: (id) => electron.ipcRenderer.invoke("plugins:deactivate", id),
    getCatalog: () => electron.ipcRenderer.invoke("plugins:getCatalog"),
    discover: () => electron.ipcRenderer.invoke("plugins:discover"),
    onChanged: (cb) => onEvent("plugins:changed", cb)
  },
  config: {
    read: () => electron.ipcRenderer.invoke("config:read"),
    write: (config) => electron.ipcRenderer.invoke("config:write", config),
    onChanged: (cb) => onEvent("config:changed", cb)
  },
  publish: {
    getContext: () => electron.ipcRenderer.invoke("publish:getContext"),
    submitScore: (request) => electron.ipcRenderer.invoke("publish:submitScore", request),
    getLogs: () => electron.ipcRenderer.invoke("publish:getLogs"),
    onLog: (cb) => onEvent("publish:log", cb),
    openExternal: (url) => electron.ipcRenderer.invoke("publish:openExternal", url),
    listBenchmarks: () => electron.ipcRenderer.invoke("publish:listBenchmarks")
  },
  backends: {
    getStatus: () => electron.ipcRenderer.invoke("backends:getStatus"),
    getPollingError: () => electron.ipcRenderer.invoke("backends:getPollingError"),
    refresh: () => electron.ipcRenderer.invoke("backends:refresh"),
    authenticate: (backend) => electron.ipcRenderer.invoke("backends:authenticate", backend),
    loginGateway: (username, password) => electron.ipcRenderer.invoke("backends:loginGateway", username, password),
    logoutGateway: () => electron.ipcRenderer.invoke("backends:logoutGateway"),
    authenticateOAuth: (backend, profileName) => electron.ipcRenderer.invoke("backends:authenticateOAuth", backend, profileName),
    authenticateOAuthConnection: (backend, label) => electron.ipcRenderer.invoke("backends:authenticateOAuthConnection", backend, label),
    getPendingAuthState: (backend, profileName) => electron.ipcRenderer.invoke("backends:getPendingAuthState", backend, profileName),
    getPendingConnectionAuthState: (backend, connectionId) => electron.ipcRenderer.invoke("backends:getPendingConnectionAuthState", backend, connectionId),
    exchangeOAuthCode: (backend, code, profileName) => electron.ipcRenderer.invoke("backends:exchangeOAuthCode", backend, code, profileName),
    exchangeOAuthConnectionCode: (backend, connectionId, code) => electron.ipcRenderer.invoke("backends:exchangeOAuthConnectionCode", backend, connectionId, code),
    listProfiles: (backend) => electron.ipcRenderer.invoke("backends:listProfiles", backend),
    deleteProfile: (backend, profileName) => electron.ipcRenderer.invoke("backends:deleteProfile", backend, profileName),
    setProfileApiKey: (backend, profileName, apiKey) => electron.ipcRenderer.invoke("backends:setProfileApiKey", backend, profileName, apiKey),
    listConnections: (backend) => electron.ipcRenderer.invoke("backends:listConnections", backend),
    createConnectionApiKey: (backend, label, apiKey) => electron.ipcRenderer.invoke("backends:createConnectionApiKey", backend, label, apiKey),
    setConnectionApiKey: (backend, connectionId, apiKey) => electron.ipcRenderer.invoke("backends:setConnectionApiKey", backend, connectionId, apiKey),
    deleteConnection: (backend, connectionId) => electron.ipcRenderer.invoke("backends:deleteConnection", backend, connectionId),
    refreshConnection: (backend, connectionId) => electron.ipcRenderer.invoke("backends:refreshConnection", backend, connectionId),
    onStatusChanged: (cb) => onEvent("backends:statusChanged", cb),
    onPollingError: (cb) => onEvent("backends:pollingError", cb),
    onAlert: (cb) => onEvent("backends:alert", cb)
  },
  aigwSession: {
    getState: () => electron.ipcRenderer.invoke("aigw-session:get-state"),
    getJwt: () => electron.ipcRenderer.invoke("aigw-session:get-jwt"),
    isLoggedIn: () => electron.ipcRenderer.invoke("aigw-session:is-logged-in"),
    login: (username, password, options) => electron.ipcRenderer.invoke("aigw-session:login", username, password, options),
    logout: () => electron.ipcRenderer.invoke("aigw-session:logout"),
    setGatewayUrl: (gatewayUrl) => electron.ipcRenderer.invoke("aigw-session:set-gateway-url", gatewayUrl),
    onChanged: (cb) => onEvent("aigw-session:changed", cb),
    onExpired: (cb) => onEvent("aigw-session:expired", cb)
  },
  session: {
    pickDir: () => electron.ipcRenderer.invoke("session:pickDir"),
    create: (type, workingDir, pluginConfig) => electron.ipcRenderer.invoke("session:create", type, workingDir, pluginConfig),
    list: () => electron.ipcRenderer.invoke("session:list"),
    terminate: (id) => electron.ipcRenderer.invoke("session:terminate", id),
    terminateAll: () => electron.ipcRenderer.invoke("session:terminateAll"),
    remove: (id) => electron.ipcRenderer.invoke("session:remove", id),
    update: (id, workingDir, pluginConfig) => electron.ipcRenderer.invoke("session:update", id, workingDir, pluginConfig),
    restart: (id) => electron.ipcRenderer.invoke("session:restart", id),
    onSessionsChanged: (cb) => onEvent("session:sessionsChanged", cb),
    onLog: (cb) => {
      const handler = (_event, id, line) => {
        cb(id, line);
      };
      electron.ipcRenderer.on("session:log", handler);
      return () => electron.ipcRenderer.removeListener("session:log", handler);
    }
  }
};
electron.contextBridge.exposeInMainWorld("electronAPI", api);
