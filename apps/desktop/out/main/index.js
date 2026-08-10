"use strict";
Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
const electron = require("electron");
const path = require("path");
const utils = require("@electron-toolkit/utils");
const https = require("https");
const http = require("http");
const child_process = require("child_process");
const events = require("events");
const util = require("util");
const fs = require("fs");
const crypto = require("crypto");
const os = require("os");
const net = require("net");
const url = require("url");
const LEGACY_DIRECT_CODEX_BACKEND = "codex-backend-api";
const GATEWAY_CODEX_BACKEND = "aigw-codex-backend";
const DEFAULT_CODEX_MODEL = "codex/gpt-5.4-mini";
const DEFAULT_GATEWAY_URL$1 = "http://127.0.0.1:9105";
class GatewayUrlConflictError extends Error {
  constructor(urls) {
    super(
      `Multiple AIGateway backend gateway_url values found: ${urls.join(", ")}. Set plugin_config["aigw-base"].gateway_url to the intended URL before starting ScreamingFace.`
    );
    this.urls = urls;
    this.name = "GatewayUrlConflictError";
  }
}
function isRecord$2(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function migratePluginList(plugins) {
  const nextPlugins = [];
  for (const plugin of plugins) {
    if (plugin === LEGACY_DIRECT_CODEX_BACKEND) {
      if (!nextPlugins.includes(GATEWAY_CODEX_BACKEND)) {
        nextPlugins.push(GATEWAY_CODEX_BACKEND);
      }
      continue;
    }
    if (plugin === GATEWAY_CODEX_BACKEND && nextPlugins.includes(GATEWAY_CODEX_BACKEND)) {
      continue;
    }
    nextPlugins.push(plugin);
  }
  for (const required of ["aigw-runner", "aigw-base"]) {
    if (!nextPlugins.includes(required)) nextPlugins.push(required);
  }
  return nextPlugins;
}
function migrateCodexBackendConfig(value) {
  const migrated = isRecord$2(value) ? { ...value } : {};
  const model = migrated.default_model;
  if (typeof model !== "string" || !model.startsWith("codex/")) {
    migrated.default_model = DEFAULT_CODEX_MODEL;
  }
  if (typeof migrated.auth_profile !== "string") {
    migrated.auth_profile = "default";
  }
  return migrated;
}
function isGatewayBackendName(name) {
  return name.startsWith("aigw-") && name.endsWith("-backend");
}
function gatewayUrls(pluginConfig) {
  const urls = [];
  for (const [name, value] of Object.entries(pluginConfig)) {
    if (!isGatewayBackendName(name) || !isRecord$2(value)) continue;
    const raw = value.gateway_url;
    if (typeof raw !== "string" || !raw.trim()) continue;
    const normalized = raw.trim().replace(/\/+$/, "");
    if (!urls.includes(normalized)) urls.push(normalized);
  }
  return urls;
}
function migrateDesktopRuntimeConfig(config, userDataDir) {
  const plugins = Array.isArray(config.plugins) ? config.plugins.filter((plugin) => typeof plugin === "string") : [];
  const hadDirectCodexBackend = plugins.includes(LEGACY_DIRECT_CODEX_BACKEND);
  const nextPlugins = migratePluginList(plugins);
  const serverConfig = isRecord$2(config.server) ? { ...config.server } : {};
  serverConfig.host = "127.0.0.1";
  const pluginConfig = isRecord$2(config.plugin_config) ? { ...config.plugin_config } : {};
  const gatewayDir = path.join(userDataDir, "aigateway");
  const runnerConfig = isRecord$2(pluginConfig["aigw-runner"]) ? { ...pluginConfig["aigw-runner"] } : {};
  const startupTimeout = runnerConfig.startup_timeout_seconds;
  const legacyRunnerRequestedAuth = runnerConfig.auth_enabled === true;
  const legacyRunnerDisabled = runnerConfig.enabled === false;
  delete runnerConfig.auth_enabled;
  delete runnerConfig.enabled;
  if (typeof runnerConfig.uv_bin !== "string" || !runnerConfig.uv_bin.trim()) {
    delete runnerConfig.uv_bin;
  }
  pluginConfig["aigw-runner"] = {
    ...runnerConfig,
    aigateway_dir: gatewayDir,
    database_path: path.join(gatewayDir, "aigateway.db"),
    startup_timeout_seconds: typeof startupTimeout === "number" && startupTimeout >= 60 ? startupTimeout : 60
  };
  if (hadDirectCodexBackend && Object.prototype.hasOwnProperty.call(pluginConfig, LEGACY_DIRECT_CODEX_BACKEND)) {
    if (!isRecord$2(pluginConfig[GATEWAY_CODEX_BACKEND])) {
      pluginConfig[GATEWAY_CODEX_BACKEND] = migrateCodexBackendConfig(
        pluginConfig[LEGACY_DIRECT_CODEX_BACKEND]
      );
    }
    delete pluginConfig[LEGACY_DIRECT_CODEX_BACKEND];
  }
  const baseConfig = isRecord$2(pluginConfig["aigw-base"]) ? { ...pluginConfig["aigw-base"] } : {};
  const urls = gatewayUrls(pluginConfig);
  if (typeof baseConfig.gateway_url !== "string") {
    if (urls.length > 1) throw new GatewayUrlConflictError(urls);
    const runnerPort = runnerConfig.port;
    baseConfig.gateway_url = urls.length === 1 ? urls[0] : typeof runnerPort === "number" && runnerPort > 0 && runnerPort !== 9105 ? `http://127.0.0.1:${runnerPort}` : DEFAULT_GATEWAY_URL$1;
  }
  if (baseConfig.mode !== "local_managed" && baseConfig.mode !== "external") {
    baseConfig.mode = legacyRunnerRequestedAuth || legacyRunnerDisabled ? "external" : "local_managed";
  }
  pluginConfig["aigw-base"] = baseConfig;
  for (const [name, value] of Object.entries(pluginConfig)) {
    if (!isGatewayBackendName(name) || !isRecord$2(value)) continue;
    delete value.gateway_url;
  }
  return {
    ...config,
    server: serverConfig,
    plugins: nextPlugins,
    plugin_config: pluginConfig
  };
}
function resolveServerDir() {
  if (!utils.is.dev) {
    return path.join(process.resourcesPath, "server");
  }
  const appPath = electron.app.getAppPath();
  return path.resolve(appPath, "..", "server");
}
function resolveConfigPath(serverDir) {
  if (!utils.is.dev) {
    const userDataDir = electron.app.getPath("userData");
    fs.mkdirSync(userDataDir, { recursive: true });
    const userDataConfig = path.join(userDataDir, "sf.json");
    if (!fs.existsSync(userDataConfig)) {
      const templatePath = path.join(serverDir, "sf.json");
      if (fs.existsSync(templatePath)) {
        fs.copyFileSync(templatePath, userDataConfig);
      }
    }
    return userDataConfig;
  }
  return path.join(serverDir, "sf.json");
}
let SERVER_DIR;
let CONFIG_PATH;
class ConfigService extends events.EventEmitter {
  configPath;
  initialized = false;
  constructor() {
    super();
  }
  ensureInitialized() {
    if (this.initialized) {
      return;
    }
    SERVER_DIR = resolveServerDir();
    if (!this.configPath) {
      CONFIG_PATH = resolveConfigPath(SERVER_DIR);
      this.configPath = CONFIG_PATH;
    }
    this.initialized = true;
    if (!utils.is.dev) {
      this.migrateDesktopRuntimeConfig();
    }
  }
  get serverDir() {
    this.ensureInitialized();
    return SERVER_DIR;
  }
  setConfigPath(path2) {
    if (this.configPath) {
      fs.unwatchFile(this.configPath);
    }
    this.configPath = path2;
    this.watch();
  }
  read() {
    const configPath = this.getConfigPath();
    try {
      const raw = fs.readFileSync(configPath, "utf-8");
      return JSON.parse(raw);
    } catch {
      return {
        version: "0.1.0",
        server: { host: "127.0.0.1", port: 8e3, reload: false, ssl: true },
        plugins: [],
        plugin_config: {}
      };
    }
  }
  write(config) {
    const configPath = this.getConfigPath();
    writeJsonAtomically(configPath, JSON.stringify(config, null, 2) + "\n");
    this.emit("changed", config);
  }
  watch() {
    const configPath = this.getConfigPath();
    fs.watchFile(configPath, { interval: 1e3, persistent: false }, () => {
      const config = this.read();
      this.emit("changed", config);
    });
  }
  getConfigPath() {
    this.ensureInitialized();
    if (!this.configPath) {
      throw new Error("Config path is not initialized");
    }
    return this.configPath;
  }
  migrateDesktopRuntimeConfig() {
    const config = this.read();
    let migrated;
    try {
      migrated = migrateDesktopRuntimeConfig(config, electron.app.getPath("userData"));
    } catch (error) {
      if (error instanceof GatewayUrlConflictError) {
        electron.dialog.showErrorBox(
          "Choose AIGateway URL",
          `${error.message}

Config: ${this.getConfigPath()}`
        );
      }
      throw error;
    }
    if (JSON.stringify(migrated) !== JSON.stringify(config)) {
      this.write(migrated);
    }
  }
}
function writeJsonAtomically(configPath, contents) {
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  const tempPath = path.join(
    path.dirname(configPath),
    `.${path.basename(configPath)}.${process.pid}.${Date.now()}.tmp`
  );
  let fd;
  try {
    fd = fs.openSync(tempPath, "w", 384);
    fs.writeFileSync(fd, contents, "utf-8");
    fs.fsyncSync(fd);
    fs.closeSync(fd);
    fd = void 0;
    fs.renameSync(tempPath, configPath);
  } catch (error) {
    if (fd !== void 0) {
      fs.closeSync(fd);
    }
    fs.rmSync(tempPath, { force: true });
    throw error;
  }
}
const configService = new ConfigService();
const SECRET_BYTES = 32;
function getDesktopSecretPath() {
  return path.join(electron.app.getPath("userData"), ".sf", "runtime", "desktop.secret");
}
function getDesktopSecretValue() {
  const path$1 = getDesktopSecretPath();
  if (fs.existsSync(path$1)) {
    return fs.readFileSync(path$1, "utf-8").trim();
  }
  fs.mkdirSync(path.dirname(path$1), { recursive: true });
  const secret = crypto.randomBytes(SECRET_BYTES).toString("base64url");
  const fd = fs.openSync(path$1, "w", 384);
  try {
    fs.writeFileSync(fd, secret + "\n", "utf-8");
  } finally {
    fs.closeSync(fd);
  }
  fs.chmodSync(path$1, 384);
  return secret;
}
function desktopSecretHeader() {
  return { "X-SF-Desktop-Secret": getDesktopSecretValue() };
}
const KNOWN_PATHS = [
  path.join(os.homedir(), ".cargo", "bin", "uv"),
  path.join(os.homedir(), ".local", "bin", "uv"),
  "/usr/local/bin/uv",
  "/opt/homebrew/bin/uv"
];
function resolveUv() {
  if (!utils.is.dev) {
    const bundled = path.join(process.resourcesPath, "server", "bin", "uv");
    if (fs.existsSync(bundled)) return bundled;
  }
  try {
    const result = child_process.execFileSync("which", ["uv"], { encoding: "utf-8" }).trim();
    if (result) return result;
  } catch {
  }
  for (const p of KNOWN_PATHS) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}
const execFileAsync = util.promisify(child_process.execFile);
class ServerProcess extends events.EventEmitter {
  child = null;
  status = "stopped";
  healthTimer = null;
  healthFailures = 0;
  restartCount = 0;
  readyInfo = null;
  stopping = false;
  static MAX_HEALTH_FAILURES = 3;
  static MAX_RESTARTS = 3;
  static HEALTH_INTERVAL_MS = 1e4;
  static RESTART_DELAY_MS = 2e3;
  get serverDir() {
    return configService.serverDir;
  }
  get sfBin() {
    if (!utils.is.dev) {
      return path.join(electron.app.getPath("userData"), ".venv", "bin", "sf");
    }
    return path.join(this.serverDir, ".venv", "bin", "sf");
  }
  /** Writable directory used as cwd when spawning the server. */
  get serverCwd() {
    if (!utils.is.dev) {
      return electron.app.getPath("userData");
    }
    return this.serverDir;
  }
  get gatewayProjectDir() {
    if (!utils.is.dev) {
      return path.join(electron.app.getPath("userData"), "aigateway");
    }
    return path.join(this.serverDir, "..", "aigateway");
  }
  get gatewayDatabasePath() {
    return path.join(electron.app.getPath("userData"), "aigateway", "aigateway.db");
  }
  serverEnv() {
    const env = (({ VIRTUAL_ENV: _drop, ...inherited }) => inherited)(
      process.env
    );
    env.SF_AIGW_RUNNER__AIGATEWAY_DIR = this.gatewayProjectDir;
    env.SF_AIGW_RUNNER__DATABASE_PATH = this.gatewayDatabasePath;
    getDesktopSecretValue();
    env.SF_DESKTOP_SECRET_FILE = getDesktopSecretPath();
    const uvBin = resolveUv();
    if (uvBin) env.SF_AIGW_RUNNER__UV_BIN = uvBin;
    return env;
  }
  setStatus(s) {
    this.status = s;
    this.emit("status", s);
  }
  getStatus() {
    return { status: this.status, info: this.readyInfo };
  }
  /**
   * Check if any enabled plugin requires root privileges by querying
   * the `sf plugin list --json` CLI output.
   */
  needsRoot() {
    try {
      const raw = child_process.execFileSync(this.sfBin, ["plugin", "list", "--json"], {
        cwd: this.serverCwd,
        timeout: 1e4
      }).toString();
      const plugins = JSON.parse(raw);
      const config = configService.read();
      const enabled = config.plugins ?? [];
      return enabled.some((name) => plugins[name]?.requires_root === true);
    } catch {
      return false;
    }
  }
  /**
   * Prompt for the admin password via a native macOS dialog.
   * Returns null if the user cancels.
   */
  async promptForPassword() {
    try {
      const { stdout } = await execFileAsync("osascript", [
        "-e",
        'display dialog "ScreamingFace needs administrator privileges for an enabled plugin." default answer "" with hidden answer with title "ScreamingFace" buttons {"Cancel", "OK"} default button "OK"',
        "-e",
        "text returned of result"
      ]);
      return stdout.trim() || null;
    } catch {
      return null;
    }
  }
  async start() {
    if (this.child || this.status === "starting") return false;
    this.setStatus("starting");
    this.readyInfo = null;
    this.stopping = false;
    const config = configService.read();
    const configJson = JSON.stringify(config);
    const args = ["run", "--subprocess", "--config-json", configJson, "--host", "127.0.0.1"];
    const env = this.serverEnv();
    const elevate = this.needsRoot() && process.getuid?.() !== 0;
    let child;
    if (elevate) {
      const password = await this.promptForPassword();
      if (!password) {
        this.setStatus("stopped");
        this.emit("log", "Administrator authentication cancelled");
        return false;
      }
      child = child_process.spawn("sudo", ["-S", this.sfBin, ...args], {
        cwd: this.serverCwd,
        env,
        stdio: ["pipe", "pipe", "pipe"]
      });
      child.stdin.write(password + "\n");
      child.stdin.end();
    } else {
      child = child_process.spawn(this.sfBin, args, {
        cwd: this.serverCwd,
        env,
        stdio: ["ignore", "pipe", "pipe"]
      });
    }
    this.child = child;
    child.stdout.on("data", (data) => {
      const lines = data.toString().split("\n").filter(Boolean);
      for (const line of lines) {
        this.handleStdoutLine(line);
      }
    });
    child.stderr.on("data", (data) => {
      this.emit("log", data.toString());
    });
    child.on("close", (code, signal) => {
      this.stopHealthCheck();
      this.child = null;
      this.readyInfo = null;
      if (this.stopping) return;
      if (code !== 0 && code !== null) {
        this.setStatus("error");
        this.emit("log", `Server exited with code ${code}`);
      } else if (signal) {
        this.setStatus("error");
        this.emit("log", `Server killed by signal ${signal}`);
      } else {
        this.setStatus("stopped");
      }
    });
    child.on("error", (err) => {
      this.emit("log", `Failed to start server: ${err.message}`);
      this.child = null;
      this.setStatus("error");
    });
    return true;
  }
  async stop() {
    this.stopHealthCheck();
    if (!this.child) return;
    this.stopping = true;
    const wasRestarting = this.status === "restarting";
    const child = this.child;
    this.child = null;
    this.readyInfo = null;
    await new Promise((resolve) => {
      child.once("close", () => resolve());
      child.kill("SIGTERM");
      setTimeout(() => {
        try {
          child.kill("SIGKILL");
        } catch {
        }
        resolve();
      }, 5e3);
    });
    this.stopping = false;
    if (!wasRestarting) {
      this.setStatus("stopped");
    }
  }
  async restart() {
    this.setStatus("restarting");
    this.restartCount = 0;
    await this.stop();
    await this.start();
  }
  handleStdoutLine(line) {
    try {
      const parsed = JSON.parse(line);
      if (parsed.event === "ready") {
        this.readyInfo = parsed;
        this.setStatus("ready");
        this.restartCount = 0;
        this.startHealthCheck();
        this.emit("log", `Server ready at ${parsed.scheme}://${parsed.host}:${parsed.port}`);
        return;
      }
    } catch {
    }
    this.emit("log", line);
  }
  startHealthCheck() {
    this.stopHealthCheck();
    this.healthFailures = 0;
    this.healthTimer = setTimeout(() => {
      this.healthTimer = setInterval(async () => {
        this.runHealthCheck();
      }, ServerProcess.HEALTH_INTERVAL_MS);
      this.runHealthCheck();
    }, 2e3);
  }
  async runHealthCheck() {
    if (!this.readyInfo || this.stopping) return;
    try {
      const ok = await this.pingHealth();
      if (ok) {
        this.healthFailures = 0;
      } else {
        this.onHealthFailure();
      }
    } catch {
      this.onHealthFailure();
    }
  }
  pingHealth() {
    return new Promise((resolve) => {
      if (!this.readyInfo) {
        resolve(false);
        return;
      }
      const { scheme, host, port } = this.readyInfo;
      const checkHost = host === "0.0.0.0" ? "127.0.0.1" : host;
      const url2 = `${scheme}://${checkHost}:${port}/health`;
      const mod = scheme === "https" ? https : http;
      const req = mod.get(
        {
          hostname: checkHost,
          port,
          path: "/health",
          timeout: 5e3,
          // Accept self-signed certs for local health checks
          rejectUnauthorized: false
        },
        (res) => {
          res.resume();
          if (res.statusCode === 200) {
            resolve(true);
          } else {
            this.emit("log", `Health check ${url2} returned ${res.statusCode}`);
            resolve(false);
          }
        }
      );
      req.on("timeout", () => {
        this.emit("log", `Health check ${url2} timed out`);
        req.destroy();
        resolve(false);
      });
      req.on("error", (err) => {
        this.emit("log", `Health check ${url2} error: ${err.message}`);
        resolve(false);
      });
    });
  }
  stopHealthCheck() {
    if (this.healthTimer) {
      clearInterval(this.healthTimer);
      this.healthTimer = null;
    }
  }
  onHealthFailure() {
    this.healthFailures++;
    this.emit(
      "log",
      `Health check failed (${this.healthFailures}/${ServerProcess.MAX_HEALTH_FAILURES})`
    );
    if (this.healthFailures >= ServerProcess.MAX_HEALTH_FAILURES) {
      if (this.restartCount < ServerProcess.MAX_RESTARTS) {
        this.restartCount++;
        this.emit(
          "log",
          `Auto-restarting (attempt ${this.restartCount}/${ServerProcess.MAX_RESTARTS})...`
        );
        setTimeout(() => this.autoRestart(), ServerProcess.RESTART_DELAY_MS);
      } else {
        this.setStatus("error");
        this.emit("log", "Max restart attempts reached. Server is down.");
      }
    }
  }
  async autoRestart() {
    this.setStatus("restarting");
    await this.stop();
    await this.start();
  }
}
const serverProcess = new ServerProcess();
const POLL_INTERVAL_MS = 3e4;
const POLL_TIMEOUT_MS = 25e3;
class BackendStatusService extends events.EventEmitter {
  timer = null;
  serverUrl = null;
  previous = {};
  lastPollingError = null;
  consecutivePollingFailures = 0;
  /** Start polling. Call after the server is ready. */
  start(serverUrl) {
    this.serverUrl = serverUrl;
    this.poll();
    this.timer = setInterval(() => this.poll(), POLL_INTERVAL_MS);
  }
  /** Stop polling. */
  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.serverUrl = null;
    this.previous = {};
    this.consecutivePollingFailures = 0;
    if (this.lastPollingError !== null) {
      this.lastPollingError = null;
      this.emit("pollingError", null);
    }
  }
  /** Get current status (last polled). */
  getStatus() {
    return this.previous;
  }
  /** Get the most recent polling failure, if the status poll is currently failing. */
  getPollingError() {
    return this.lastPollingError;
  }
  /** Get the SF server base URL the service is currently polling, if any. */
  getServerUrl() {
    return this.serverUrl;
  }
  /** Force an immediate poll. */
  async refresh() {
    return this.poll();
  }
  /** Open a terminal with the re-auth command for a backend. */
  authenticate(backend) {
    const health = backendMap(this.previous)[backend];
    const command = health?.cli_command;
    if (!command) return;
    if (process.platform === "darwin") {
      child_process.execFile("osascript", [
        "-e",
        `tell application "Terminal" to do script "${escapeAppleScriptString(command)}"`,
        "-e",
        'tell application "Terminal" to activate'
      ]);
    } else if (process.platform === "linux") {
      child_process.execFile("x-terminal-emulator", ["-e", command]);
    }
  }
  async poll() {
    if (!this.serverUrl) return {};
    try {
      const data = await this.fetchStatus();
      this.detectTransitions(data);
      this.previous = data;
      this.emit("statusChanged", data);
      this.consecutivePollingFailures = 0;
      if (this.lastPollingError !== null) {
        this.lastPollingError = null;
        this.emit("pollingError", null);
      }
      return data;
    } catch (e) {
      this.consecutivePollingFailures += 1;
      const pollingError = pollingErrorFromUnknown(e, this.consecutivePollingFailures);
      this.lastPollingError = pollingError;
      this.emit("pollingError", pollingError);
      return this.previous;
    }
  }
  detectTransitions(current) {
    if (isStatusV2(current) && current.gateway.mode === "external" && !current.gateway.authenticated) {
      this.previous = current;
      return;
    }
    const currentBackends = backendMap(current);
    const previousBackends = backendMap(this.previous);
    for (const [name, health] of Object.entries(currentBackends)) {
      const prev = previousBackends[name];
      if (!prev) continue;
      if (prev.action === "healthy" && health.action === "reauth") {
        this.showNotification(
          `${name} needs re-authentication`,
          health.help_text || health.error || `Run: ${health.cli_command}`
        );
        this.emit("alert", { backend: name, type: "reauth", health });
      }
      if (prev.action === "healthy" && health.action === "rate_limited") {
        this.emit("alert", { backend: name, type: "rate_limited", health });
      }
      if ((prev.action === "reauth" || prev.action === "rate_limited") && health.action === "healthy") {
        this.emit("alert", { backend: name, type: "recovered", health });
      }
    }
  }
  showNotification(title, body) {
    if (electron.Notification.isSupported()) {
      new electron.Notification({ title, body }).show();
    }
  }
  async loginGateway(username, password) {
    if (!this.serverUrl) return { ok: false, message: "SF server is not running" };
    try {
      const result = await nodeFetch$1(`${this.serverUrl}/aigateway/session/login`, {
        method: "POST",
        headers: { ...desktopSecretHeader(), "content-type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      if (result.status >= 200 && result.status < 300) {
        await this.refresh();
        return { ok: true };
      }
      return { ok: false, message: extractErrorMessage$1(result.body) ?? `HTTP ${result.status}` };
    } catch (e) {
      return { ok: false, message: e instanceof Error ? e.message : String(e) };
    }
  }
  async logoutGateway() {
    if (!this.serverUrl) return;
    await nodeFetch$1(`${this.serverUrl}/aigateway/session/logout`, {
      method: "POST",
      headers: desktopSecretHeader()
    });
    await this.refresh();
  }
  fetchStatus() {
    return new Promise((resolve, reject) => {
      const url2 = `${this.serverUrl}/backends/status`;
      const parsed = new URL(url2);
      const mod = parsed.protocol === "https:" ? https : http;
      const req = mod.get(
        {
          hostname: parsed.hostname,
          port: parsed.port,
          path: parsed.pathname,
          timeout: POLL_TIMEOUT_MS,
          rejectUnauthorized: false,
          headers: {
            Accept: "application/vnd.screamingface.backends-status+json;version=2",
            ...desktopSecretHeader()
          }
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => {
            data += chunk.toString();
          });
          res.on("end", () => {
            const status = res.statusCode ?? 0;
            if (status < 200 || status >= 300) {
              reject(new BackendStatusPollError(status, data));
              return;
            }
            try {
              resolve(parseBackendStatus(JSON.parse(data)));
            } catch {
              reject(new Error(`Invalid JSON from /backends/status`));
            }
          });
        }
      );
      req.on("timeout", () => {
        req.destroy();
        reject(new Error("timeout"));
      });
      req.on("error", reject);
    });
  }
}
class BackendStatusPollError extends Error {
  code;
  status;
  constructor(status, body) {
    const message = extractErrorMessage$1(body) ?? `HTTP ${status}`;
    super(message);
    this.name = "BackendStatusPollError";
    this.status = status;
    this.code = extractErrorCode$1(body);
  }
}
const backendStatusService = new BackendStatusService();
function isStatusV2(value) {
  if (!isRecord$1(value) || value.version !== 2) return false;
  return isGatewayStatus(value.gateway);
}
function backendMap(value) {
  if (isStatusV2(value)) return value.backends ?? {};
  return value;
}
function parseBackendStatus(value, desktopGatewayConfig) {
  if (isStatusV2(value)) return value;
  if (isRecord$1(value) && typeof value.version === "number" && value.version > 2) {
    return {
      version: 2,
      gateway: isGatewayStatus(value.gateway) ? value.gateway : gatewayStatusFromDesktopConfig(),
      action: "gateway_misconfigured",
      message: "Desktop app is out of date — update required to use this SF server"
    };
  }
  if (isLegacyStatusMap(value)) {
    if (desktopConfigGatewayMode() === "external") {
      return {
        version: 2,
        gateway: gatewayStatusFromDesktopConfig(),
        action: "gateway_misconfigured",
        message: "SF server is out of date — update required to use external gateway mode"
      };
    }
    return value;
  }
  throw new Error("Unsupported /backends/status response");
}
function isLegacyStatusMap(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return !Object.prototype.hasOwnProperty.call(value, "version");
}
function isRecord$1(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isGatewayStatus(value) {
  if (!isRecord$1(value)) return false;
  return (value.mode === "local_managed" || value.mode === "external") && typeof value.managed_by_runner === "boolean" && typeof value.reachable === "boolean" && typeof value.authenticated === "boolean" && typeof value.auth_required === "boolean" && typeof value.url === "string";
}
function gatewayStatusFromDesktopConfig(desktopGatewayConfig) {
  const mode = desktopConfigGatewayMode();
  return {
    mode,
    managed_by_runner: mode === "local_managed",
    reachable: false,
    authenticated: false,
    auth_required: true,
    url: desktopConfigGatewayUrl()
  };
}
function desktopConfigGatewayMode(desktopGatewayConfig) {
  const base = desktopConfigAigwBase();
  return base.mode === "external" ? "external" : "local_managed";
}
function desktopConfigGatewayUrl(desktopGatewayConfig) {
  const base = desktopConfigAigwBase();
  return typeof base.gateway_url === "string" ? base.gateway_url : "http://127.0.0.1:9105";
}
function desktopConfigAigwBase() {
  const config = configService.read();
  const pluginConfig = config.plugin_config;
  if (typeof pluginConfig !== "object" || pluginConfig === null || Array.isArray(pluginConfig))
    return {};
  const base = pluginConfig["aigw-base"];
  if (typeof base !== "object" || base === null || Array.isArray(base)) return {};
  return base;
}
function nodeFetch$1(url2, init) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url2);
    const mod = parsed.protocol === "https:" ? https : http;
    const req = mod.request(
      url2,
      {
        method: init?.method ?? "GET",
        headers: init?.headers,
        timeout: POLL_TIMEOUT_MS,
        rejectUnauthorized: false
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk.toString();
        });
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body: data }));
      }
    );
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("timeout"));
    });
    req.on("error", reject);
    if (init?.body) req.write(init.body);
    req.end();
  });
}
function extractErrorMessage$1(body) {
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed.message === "string") return parsed.message;
    const detail = unwrapFastApiDetail(parsed.detail);
    if (Array.isArray(detail)) {
      const first = detail.find((entry) => typeof entry === "object" && entry !== null);
      if (first) {
        const record = first;
        const msg = typeof record.msg === "string" ? record.msg : void 0;
        if (!msg) return void 0;
        const loc = Array.isArray(record.loc) ? record.loc.filter((part) => typeof part === "string").slice(1).join(".") : "";
        return loc ? `${loc}: ${msg}` : msg;
      }
      return void 0;
    }
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null) {
      const message = detail.message;
      if (typeof message === "string") return message;
      const code = detail.code;
      if (typeof code === "string") return code;
    }
  } catch {
    return void 0;
  }
  return void 0;
}
function extractErrorCode$1(body) {
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed.code === "string") return parsed.code;
    const detail = unwrapFastApiDetail(parsed.detail);
    if (typeof detail === "object" && detail !== null) {
      const code = detail.code;
      if (typeof code === "string") return code;
    }
  } catch {
    return void 0;
  }
  return void 0;
}
function pollingErrorFromUnknown(error, consecutiveFailures) {
  if (error instanceof BackendStatusPollError) {
    const pollingError = {
      status: error.status,
      message: error.message,
      consecutiveFailures
    };
    if (error.code) pollingError.code = error.code;
    return pollingError;
  }
  return {
    message: error instanceof Error ? error.message : String(error),
    consecutiveFailures
  };
}
function unwrapFastApiDetail(detail) {
  if (typeof detail === "object" && detail !== null && "detail" in detail) {
    return detail.detail;
  }
  return detail;
}
function escapeAppleScriptString(value) {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r/g, "\\r").replace(/\n/g, "\\n");
}
const AIGW_BASE_PLUGIN = "aigw-base";
const DEFAULT_GATEWAY_URL = "http://127.0.0.1:9105";
const JWT_REFRESH_BUFFER_MS = 3e4;
const REQUEST_TIMEOUT_MS = 25e3;
const USERNAME_KEY = "aigw_credentials_username";
const ENCRYPTED_PASSWORD_KEY = "aigw_credentials_enc";
const PLAINTEXT_PASSWORD_KEY = "aigw_credentials_plaintext";
const STORAGE_KEY = "aigw_credentials_storage";
class AigwSessionService extends events.EventEmitter {
  config;
  storage;
  requestJson;
  secretHeader;
  now;
  initialized = false;
  serverUrl = null;
  jwt = null;
  jwtExpiresAt = null;
  credentials = null;
  credentialsPersisted = false;
  storedInPlaintext = false;
  lastError = null;
  constructor(dependencies = {}) {
    super();
    this.config = dependencies.config ?? configService;
    this.storage = dependencies.safeStorage ?? electron.safeStorage;
    this.requestJson = dependencies.requestJson ?? nodeRequestJson;
    this.secretHeader = dependencies.desktopSecretHeader ?? desktopSecretHeader;
    this.now = dependencies.now ?? (() => /* @__PURE__ */ new Date());
  }
  async init() {
    if (this.initialized) return this.snapshot();
    this.initialized = true;
    this.credentials = this.loadCredentials();
    this.credentialsPersisted = this.credentials !== null;
    this.emitChanged();
    if (this.serverUrl && this.credentials) {
      await this.login(this.credentials, this.silentLoginOptions());
    }
    return this.snapshot();
  }
  async setServerUrl(serverUrl) {
    const nextUrl = serverUrl ? normalizeBaseUrl(serverUrl) : null;
    if (this.serverUrl === nextUrl) return this.snapshot();
    this.serverUrl = nextUrl;
    this.clearJwtOnly();
    this.emitChanged();
    if (this.initialized && this.serverUrl && this.credentials) {
      await this.login(this.credentials, this.silentLoginOptions());
    }
    return this.snapshot();
  }
  getState() {
    return this.snapshot();
  }
  isLoggedIn() {
    return this.hasValidJwt();
  }
  async getJwt() {
    if (this.hasValidJwt(JWT_REFRESH_BUFFER_MS)) return this.jwt;
    const hadJwt = this.jwt !== null;
    this.clearJwtOnly();
    if (this.credentials) {
      const result = await this.login(this.credentials, this.silentLoginOptions());
      if (result.ok && this.hasValidJwt(JWT_REFRESH_BUFFER_MS)) return this.jwt;
    }
    if (hadJwt) this.emitExpired("AIGateway session expired");
    return null;
  }
  async ensureLoggedIn() {
    if (!this.credentials) {
      this.emitExpired("AIGateway login required");
      return null;
    }
    const result = await this.login(this.credentials, this.silentLoginOptions());
    if (result.ok) return this.jwt;
    this.emitExpired(result.message);
    return null;
  }
  async login(credentials, options = {}) {
    const persist = options.persist ?? true;
    if (!this.serverUrl) {
      return this.loginFailure(
        "SF server is not running. Start the Desktop server and try again.",
        options.silent === true
      );
    }
    if (persist && !this.encryptionAvailable() && options.allowPlaintextStorage !== true) {
      return this.loginFailure(
        'OS-provided encryption is unavailable. Uncheck "Save password" to sign in for this Desktop session only, or allow plaintext storage.',
        options.silent === true
      );
    }
    try {
      const response = await this.requestJson(`${this.serverUrl}/aigateway/session/login`, {
        method: "POST",
        headers: { ...this.secretHeader(), "content-type": "application/json" },
        body: JSON.stringify({ ...credentials, gateway_url: this.gatewayUrl() })
      });
      if (response.status < 200 || response.status >= 300) {
        return this.loginFailure(describeLoginResponse(response), false);
      }
      const token = readStringField(response.json, "token");
      const expiresAt = parseExpiresAt(readStringField(response.json, "expires_at"));
      if (!token || !expiresAt) {
        return this.loginFailure("Gateway login returned an invalid session", false);
      }
      this.jwt = token;
      this.jwtExpiresAt = expiresAt;
      this.credentials = { ...credentials };
      this.credentialsPersisted = persist;
      this.lastError = null;
      const warning = persist ? this.saveCredentials(credentials, options.allowPlaintextStorage === true) : this.clearPersistedCredentials();
      this.emitChanged();
      const snapshot = this.snapshot();
      return warning ? { ok: true, snapshot, warning } : { ok: true, snapshot };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return this.loginFailure(describeNetworkError(message), options.silent === true);
    }
  }
  async logout() {
    if (this.serverUrl) {
      try {
        await this.requestJson(`${this.serverUrl}/aigateway/session/logout`, {
          method: "POST",
          headers: this.secretHeader()
        });
      } catch {
      }
    }
    this.clearJwtOnly();
    this.credentials = null;
    this.credentialsPersisted = false;
    this.lastError = null;
    this.clearPersistedCredentials();
    this.emitChanged();
    return this.snapshot();
  }
  notifyExpired(message = "AIGateway session expired") {
    this.emitExpired(message);
  }
  setGatewayUrl(gatewayUrl) {
    const normalized = validateGatewayUrl(gatewayUrl);
    const config = this.config.read();
    const pluginConfig = readPluginConfig(config);
    const baseConfig = readAigwBaseConfig(config);
    baseConfig.gateway_url = normalized;
    baseConfig.mode = "external";
    pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
    config.plugin_config = pluginConfig;
    this.config.write(config);
    this.clearJwtOnly();
    this.emitChanged();
    return this.snapshot();
  }
  snapshot() {
    const username = this.credentials?.username ?? readStringField(readAigwBaseConfig(this.config.read()), USERNAME_KEY);
    return {
      hasValidJwt: this.hasValidJwt(),
      jwtExpiresAt: this.jwtExpiresAt ? this.jwtExpiresAt.toISOString() : null,
      isLoggedIn: this.hasValidJwt(),
      username: username ?? null,
      gatewayUrl: this.gatewayUrl(),
      rememberAvailable: true,
      secureStorageAvailable: this.encryptionAvailable(),
      storedInPlaintext: this.storedInPlaintext,
      lastError: this.lastError
    };
  }
  hasValidJwt(bufferMs = 0) {
    if (!this.jwt || !this.jwtExpiresAt) return false;
    return this.jwtExpiresAt.getTime() > this.now().getTime() + bufferMs;
  }
  clearJwtOnly() {
    this.jwt = null;
    this.jwtExpiresAt = null;
  }
  emitChanged() {
    this.emit("changed", this.snapshot());
  }
  emitExpired(message) {
    this.clearJwtOnly();
    this.lastError = message;
    const snapshot = this.snapshot();
    this.emit("expired", snapshot);
    this.emit("changed", snapshot);
  }
  loginFailure(message, silent) {
    this.clearJwtOnly();
    this.lastError = message;
    if (!silent) this.emitChanged();
    return { ok: false, message, snapshot: this.snapshot() };
  }
  silentLoginOptions() {
    return {
      persist: this.credentialsPersisted,
      silent: true,
      allowPlaintextStorage: this.storedInPlaintext
    };
  }
  loadCredentials() {
    const baseConfig = readAigwBaseConfig(this.config.read());
    const username = readStringField(baseConfig, USERNAME_KEY);
    if (!username) return null;
    const encrypted = readStringField(baseConfig, ENCRYPTED_PASSWORD_KEY);
    if (encrypted) {
      try {
        this.storedInPlaintext = false;
        return { username, password: this.storage.decryptString(Buffer.from(encrypted, "base64")) };
      } catch {
        this.lastError = "Stored AIGateway credentials could not be decrypted";
        this.clearPersistedCredentials();
        return null;
      }
    }
    const plaintext = readStringField(baseConfig, PLAINTEXT_PASSWORD_KEY);
    if (!plaintext) return null;
    this.storedInPlaintext = true;
    return { username, password: plaintext };
  }
  saveCredentials(credentials, allowPlaintextStorage) {
    const config = this.config.read();
    const pluginConfig = readPluginConfig(config);
    const baseConfig = readAigwBaseConfig(config);
    baseConfig[USERNAME_KEY] = credentials.username;
    delete baseConfig[ENCRYPTED_PASSWORD_KEY];
    delete baseConfig[PLAINTEXT_PASSWORD_KEY];
    delete baseConfig[STORAGE_KEY];
    if (this.encryptionAvailable()) {
      try {
        baseConfig[ENCRYPTED_PASSWORD_KEY] = this.storage.encryptString(credentials.password).toString("base64");
        baseConfig[STORAGE_KEY] = "safeStorage";
        this.storedInPlaintext = false;
        pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
        config.plugin_config = pluginConfig;
        this.config.write(config);
        return void 0;
      } catch {
        if (!allowPlaintextStorage) {
          pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
          config.plugin_config = pluginConfig;
          this.config.write(config);
          this.credentialsPersisted = false;
          this.storedInPlaintext = false;
          return "AIGateway password was not saved because OS-provided encryption failed. You are signed in for this Desktop session only.";
        }
      }
    }
    if (!allowPlaintextStorage) {
      pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
      config.plugin_config = pluginConfig;
      this.config.write(config);
      this.credentialsPersisted = false;
      this.storedInPlaintext = false;
      return "AIGateway password was not saved because OS-provided encryption is unavailable. You are signed in for this Desktop session only.";
    }
    baseConfig[PLAINTEXT_PASSWORD_KEY] = credentials.password;
    baseConfig[STORAGE_KEY] = "plaintext";
    this.storedInPlaintext = true;
    pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
    config.plugin_config = pluginConfig;
    this.config.write(config);
    return "AIGateway password was saved in plaintext because OS-provided encryption is unavailable.";
  }
  clearPersistedCredentials() {
    const config = this.config.read();
    const pluginConfig = readPluginConfig(config);
    const baseConfig = readAigwBaseConfig(config);
    delete baseConfig[USERNAME_KEY];
    delete baseConfig[ENCRYPTED_PASSWORD_KEY];
    delete baseConfig[PLAINTEXT_PASSWORD_KEY];
    delete baseConfig[STORAGE_KEY];
    pluginConfig[AIGW_BASE_PLUGIN] = baseConfig;
    config.plugin_config = pluginConfig;
    this.config.write(config);
    this.storedInPlaintext = false;
    return void 0;
  }
  encryptionAvailable() {
    try {
      return this.storage.isEncryptionAvailable();
    } catch {
      return false;
    }
  }
  gatewayUrl() {
    const gatewayUrl = readStringField(readAigwBaseConfig(this.config.read()), "gateway_url");
    return gatewayUrl ? normalizeBaseUrl(gatewayUrl) : DEFAULT_GATEWAY_URL;
  }
}
const aigwSessionService = new AigwSessionService();
function readPluginConfig(config) {
  return isRecord(config.plugin_config) ? { ...config.plugin_config } : {};
}
function readAigwBaseConfig(config) {
  const pluginConfig = readPluginConfig(config);
  const value = pluginConfig[AIGW_BASE_PLUGIN];
  return isRecord(value) ? { ...value } : {};
}
function readStringField(value, key) {
  if (!isRecord(value)) return void 0;
  const field = value[key];
  return typeof field === "string" && field.length > 0 ? field : void 0;
}
function parseExpiresAt(value) {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : new Date(timestamp);
}
function validateGatewayUrl(value) {
  let parsed;
  try {
    parsed = new URL(value.trim());
  } catch {
    throw new Error("AIGateway URL must be an absolute http or https URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("AIGateway URL must use http or https");
  }
  if (parsed.username || parsed.password) {
    throw new Error("AIGateway URL must not include credentials");
  }
  if (parsed.protocol === "http:" && !insecureGatewayUrlAllowed(parsed.hostname)) {
    throw new Error("External AIGateway URL must use HTTPS unless it is loopback");
  }
  parsed.hash = "";
  parsed.search = "";
  return normalizeBaseUrl(parsed.toString());
}
function insecureGatewayUrlAllowed(hostname) {
  if (process.env["SF_AIGW_ALLOW_INSECURE_EXTERNAL"] === "1") return true;
  return isLoopbackHost(hostname);
}
function isLoopbackHost(hostname) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (normalized === "localhost") return true;
  const version = net.isIP(normalized);
  if (version === 4) return normalized.split(".")[0] === "127";
  if (version === 6) return normalized === "::1";
  return false;
}
function normalizeBaseUrl(value) {
  return value.trim().replace(/\/+$/, "");
}
function shouldVerifyServerCertificate(parsed) {
  if (process.env["SF_DESKTOP_ALLOW_INSECURE_SERVER_TLS"] === "1") return false;
  return !isLoopbackHost(parsed.hostname);
}
function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
async function nodeRequestJson(url2, init) {
  const response = await nodeRequest(url2, init);
  let json = null;
  if (response.body) {
    try {
      json = JSON.parse(response.body);
    } catch {
      json = null;
    }
  }
  return { ...response, json };
}
function nodeRequest(url2, init) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url2);
    const mod = parsed.protocol === "https:" ? https : http;
    const requestOptions = {
      method: init?.method ?? "GET",
      headers: init?.headers,
      timeout: REQUEST_TIMEOUT_MS,
      ...parsed.protocol === "https:" ? { rejectUnauthorized: shouldVerifyServerCertificate(parsed) } : {}
    };
    const req = mod.request(url2, requestOptions, (res) => {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk.toString();
      });
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
    });
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("timeout"));
    });
    req.on("error", reject);
    if (init?.body) req.write(init.body);
    req.end();
  });
}
function extractErrorMessage(response) {
  if (isRecord(response.json)) {
    const message = readStringField(response.json, "message");
    if (message) return message;
    const detail = response.json.detail;
    if (typeof detail === "string") return detail;
    if (isRecord(detail)) {
      return readStringField(detail, "message") ?? readStringField(detail, "code");
    }
  }
  return response.body || void 0;
}
function extractErrorCode(response) {
  if (!isRecord(response.json)) return void 0;
  const code = readStringField(response.json, "code");
  if (code) return code;
  const detail = response.json.detail;
  return isRecord(detail) ? readStringField(detail, "code") : void 0;
}
function describeLoginResponse(response) {
  const detail = extractErrorMessage(response);
  const code = extractErrorCode(response);
  if (response.status === 401) return detail ?? "Invalid AIGateway username or password.";
  if (code === "invalid_gateway_url") return `Check the AIGateway URL. ${detail ?? ""}`.trim();
  if (code === "gateway_unreachable") {
    return `AIGateway is unreachable. Check the URL and that the gateway is running.${detail ? ` ${detail}` : ""}`;
  }
  if (code === "local_managed") return detail ?? "Gateway login is external-mode only.";
  return detail ?? `HTTP ${response.status}`;
}
function describeNetworkError(message) {
  if (message === "timeout") {
    return "Timed out reaching the SF server. Check the Desktop server status and try again.";
  }
  if (/self-signed|certificate|CERT_/i.test(message)) {
    return `Could not verify the SF server certificate. Loopback development servers are allowed; for non-loopback servers, use a trusted certificate. ${message}`;
  }
  return message;
}
const BACKEND_NAME_RE = /^[a-z0-9-]+$/;
const OAUTH_CONNECTION_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const UUID_PATH_SEGMENT_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const GOOGLE_CLIENT_IDS = /* @__PURE__ */ new Set([
  "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com",
  "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
]);
const OAUTH_AUTHORIZE_POLICIES = /* @__PURE__ */ new Map([
  [
    "auth.openai.com",
    {
      authorizePath: "/oauth/authorize",
      redirectPath: "/auth/callback",
      ports: /* @__PURE__ */ new Set(["1455", "1457"])
    }
  ],
  [
    "chatgpt.com",
    {
      authorizePath: "/oauth/authorize",
      redirectPath: "/auth/callback",
      ports: /* @__PURE__ */ new Set(["1455", "1457"])
    }
  ],
  [
    "claude.com",
    { authorizePath: "/cai/oauth/authorize", redirectPath: "/callback", ports: /* @__PURE__ */ new Set(["9105"]) }
  ],
  [
    "claude.ai",
    { authorizePath: "/oauth/authorize", redirectPath: "/callback", ports: /* @__PURE__ */ new Set(["9105"]) }
  ],
  [
    "accounts.google.com",
    {
      authorizePath: "/o/oauth2/v2/auth",
      redirectPath: "/oauth2callback",
      ports: /* @__PURE__ */ new Set(["9105"]),
      clientIds: GOOGLE_CLIENT_IDS
    }
  ]
]);
function isSafeBackendName(backendName) {
  return BACKEND_NAME_RE.test(backendName);
}
function isSafeOAuthConnectionId(connectionId) {
  return OAUTH_CONNECTION_ID_RE.test(connectionId);
}
function isPinnedClientIdSatisfied(clientIds, clientId) {
  if (!clientIds) return true;
  return clientId !== null && clientIds.has(clientId);
}
function isAllowedOAuthAuthorizeUrl(urlString, options) {
  const url2 = parseHttpsUrl(urlString);
  if (!url2) return false;
  const policy = OAUTH_AUTHORIZE_POLICIES.get(url2.hostname);
  if (!policy) return false;
  if (url2.pathname !== policy.authorizePath) return false;
  const params = url2.searchParams;
  if (!hasSingleParam(params, "response_type", "code")) return false;
  if (!hasSingleParam(params, "client_id")) return false;
  if (!isPinnedClientIdSatisfied(policy.clientIds, params.get("client_id"))) return false;
  if (!hasSingleParam(params, "redirect_uri")) return false;
  if (!hasSingleParam(params, "scope")) return false;
  if (!hasSingleParam(params, "state")) return false;
  if (!hasSingleParam(params, "code_challenge")) return false;
  if (!hasSingleParam(params, "code_challenge_method", "S256")) return false;
  const redirectUri = params.get("redirect_uri");
  if (!redirectUri || !isLoopbackRedirectUri(redirectUri, policy, options)) {
    return false;
  }
  return true;
}
function isAllowedExternalBrowserUrl(urlString) {
  let url2;
  try {
    url2 = new URL(urlString);
  } catch {
    return false;
  }
  return url2.protocol === "https:" && url2.username === "" && url2.password === "";
}
function isAllowedServerFetchUrl(urlString, serverInfo, method = "GET") {
  if (!serverInfo) return false;
  let url2;
  try {
    url2 = new URL(urlString);
  } catch {
    return false;
  }
  const expectedProtocol = `${serverInfo.scheme}:`;
  if (url2.protocol !== expectedProtocol) return false;
  if (url2.username || url2.password) return false;
  if (!isLoopbackHostname$1(url2.hostname)) return false;
  if (!isLoopbackOrWildcardHostname(serverInfo.host)) return false;
  if (url2.port !== String(serverInfo.port)) return false;
  return isAllowedServerFetchPathAndMethod(url2, method);
}
function isAllowedPopupUrl(urlString) {
  let url2;
  try {
    url2 = new URL(urlString);
  } catch {
    return false;
  }
  return url2.protocol === "http:" && isLoopbackHostname$1(url2.hostname) && url2.port === "6006" && url2.username === "" && url2.password === "";
}
function parseHttpsUrl(urlString) {
  try {
    const url2 = new URL(urlString);
    if (url2.protocol !== "https:") return null;
    if (url2.username || url2.password || url2.port) return null;
    return url2;
  } catch {
    return null;
  }
}
function hasSingleParam(params, name, expectedValue) {
  const values = params.getAll(name);
  if (values.length !== 1 || values[0] === "") return false;
  return expectedValue === void 0 || values[0] === expectedValue;
}
function isLoopbackRedirectUri(redirectUri, policy, options) {
  try {
    const url2 = new URL(redirectUri);
    const ports = allowedRedirectPorts(policy, options);
    return url2.protocol === "http:" && isLoopbackHostname$1(url2.hostname) && ports.has(url2.port) && url2.pathname === policy.redirectPath && url2.search === "" && url2.hash === "" && url2.username === "" && url2.password === "";
  } catch {
    return false;
  }
}
function allowedRedirectPorts(policy, options) {
  const ports = new Set(policy.ports);
  for (const port of options?.allowedRedirectPorts ?? []) {
    const normalized = String(port);
    if (/^[1-9][0-9]{0,4}$/.test(normalized) && Number(normalized) <= 65535) {
      ports.add(normalized);
    }
  }
  return ports;
}
function isLoopbackHostname$1(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}
function isLoopbackOrWildcardHostname(hostname) {
  return isLoopbackHostname$1(hostname) || hostname === "0.0.0.0";
}
function isAllowedServerFetchPathAndMethod(url2, method) {
  const normalizedMethod = method.toUpperCase();
  if (url2.hash) return false;
  if (url2.pathname === "/private" && hasNoQuery(url2)) {
    return normalizedMethod === "GET" || normalizedMethod === "POST";
  }
  const privateMatch = /^\/private\/([^/]+)$/.exec(url2.pathname);
  if (privateMatch && hasNoQuery(url2) && UUID_PATH_SEGMENT_RE.test(privateMatch[1])) {
    return normalizedMethod === "GET" || normalizedMethod === "PUT" || normalizedMethod === "DELETE";
  }
  if (url2.pathname === "/plugins" && hasNoQuery(url2)) {
    return normalizedMethod === "GET";
  }
  if (/^\/plugins\/[a-z0-9-]+\/schema$/.test(url2.pathname) && hasNoQuery(url2)) {
    return normalizedMethod === "GET";
  }
  if (/^\/plugins\/[a-z0-9-]+\/settings$/.test(url2.pathname) && hasNoQuery(url2)) {
    return normalizedMethod === "GET" || normalizedMethod === "POST";
  }
  if (/^\/plugins\/[a-z0-9-]+\/settings\/validate$/.test(url2.pathname) && hasNoQuery(url2)) {
    return normalizedMethod === "POST";
  }
  if (url2.pathname === "/config/validate" && hasNoQuery(url2)) {
    return normalizedMethod === "POST";
  }
  if (url2.pathname === "/ensemble/format" && hasNoQuery(url2)) {
    return normalizedMethod === "POST";
  }
  if (url2.pathname === "/ensemble/highlight") {
    return normalizedMethod === "GET" && hasSingleParam(url2.searchParams, "q") && hasOnlySingleQueryParams(url2, /* @__PURE__ */ new Set(["q"]));
  }
  if (url2.pathname === "/ensemble") {
    return normalizedMethod === "GET" && hasSingleParam(url2.searchParams, "q") && hasOnlySingleQueryParams(url2, /* @__PURE__ */ new Set(["q", "ast", "processor"]));
  }
  if (url2.pathname === "/eval_runs") {
    return normalizedMethod === "GET" && hasOnlySingleQueryParams(url2, /* @__PURE__ */ new Set(["limit", "offset"]));
  }
  const evalRunMatch = /^\/eval_runs\/([^/]+)$/.exec(url2.pathname);
  if (evalRunMatch && hasNoQuery(url2) && UUID_PATH_SEGMENT_RE.test(evalRunMatch[1])) {
    return normalizedMethod === "GET" || normalizedMethod === "PATCH" || normalizedMethod === "DELETE";
  }
  return false;
}
function hasNoQuery(url2) {
  return url2.search === "";
}
function hasOnlySingleQueryParams(url2, allowedParams) {
  const seen = /* @__PURE__ */ new Set();
  for (const [key, value] of url2.searchParams) {
    if (!allowedParams.has(key) || seen.has(key) || value === "") return false;
    seen.add(key);
  }
  return true;
}
function requireTrustedIpcSender(event) {
  const frameUrl = event.senderFrame?.url ?? event.sender.getURL();
  if (!isTrustedIpcSenderUrl(frameUrl)) {
    throw new Error("untrusted IPC sender");
  }
}
function isTrustedIpcSenderUrl(frameUrl, trustedRendererUrl) {
  let url2;
  try {
    url2 = new URL(frameUrl);
  } catch {
    return false;
  }
  if (url2.protocol === "file:") {
    const trusted = new URL(packagedRendererFileUrl());
    return trusted.protocol === "file:" && url2.pathname === trusted.pathname && url2.search === "" && url2.username === "" && url2.password === "";
  }
  if (utils.is.dev) {
    const rendererUrl = process.env["ELECTRON_RENDERER_URL"];
    if (rendererUrl) return sameOrigin(url2, rendererUrl);
    return url2.protocol === "http:" && isLoopbackHostname(url2.hostname);
  }
  return false;
}
function packagedRendererFileUrl() {
  return url.pathToFileURL(path.join(__dirname, "../renderer/index.html")).href;
}
function sameOrigin(url2, expectedUrlString) {
  try {
    const expected = new URL(expectedUrlString);
    return url2.origin === expected.origin;
  } catch {
    return false;
  }
}
function isLoopbackHostname(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}
function nodeFetch(url2, init) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url2);
    const mod = parsed.protocol === "https:" ? https : http;
    const method = init?.method ?? "GET";
    const req = mod.request(
      url2,
      {
        method,
        rejectUnauthorized: false,
        timeout: 5e3,
        headers: serverFetchHeaders(init)
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk.toString();
        });
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body: data }));
      }
    );
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("timeout"));
    });
    req.on("error", reject);
    if (init?.body) req.write(init.body);
    req.end();
  });
}
function serverFetchHeaders(init) {
  const rendererHeaders = Object.fromEntries(
    Object.entries(init?.headers ?? {}).filter(
      ([key]) => key.toLowerCase() !== "x-sf-desktop-secret"
    )
  );
  return {
    ...init?.body ? { "Content-Type": "application/json" } : {},
    ...rendererHeaders,
    ...desktopSecretHeader()
  };
}
function registerServerHandlers() {
  electron.ipcMain.handle("server:start", (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.start();
  });
  electron.ipcMain.handle("server:stop", (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.stop();
  });
  electron.ipcMain.handle("server:restart", (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.restart();
  });
  electron.ipcMain.handle("server:getStatus", (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.getStatus();
  });
  electron.ipcMain.handle("server:fetch", async (event, url2, init) => {
    requireTrustedIpcSender(event);
    const { info } = serverProcess.getStatus();
    if (!info) {
      return { ok: false, status: 503, body: "server_restarting" };
    }
    if (!isAllowedServerFetchUrl(url2, info, init?.method ?? "GET")) {
      return { ok: false, status: 0, body: "" };
    }
    try {
      const { status, body } = await nodeFetch(url2, init);
      return { ok: status >= 200 && status < 300, status, body };
    } catch {
      return { ok: false, status: 0, body: "" };
    }
  });
  serverProcess.on("status", (status) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("server:statusChanged", status);
    }
    if (status === "ready") {
      const { info } = serverProcess.getStatus();
      if (info) {
        const host = info.host === "0.0.0.0" ? "127.0.0.1" : info.host;
        const serverUrl = `${info.scheme}://${host}:${info.port}`;
        void aigwSessionService.setServerUrl(serverUrl);
        backendStatusService.start(serverUrl);
      }
    } else if (status === "stopped" || status === "error") {
      void aigwSessionService.setServerUrl(null);
      backendStatusService.stop();
    }
  });
  serverProcess.on("log", (line) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("server:log", line);
    }
  });
}
const debugLogPath = path.join(electron.app.getPath("userData"), "debug.log");
try {
  fs.writeFileSync(debugLogPath, `=== ScreamingFace launch ${(/* @__PURE__ */ new Date()).toISOString()} ===
`);
} catch {
}
function log(msg) {
  const line = `[${Date.now()}] ${msg}
`;
  try {
    fs.appendFileSync(debugLogPath, line);
  } catch {
  }
}
class VenvManager extends events.EventEmitter {
  status = "unknown";
  uvBin = null;
  syncing = false;
  get serverDir() {
    return configService.serverDir;
  }
  /** In production, uv commands run from userData (writable) instead of the read-only bundle. */
  get projectDir() {
    if (!utils.is.dev) {
      return electron.app.getPath("userData");
    }
    return this.serverDir;
  }
  get venvDir() {
    return path.join(this.projectDir, ".venv");
  }
  get pythonBin() {
    return path.join(this.venvDir, "bin", "python");
  }
  get bundledPythonBin() {
    if (utils.is.dev) return null;
    const bundledPython = path.join(process.resourcesPath, "server", "python", "bin", "python3.12");
    return fs.existsSync(bundledPython) ? bundledPython : null;
  }
  get gatewayProjectDir() {
    return path.join(electron.app.getPath("userData"), "aigateway");
  }
  get gatewayVenvDir() {
    return path.join(this.gatewayProjectDir, ".venv");
  }
  get gatewayPythonBin() {
    return path.join(this.gatewayVenvDir, "bin", "python");
  }
  setStatus(s) {
    log(`[venv] status: ${this.status} -> ${s}`);
    this.status = s;
    this.emit("status", s);
  }
  getStatus() {
    return this.status;
  }
  async detect() {
    log(`[venv] detect() called`);
    log(`[venv] serverDir=${this.serverDir} projectDir=${this.projectDir} venvDir=${this.venvDir}`);
    this.setStatus("checking");
    this.uvBin = resolveUv();
    log(`[venv] uvBin=${this.uvBin}`);
    if (!this.uvBin) {
      this.setStatus("error");
      return { status: "error", uvFound: false, needsSync: false, autoBootstrap: false };
    }
    log(`[venv] pythonBin=${this.pythonBin} exists=${fs.existsSync(this.pythonBin)}`);
    if (fs.existsSync(this.pythonBin)) {
      try {
        const pyVer = child_process.execFileSync(this.pythonBin, ["--version"], { encoding: "utf-8" });
        log(`[venv] python --version: ${pyVer.trim()}`);
        this.setStatus("ready");
        const needsSync = this.needsResync() || !utils.is.dev && !fs.existsSync(this.gatewayPythonBin);
        log(`[venv] needsResync=${needsSync}`);
        return { status: "ready", uvFound: true, needsSync, autoBootstrap: false };
      } catch {
        this.setStatus("error");
        return { status: "error", uvFound: true, needsSync: false, autoBootstrap: false };
      }
    }
    this.setStatus("missing");
    log(`[venv] detect result: missing, autoBootstrap=${!utils.is.dev}`);
    return { status: "missing", uvFound: true, needsSync: false, autoBootstrap: !utils.is.dev };
  }
  async create() {
    log(`[venv] create() called`);
    if (!this.uvBin) {
      this.setStatus("error");
      return false;
    }
    this.setStatus("creating");
    const args = [this.uvBin, "venv", this.venvDir];
    if (!utils.is.dev) {
      const bundledPython = this.bundledPythonBin;
      if (bundledPython) {
        args.push("--python", bundledPython);
      }
    }
    log(`[venv] create() spawning: ${args.join(" ")}`);
    const ok = await this.runUvCommand(args, void 0, { suppressReady: true });
    log(`[venv] create() result=${ok}`);
    return ok;
  }
  async sync(extra) {
    log(`[venv] sync() called, extra=${extra}`);
    if (this.syncing) {
      log(`[venv] sync already in progress`);
      return false;
    }
    if (!this.uvBin) {
      this.setStatus("error");
      return false;
    }
    this.syncing = true;
    try {
      let extraEnv;
      if (!utils.is.dev) {
        log(`[venv] sync: copying project files...`);
        this.copyProjectFiles();
        const cacheDir = path.join(electron.app.getPath("userData"), "uv-cache");
        log(`[venv] sync: extracting cache to ${cacheDir}`);
        try {
          await this.extractCacheIfNeeded(cacheDir);
          log(`[venv] sync: cache extraction done`);
        } catch (err) {
          log(`[venv] sync: cache extraction failed: ${err}`);
        }
        extraEnv = { UV_CACHE_DIR: cacheDir, UV_OFFLINE: "1" };
      }
      const args = [this.uvBin, "sync"];
      if (!utils.is.dev) {
        const bundledPython = this.bundledPythonBin;
        if (bundledPython) args.push("--python", bundledPython);
        args.push("--no-install-project");
      }
      if (extra) args.push("--extra", extra);
      log(`[venv] sync: spawning ${args.join(" ")}`);
      const ok = await this.runUvCommand(args, extraEnv, { suppressReady: !utils.is.dev });
      log(`[venv] sync() result=${ok}`);
      if (ok && !utils.is.dev) {
        const serverSrc = path.join(process.resourcesPath, "server");
        const installArgs = [this.uvBin, "pip", "install", "--no-deps", serverSrc];
        log(`[venv] installing project from ${serverSrc}`);
        const installOk = await this.runUvCommand(installArgs, void 0, { suppressReady: true });
        log(`[venv] project install result=${installOk}`);
        if (!installOk) return false;
        const gatewayOk = await this.syncGatewayProject(extraEnv);
        log(`[venv] gateway project sync result=${gatewayOk}`);
        if (!gatewayOk) return false;
        this.writeVersionStamp();
        this.setStatus("ready");
      }
      return ok;
    } finally {
      this.syncing = false;
    }
  }
  async listPackages() {
    if (!this.uvBin) return [];
    try {
      const output = child_process.execFileSync(this.uvBin, ["pip", "list", "--format", "json"], {
        cwd: this.projectDir,
        encoding: "utf-8",
        env: { ...process.env, VIRTUAL_ENV: this.venvDir }
      });
      return JSON.parse(output);
    } catch {
      return [];
    }
  }
  async discoverPlugins() {
    const sfBin = path.join(this.venvDir, "bin", "sf");
    if (!fs.existsSync(sfBin)) return {};
    return new Promise((resolve) => {
      child_process.execFile(
        sfBin,
        ["plugin", "list", "--json"],
        {
          cwd: this.projectDir,
          encoding: "utf-8",
          timeout: 1e4,
          env: { ...process.env, VIRTUAL_ENV: this.venvDir }
        },
        (error, stdout) => {
          if (error) {
            resolve({});
            return;
          }
          try {
            resolve(JSON.parse(stdout));
          } catch {
            resolve({});
          }
        }
      );
    });
  }
  runUvCommand(args, extraEnv, opts) {
    return new Promise((resolve) => {
      const [cmd, ...rest] = args;
      const env = {
        ...process.env,
        VIRTUAL_ENV: opts?.venvDir ?? this.venvDir,
        ...extraEnv
      };
      const child = child_process.spawn(cmd, rest, {
        cwd: opts?.cwd ?? this.projectDir,
        env
      });
      child.stdout.on("data", (data) => {
        this.emit("progress", data.toString());
      });
      child.stderr.on("data", (data) => {
        this.emit("progress", data.toString());
      });
      child.on("close", (code) => {
        if (code === 0) {
          if (!opts?.suppressReady) this.setStatus("ready");
          resolve(true);
        } else {
          log(`[venv] command failed (${code}): ${cmd} ${rest.join(" ")}`);
          this.setStatus("error");
          resolve(false);
        }
      });
      child.on("error", (err) => {
        log(`[venv] command error: ${err.message}`);
        this.setStatus("error");
        resolve(false);
      });
    });
  }
  /** Copy pyproject.toml and uv.lock from the read-only bundle to writable userData. */
  copyProjectFiles() {
    const dest = electron.app.getPath("userData");
    for (const file of ["pyproject.toml", "uv.lock"]) {
      const src = path.join(process.resourcesPath, "server", file);
      const dst = path.join(dest, file);
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, dst);
      }
    }
  }
  async syncGatewayProject(extraEnv) {
    if (!this.uvBin) return false;
    this.copyGatewayProjectFiles();
    const syncArgs = [this.uvBin, "sync"];
    const bundledPython = this.bundledPythonBin;
    if (bundledPython) syncArgs.push("--python", bundledPython);
    syncArgs.push("--no-install-project");
    const syncOk = await this.runUvCommand(syncArgs, extraEnv, {
      suppressReady: true,
      cwd: this.gatewayProjectDir,
      venvDir: this.gatewayVenvDir
    });
    if (!syncOk) return false;
    return this.runUvCommand(
      [this.uvBin, "pip", "install", "--no-deps", this.gatewayProjectDir],
      void 0,
      {
        suppressReady: true,
        cwd: this.gatewayProjectDir,
        venvDir: this.gatewayVenvDir
      }
    );
  }
  copyGatewayProjectFiles() {
    fs.mkdirSync(this.gatewayProjectDir, { recursive: true });
    const srcRoot = path.join(process.resourcesPath, "aigateway");
    for (const file of ["pyproject.toml", "uv.lock"]) {
      const src2 = path.join(srcRoot, file);
      const dst2 = path.join(this.gatewayProjectDir, file);
      if (fs.existsSync(src2)) fs.copyFileSync(src2, dst2);
    }
    const src = path.join(srcRoot, "src");
    const dst = path.join(this.gatewayProjectDir, "src");
    if (fs.existsSync(src)) fs.cpSync(src, dst, { recursive: true, force: true });
  }
  extractCacheIfNeeded(cacheDir) {
    const completeSentinel = path.join(cacheDir, ".cache-complete");
    if (fs.existsSync(completeSentinel)) return Promise.resolve();
    const tarball = path.join(process.resourcesPath, "server", "cache.tar.gz");
    if (!fs.existsSync(tarball)) return Promise.resolve();
    if (fs.existsSync(cacheDir)) fs.rmSync(cacheDir, { recursive: true, force: true });
    return new Promise((resolve, reject) => {
      fs.mkdirSync(cacheDir, { recursive: true });
      this.emit("progress", "Extracting package cache...\n");
      const child = child_process.spawn("tar", ["xzf", tarball, "-C", cacheDir]);
      child.on("close", (code) => {
        if (code === 0) {
          fs.writeFileSync(completeSentinel, "ok\n", "utf-8");
          resolve();
        } else {
          reject(new Error(`tar exited ${code}`));
        }
      });
      child.on("error", reject);
    });
  }
  get versionStampPath() {
    return path.join(electron.app.getPath("userData"), ".sf-version");
  }
  writeVersionStamp() {
    try {
      fs.writeFileSync(this.versionStampPath, electron.app.getVersion(), "utf-8");
    } catch {
    }
  }
  needsResync() {
    if (utils.is.dev) return false;
    try {
      const stamp = fs.readFileSync(this.versionStampPath, "utf-8").trim();
      return stamp !== electron.app.getVersion();
    } catch {
      return true;
    }
  }
}
const venvManager = new VenvManager();
function registerVenvHandlers() {
  electron.ipcMain.handle("venv:detect", async (event) => {
    requireTrustedIpcSender(event);
    log(`[ipc] venv:detect received`);
    const result = await venvManager.detect();
    log(`[ipc] venv:detect returning ${JSON.stringify(result)}`);
    return result;
  });
  electron.ipcMain.handle("venv:create", async (event) => {
    requireTrustedIpcSender(event);
    log(`[ipc] venv:create received`);
    const result = await venvManager.create();
    log(`[ipc] venv:create returning ${result}`);
    return result;
  });
  electron.ipcMain.handle("venv:sync", async (event, extra) => {
    requireTrustedIpcSender(event);
    log(`[ipc] venv:sync received, extra=${extra}`);
    const result = await venvManager.sync(extra);
    log(`[ipc] venv:sync returning ${result}`);
    return result;
  });
  electron.ipcMain.handle("venv:listPackages", (event) => {
    requireTrustedIpcSender(event);
    return venvManager.listPackages();
  });
  venvManager.on("status", (status) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("venv:statusChanged", status);
    }
  });
  venvManager.on("progress", (line) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("venv:progress", line);
    }
  });
}
class PluginRegistryService extends events.EventEmitter {
  pluginsPath;
  constructor() {
    super();
    this.pluginsPath = "";
  }
  getPath() {
    if (!this.pluginsPath) {
      try {
        this.pluginsPath = path.join(electron.app.getPath("userData"), "plugins.json");
      } catch {
        this.pluginsPath = path.join(process.cwd(), "plugins.json");
      }
    }
    return this.pluginsPath;
  }
  readStore() {
    const p = this.getPath();
    if (!fs.existsSync(p)) return [];
    try {
      return JSON.parse(fs.readFileSync(p, "utf-8"));
    } catch {
      return [];
    }
  }
  writeStore(plugins) {
    fs.writeFileSync(this.getPath(), JSON.stringify(plugins, null, 2), "utf-8");
    this.emit("changed");
  }
  list() {
    return this.readStore();
  }
  async install(remoteEntryUrl) {
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
  uninstall(id) {
    const plugins = this.readStore().filter((p) => p.id !== id);
    this.writeStore(plugins);
  }
  activate(id) {
    const plugins = this.readStore();
    const plugin = plugins.find((p) => p.id === id);
    if (plugin) {
      plugin.active = true;
      this.writeStore(plugins);
    }
  }
  deactivate(id) {
    const plugins = this.readStore();
    const plugin = plugins.find((p) => p.id === id);
    if (plugin) {
      plugin.active = false;
      this.writeStore(plugins);
    }
  }
  getCatalog() {
    return [];
  }
  async fetchRemoteEntry(url2) {
    const response = await electron.net.fetch(url2);
    if (!response.ok) {
      throw new Error(`Failed to fetch remote entry: ${response.status}`);
    }
    const data = await response.json();
    if (!data.id || !data.name || !data.version || !data.exposedModule) {
      throw new Error("Invalid remote entry: missing required fields (id, name, version, exposedModule)");
    }
    return {
      id: data.id,
      name: data.name,
      version: data.version,
      remoteEntryUrl: url2,
      exposedModule: data.exposedModule,
      description: data.description || "",
      iconUrl: data.iconUrl || "",
      active: true
    };
  }
}
const pluginRegistry = new PluginRegistryService();
function registerPluginHandlers() {
  electron.ipcMain.handle("plugins:list", (event) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.list();
  });
  electron.ipcMain.handle("plugins:discover", (event) => {
    requireTrustedIpcSender(event);
    return venvManager.discoverPlugins();
  });
  electron.ipcMain.handle("plugins:install", (event, url2) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.install(url2);
  });
  electron.ipcMain.handle("plugins:uninstall", (event, id) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.uninstall(id);
  });
  electron.ipcMain.handle("plugins:activate", (event, id) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.activate(id);
  });
  electron.ipcMain.handle("plugins:deactivate", (event, id) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.deactivate(id);
  });
  electron.ipcMain.handle("plugins:getCatalog", (event) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.getCatalog();
  });
  pluginRegistry.on("changed", () => {
    const plugins = pluginRegistry.list();
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("plugins:changed", plugins);
    }
  });
}
function registerConfigHandlers() {
  electron.ipcMain.handle("config:read", (event) => {
    requireTrustedIpcSender(event);
    return configService.read();
  });
  electron.ipcMain.handle("config:write", (event, config) => {
    requireTrustedIpcSender(event);
    configService.write(config);
  });
  configService.on("changed", (config) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("config:changed", config);
    }
  });
  configService.watch();
}
const PORT_RANGE_START = 9101;
const PORT_RANGE_SIZE = 100;
const PROXY_READY_TIMEOUT_MS = 15e3;
function frontendPluginNameForSession(type) {
  switch (type) {
    case "codex":
      return "codex-frontend";
    case "gemini":
      return "gemini-frontend";
    case "claude":
    case "claude-desktop":
      return "claude-frontend";
    default:
      return "claude-frontend";
  }
}
class SessionManager extends events.EventEmitter {
  sessions = /* @__PURE__ */ new Map();
  get sfBin() {
    if (!utils.is.dev) {
      return path.join(electron.app.getPath("userData"), ".venv", "bin", "sf");
    }
    return path.join(configService.serverDir, ".venv", "bin", "sf");
  }
  get serverCwd() {
    if (!utils.is.dev) {
      return electron.app.getPath("userData");
    }
    return configService.serverDir;
  }
  // --- Port allocation ---
  usedPorts() {
    const ports = /* @__PURE__ */ new Set();
    for (const s of this.sessions.values()) {
      ports.add(s.port);
    }
    return ports;
  }
  async isPortFree(port) {
    return new Promise((resolve) => {
      const sock = new net.Socket();
      sock.once("connect", () => {
        sock.destroy();
        resolve(false);
      });
      sock.once("error", () => {
        sock.destroy();
        resolve(true);
      });
      sock.connect(port, "127.0.0.1");
    });
  }
  async allocatePort() {
    const used = this.usedPorts();
    for (let i = 0; i < PORT_RANGE_SIZE; i++) {
      const candidate = PORT_RANGE_START + i;
      if (used.has(candidate)) continue;
      if (await this.isPortFree(candidate)) return candidate;
    }
    throw new Error("No free ports available in session range");
  }
  /** Find a random free port by binding to port 0 and reading the assigned port. */
  async allocateRandomPort() {
    return new Promise((resolve, reject) => {
      const srv = net.createServer();
      srv.listen(0, "127.0.0.1", () => {
        const addr = srv.address();
        if (addr && typeof addr === "object") {
          const port = addr.port;
          srv.close(() => resolve(port));
        } else {
          srv.close(() => reject(new Error("Failed to allocate random port")));
        }
      });
      srv.on("error", reject);
    });
  }
  // --- Folder picker ---
  async pickWorkingDir() {
    const win = electron.BrowserWindow.getFocusedWindow();
    if (!win) return null;
    const result = await electron.dialog.showOpenDialog(win, {
      title: "Choose working directory for Claude session",
      properties: ["openDirectory"],
      defaultPath: electron.app.getPath("home")
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
  }
  // --- Session lifecycle ---
  async createSession(type, workingDir, pluginConfig) {
    const id = crypto.randomUUID();
    const port = await this.allocatePort();
    if (!fs.existsSync(workingDir)) {
      fs.mkdirSync(workingDir, { recursive: true });
    }
    const session = {
      id,
      type,
      port,
      status: "starting",
      createdAt: /* @__PURE__ */ new Date(),
      workingDir,
      pluginConfig: pluginConfig || {},
      proxy: null,
      proxyReady: null,
      scriptPath: null
    };
    this.sessions.set(id, session);
    this.emitSessionsChanged();
    try {
      await this.spawnProxy(session, pluginConfig);
      this.openTerminal(session);
      session.status = "running";
      this.emitSessionsChanged();
    } catch (err) {
      session.status = "error";
      this.emitSessionsChanged();
      throw err;
    }
    return this.toSessionInfo(session);
  }
  async spawnProxy(session, pluginConfig) {
    const serverPort = await this.allocateRandomPort();
    const config = configService.read();
    const defaults = config.plugin_config || {};
    const frontendPlugin = frontendPluginNameForSession(session.type);
    const proxyConfig = {
      version: config.version || "0.1.0",
      server: {
        host: "127.0.0.1",
        port: serverPort,
        reload: false,
        ssl: false
      },
      plugins: ["tracing", frontendPlugin, "url4-specs"],
      plugin_config: {
        tracing: {
          ...defaults["tracing"] || {},
          phoenix_launch: false
          // connect to shared Phoenix, don't spawn per-session
        },
        [frontendPlugin]: {
          ...defaults[frontendPlugin] || {},
          // User overrides from dialog:
          ...pluginConfig?.[frontendPlugin] || {},
          // Forced by session-manager (cannot be overridden):
          listen_host: "127.0.0.1",
          listen_port: session.port,
          session_service_url: "http://127.0.0.1:9200",
          // All url4/data/backend calls go to the main SF server.
          // Use the LIVE URL from backend-status service (the port SF is
          // actually listening on) rather than the static sf.json port.
          // sf.json's port may be stale if SF auto-incremented because the
          // configured port was busy (e.g. another local dev process held
          // it), and a stale backend_url makes /data 404 when the proxy
          // tries to store $prompt blobs.
          backend_url: backendStatusService.getServerUrl() ?? `${config.server.ssl ? "https" : "http"}://127.0.0.1:${config.server.port || 8e3}`
        },
        "url4-specs": defaults["url4-specs"] || {}
      }
    };
    const args = [
      "run",
      "--subprocess",
      "--session-id",
      session.id,
      "--config-json",
      JSON.stringify(proxyConfig)
    ];
    return new Promise((resolve, reject) => {
      const child = child_process.spawn(this.sfBin, args, {
        cwd: this.serverCwd,
        env: { ...process.env },
        stdio: ["ignore", "pipe", "pipe"]
      });
      session.proxy = child;
      let settled = false;
      let timeout;
      let onClose;
      let onError;
      let onStderr;
      let onStdout;
      const cleanupStartupFailure = () => {
        clearTimeout(timeout);
        child.stdout?.removeListener("data", onStdout);
        child.stderr?.removeListener("data", onStderr);
        child.removeListener("close", onClose);
        child.removeListener("error", onError);
        session.proxyReady = null;
        if (session.proxy === child) {
          session.proxy = null;
        }
        try {
          child.kill("SIGTERM");
        } catch {
        }
        const forceKillTimer = setTimeout(() => {
          try {
            child.kill("SIGKILL");
          } catch {
          }
        }, 5e3);
        child.once("close", () => clearTimeout(forceKillTimer));
      };
      onStdout = (data) => {
        const lines = data.toString().split("\n").filter(Boolean);
        for (const line of lines) {
          try {
            const parsed = JSON.parse(line);
            if (parsed.event === "ready") {
              if (settled) return;
              settled = true;
              clearTimeout(timeout);
              session.proxyReady = parsed;
              resolve();
              return;
            }
          } catch {
          }
          this.emit("log", session.id, line);
        }
      };
      onStderr = (data) => {
        this.emit("log", session.id, data.toString());
      };
      onClose = (code, signal) => {
        clearTimeout(timeout);
        this.emit("log", session.id, `Proxy process exited (code=${code}, signal=${signal})`);
        if (!settled) {
          settled = true;
          session.proxy = null;
          session.proxyReady = null;
          reject(new Error("Proxy exited before ready"));
          return;
        }
        if (session.status !== "stopping" && session.status !== "stopped") {
          session.status = "error";
          session.proxy = null;
          this.emitSessionsChanged();
        }
      };
      onError = (err) => {
        clearTimeout(timeout);
        session.proxy = null;
        session.proxyReady = null;
        session.status = "error";
        this.emitSessionsChanged();
        if (settled) return;
        settled = true;
        reject(err);
      };
      timeout = setTimeout(() => {
        if (settled) return;
        settled = true;
        cleanupStartupFailure();
        reject(new Error("Proxy ready timeout"));
      }, PROXY_READY_TIMEOUT_MS);
      child.stdout.on("data", onStdout);
      child.stderr.on("data", onStderr);
      child.on("close", onClose);
      child.on("error", onError);
    });
  }
  cliCommand(type) {
    switch (type) {
      case "claude":
        return "claude";
      case "codex":
        return "codex";
      case "gemini":
        return "gemini";
      case "claude-desktop":
        return "claude";
      default:
        return "claude";
    }
  }
  envVarName(type) {
    switch (type) {
      case "claude":
      case "claude-desktop":
        return "ANTHROPIC_BASE_URL";
      case "codex":
        return "OPENAI_BASE_URL";
      case "gemini":
        return "GEMINI_BASE_URL";
      default:
        return "ANTHROPIC_BASE_URL";
    }
  }
  openTerminal(session) {
    const baseUrl = `http://127.0.0.1:${session.port}`;
    const cmd = this.cliCommand(session.type);
    const envVar = this.envVarName(session.type);
    const scriptPath = path.join(os.tmpdir(), `sf-session-${session.id}.sh`);
    const pidPath = path.join(os.tmpdir(), `sf-session-${session.id}.pid`);
    const scriptContent = [
      "#!/bin/bash",
      `echo $$ > ${this.shellEscape(pidPath)}`,
      `cd ${this.shellEscape(session.workingDir)}`,
      `export ${envVar}=${this.shellEscape(baseUrl)}`,
      `exec ${cmd}`
    ].join("\n");
    fs.writeFileSync(scriptPath, scriptContent, "utf-8");
    fs.chmodSync(scriptPath, 493);
    session.scriptPath = scriptPath;
    const escapedPath = scriptPath.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const appleScript = `tell application "Terminal"
  activate
  do script "${escapedPath}"
end tell`;
    this.emit("log", session.id, `Opening terminal: ${scriptPath}`);
    child_process.execFile("osascript", ["-e", appleScript], (err, _stdout, stderr) => {
      if (err) {
        this.emit("log", session.id, `ERROR: Failed to open terminal: ${err.message}`);
        if (stderr) this.emit("log", session.id, `osascript stderr: ${stderr}`);
        session.status = "error";
        this.emitSessionsChanged();
      }
    });
  }
  shellEscape(s) {
    return `'${s.replace(/'/g, "'\\''")}'`;
  }
  /**
   * Kill the CLI process via its PID file, then close the Terminal window.
   */
  async killTerminalProcess(session) {
    const pidPath = path.join(os.tmpdir(), `sf-session-${session.id}.pid`);
    if (fs.existsSync(pidPath)) {
      try {
        const pid = parseInt(fs.readFileSync(pidPath, "utf-8").trim(), 10);
        if (!isNaN(pid)) {
          this.emit("log", session.id, `Killing CLI process (PID ${pid})`);
          try {
            process.kill(pid, "SIGTERM");
          } catch {
          }
          await new Promise((r) => setTimeout(r, 2e3));
          try {
            process.kill(pid, "SIGKILL");
          } catch {
          }
        }
      } catch {
      }
      try {
        fs.unlinkSync(pidPath);
      } catch {
      }
    } else {
      this.emit("log", session.id, "No PID file found — CLI may need manual close");
    }
    await new Promise((resolve) => {
      const closeScript = `tell application "Terminal"
  set windowsToClose to {}
  repeat with w in (every window)
    set allDone to true
    repeat with t in (every tab of w)
      if busy of t is true then
        set allDone to false
        exit repeat
      end if
    end repeat
    if allDone then set end of windowsToClose to w
  end repeat
  repeat with w in windowsToClose
    close w
  end repeat
end tell`;
      child_process.execFile("osascript", ["-e", closeScript], () => resolve());
    });
    if (session.scriptPath) {
      try {
        fs.unlinkSync(session.scriptPath);
      } catch {
      }
      session.scriptPath = null;
    }
  }
  async terminateSession(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    session.status = "stopping";
    this.emitSessionsChanged();
    await this.killTerminalProcess(session);
    if (session.proxy) {
      session.proxy.kill("SIGTERM");
      await new Promise((resolve) => {
        const timer = setTimeout(() => {
          try {
            session.proxy?.kill("SIGKILL");
          } catch {
          }
          resolve();
        }, 5e3);
        session.proxy.once("close", () => {
          clearTimeout(timer);
          resolve();
        });
      });
      session.proxy = null;
    }
    session.status = "stopped";
    this.emitSessionsChanged();
  }
  async terminateAll() {
    const ids = [...this.sessions.keys()];
    await Promise.all(ids.map((id) => this.terminateSession(id)));
  }
  listSessions() {
    return [...this.sessions.values()].map((s) => this.toSessionInfo(s));
  }
  removeSession(id) {
    this.sessions.delete(id);
    this.emitSessionsChanged();
  }
  updateSession(id, workingDir, pluginConfig) {
    const session = this.sessions.get(id);
    if (!session) throw new Error(`Session ${id} not found`);
    if (session.status !== "stopped" && session.status !== "error") {
      throw new Error("Can only edit stopped or error sessions");
    }
    session.workingDir = workingDir;
    session.pluginConfig = pluginConfig || {};
    if (!fs.existsSync(workingDir)) {
      fs.mkdirSync(workingDir, { recursive: true });
    }
    this.emitSessionsChanged();
    return this.toSessionInfo(session);
  }
  async restartSession(id) {
    const session = this.sessions.get(id);
    if (!session) throw new Error(`Session ${id} not found`);
    if (session.status !== "stopped" && session.status !== "error") {
      throw new Error("Can only restart stopped or error sessions");
    }
    session.port = await this.allocatePort();
    session.status = "starting";
    session.createdAt = /* @__PURE__ */ new Date();
    this.emitSessionsChanged();
    try {
      await this.spawnProxy(session, session.pluginConfig);
      this.openTerminal(session);
      session.status = "running";
      this.emitSessionsChanged();
    } catch (err) {
      session.status = "error";
      this.emitSessionsChanged();
      throw err;
    }
    return this.toSessionInfo(session);
  }
  toSessionInfo(s) {
    return {
      id: s.id,
      type: s.type,
      port: s.port,
      status: s.status,
      createdAt: s.createdAt.toISOString(),
      workingDir: s.workingDir,
      pluginConfig: s.pluginConfig
    };
  }
  emitSessionsChanged() {
    this.emit("sessionsChanged", this.listSessions());
  }
}
const sessionManager = new SessionManager();
function registerSessionHandlers() {
  electron.ipcMain.handle("session:pickDir", (event) => {
    requireTrustedIpcSender(event);
    return sessionManager.pickWorkingDir();
  });
  electron.ipcMain.handle(
    "session:create",
    (event, type, workingDir, pluginConfig) => {
      requireTrustedIpcSender(event);
      return sessionManager.createSession(type, workingDir, pluginConfig);
    }
  );
  electron.ipcMain.handle("session:list", (event) => {
    requireTrustedIpcSender(event);
    return sessionManager.listSessions();
  });
  electron.ipcMain.handle("session:terminate", (event, id) => {
    requireTrustedIpcSender(event);
    return sessionManager.terminateSession(id);
  });
  electron.ipcMain.handle("session:terminateAll", (event) => {
    requireTrustedIpcSender(event);
    return sessionManager.terminateAll();
  });
  electron.ipcMain.handle("session:remove", (event, id) => {
    requireTrustedIpcSender(event);
    sessionManager.removeSession(id);
  });
  electron.ipcMain.handle(
    "session:update",
    (event, id, workingDir, pluginConfig) => {
      requireTrustedIpcSender(event);
      return sessionManager.updateSession(id, workingDir, pluginConfig);
    }
  );
  electron.ipcMain.handle("session:restart", (event, id) => {
    requireTrustedIpcSender(event);
    return sessionManager.restartSession(id);
  });
  sessionManager.on("sessionsChanged", (sessions) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("session:sessionsChanged", sessions);
    }
  });
  sessionManager.on("log", (id, line) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("session:log", id, line);
    }
  });
}
const pendingStateByBackendProfile = /* @__PURE__ */ new Map();
const pendingStateByBackendConnection = /* @__PURE__ */ new Map();
const activeLaunchesByBackendProfile = /* @__PURE__ */ new Set();
function pendingAuthKey(backendName, profileName) {
  return `${backendName}\0${profileName ?? ""}`;
}
function pendingConnectionAuthKey(backendName, connectionId) {
  return `${backendName}\0connection\0${connectionId}`;
}
function hasPendingProfileLaunch(authKey) {
  return activeLaunchesByBackendProfile.has(authKey) || pendingStateByBackendProfile.has(authKey);
}
function getPendingAuthState(backendName, profileName) {
  return pendingStateByBackendProfile.get(pendingAuthKey(backendName, profileName)) ?? null;
}
function clearPendingAuthState(backendName, profileName) {
  pendingStateByBackendProfile.delete(pendingAuthKey(backendName, profileName));
}
function getPendingConnectionAuthState(backendName, connectionId) {
  if (!connectionId) return null;
  return pendingStateByBackendConnection.get(pendingConnectionAuthKey(backendName, connectionId)) ?? null;
}
function clearPendingConnectionAuthState(backendName, connectionId) {
  pendingStateByBackendConnection.delete(pendingConnectionAuthKey(backendName, connectionId));
}
function clearPendingOAuthStates() {
  pendingStateByBackendProfile.clear();
  pendingStateByBackendConnection.clear();
  activeLaunchesByBackendProfile.clear();
}
async function runOAuthLauncher(opts) {
  if (!isSafeBackendName(opts.backendName)) {
    return {
      kind: "failed",
      reason: "gateway_error",
      message: `invalid browser OAuth backend: ${opts.backendName}`
    };
  }
  const fetchImpl = opts.fetchImpl ?? fetch;
  const pollIntervalMs = opts.pollIntervalMs ?? 2e3;
  const timeoutMs = opts.timeoutMs ?? 10 * 60 * 1e3;
  const query = opts.profileName ? `?name=${encodeURIComponent(opts.profileName)}` : "";
  const startUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/start${query}`;
  const statusUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/status${query}`;
  if (opts.abortSignal?.aborted) return cancelledResult();
  const authKey = pendingAuthKey(opts.backendName, opts.profileName);
  if (hasPendingProfileLaunch(authKey)) {
    return {
      kind: "failed",
      reason: "gateway_error",
      message: "OAuth launch already pending for this backend/profile"
    };
  }
  activeLaunchesByBackendProfile.add(authKey);
  try {
    console.log(`[oauth-launcher] POST ${startUrl}`);
    let startResp;
    try {
      startResp = await fetchImpl(startUrl, {
        method: "POST",
        headers: opts.headers,
        ...abortFetchInit(opts.abortSignal)
      });
    } catch (e) {
      if (isAbortError(e, opts.abortSignal)) return cancelledResult();
      console.log(`[oauth-launcher] start fetch threw:`, e);
      return { kind: "failed", reason: "network_error", message: String(e) };
    }
    console.log(`[oauth-launcher] start status=${startResp.status}`);
    if (!startResp.ok) {
      let body = "";
      try {
        body = await startResp.text();
      } catch {
      }
      console.log(`[oauth-launcher] start body=${body.slice(0, 500)}`);
      return {
        kind: "failed",
        reason: "gateway_error",
        message: `start returned ${startResp.status}: ${body.slice(0, 200)}`
      };
    }
    const startBody = await startResp.json();
    if (!startBody.authorize_url || !isAllowedOAuthAuthorizeUrl(startBody.authorize_url, {
      allowedRedirectPorts: opts.allowedOAuthRedirectPorts
    })) {
      return {
        kind: "failed",
        reason: "gateway_error",
        message: "blocked unexpected OAuth authorize URL"
      };
    }
    if (startBody.state) {
      pendingStateByBackendProfile.set(authKey, startBody.state);
    }
    if (opts.abortSignal?.aborted) return cancelledResult();
    console.log(`[oauth-launcher] opening browser for ${opts.backendName}`);
    await electron.shell.openExternal(startBody.authorize_url);
    return await pollProfileOAuthStatus({
      backendName: opts.backendName,
      profileName: opts.profileName,
      headers: opts.headers,
      abortSignal: opts.abortSignal,
      statusUrl,
      fetchImpl,
      pollIntervalMs,
      timeoutMs
    });
  } finally {
    activeLaunchesByBackendProfile.delete(authKey);
  }
}
async function pollProfileOAuthStatus(opts) {
  const deadline = Date.now() + opts.timeoutMs;
  let networkBlips = 0;
  while (Date.now() < deadline) {
    let statusResp;
    try {
      statusResp = await opts.fetchImpl(opts.statusUrl, {
        headers: opts.headers,
        ...abortFetchInit(opts.abortSignal)
      });
    } catch (e) {
      if (isAbortError(e, opts.abortSignal)) return cancelledResult();
      networkBlips += 1;
      if (networkBlips >= 5) {
        return { kind: "failed", reason: "network_error" };
      }
      if (await sleep$1(opts.pollIntervalMs, opts.abortSignal) === "aborted") {
        return cancelledResult();
      }
      continue;
    }
    networkBlips = 0;
    if (statusResp.status === 404) {
      return { kind: "failed", reason: "gateway_error", message: "profile not found" };
    }
    if (!statusResp.ok) {
      return {
        kind: "failed",
        reason: "gateway_error",
        message: `status returned ${statusResp.status}`
      };
    }
    const body = await statusResp.json();
    if (body.state === "authenticated") {
      clearPendingAuthState(opts.backendName, opts.profileName);
      return { kind: "complete" };
    }
    if (body.state === "error") {
      return { kind: "failed", reason: "provider_error", message: body.error };
    }
    if (await sleep$1(opts.pollIntervalMs, opts.abortSignal) === "aborted")
      return cancelledResult();
  }
  return { kind: "failed", reason: "timeout" };
}
async function runOAuthConnectionLauncher(opts) {
  if (!isSafeBackendName(opts.backendName)) {
    return {
      kind: "failed",
      reason: "gateway_error",
      message: `invalid browser OAuth backend: ${opts.backendName}`
    };
  }
  const fetchImpl = opts.fetchImpl ?? fetch;
  const pollIntervalMs = opts.pollIntervalMs ?? 2e3;
  const timeoutMs = opts.timeoutMs ?? 10 * 60 * 1e3;
  const startUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/connections`;
  if (opts.abortSignal?.aborted) return cancelledResult();
  let startResp;
  try {
    startResp = await fetchImpl(startUrl, {
      method: "POST",
      headers: { ...opts.headers, "content-type": "application/json" },
      body: JSON.stringify(opts.label ? { label: opts.label } : {}),
      ...abortFetchInit(opts.abortSignal)
    });
  } catch (e) {
    if (isAbortError(e, opts.abortSignal)) return cancelledResult();
    return { kind: "failed", reason: "network_error", message: String(e) };
  }
  if (!startResp.ok) {
    return {
      kind: "failed",
      reason: "gateway_error",
      message: `start returned ${startResp.status}: ${(await safeText(startResp)).slice(0, 200)}`
    };
  }
  const startBody = await startResp.json();
  if (!startBody.connection_id || !isSafeOAuthConnectionId(startBody.connection_id)) {
    return { kind: "failed", reason: "gateway_error", message: "invalid connection id" };
  }
  if (!startBody.authorize_url || !isAllowedOAuthAuthorizeUrl(startBody.authorize_url, {
    allowedRedirectPorts: opts.allowedOAuthRedirectPorts
  })) {
    return {
      kind: "failed",
      reason: "gateway_error",
      message: "blocked unexpected OAuth authorize URL"
    };
  }
  if (startBody.state) {
    pendingStateByBackendConnection.set(
      pendingConnectionAuthKey(opts.backendName, startBody.connection_id),
      startBody.state
    );
  }
  if (opts.abortSignal?.aborted) return cancelledResult();
  await electron.shell.openExternal(startBody.authorize_url);
  const statusUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/connections/${encodeURIComponent(startBody.connection_id)}`;
  const deadline = Date.now() + timeoutMs;
  let networkBlips = 0;
  while (Date.now() < deadline) {
    let statusResp;
    try {
      statusResp = await fetchImpl(statusUrl, {
        headers: opts.headers,
        ...abortFetchInit(opts.abortSignal)
      });
    } catch (e) {
      if (isAbortError(e, opts.abortSignal)) return cancelledResult();
      networkBlips += 1;
      if (networkBlips >= 5) {
        return { kind: "failed", reason: "network_error" };
      }
      if (await sleep$1(pollIntervalMs, opts.abortSignal) === "aborted") return cancelledResult();
      continue;
    }
    networkBlips = 0;
    if (statusResp.status === 404) {
      return { kind: "failed", reason: "gateway_error", message: "connection not found" };
    }
    if (!statusResp.ok) {
      return {
        kind: "failed",
        reason: "gateway_error",
        message: `status returned ${statusResp.status}`
      };
    }
    const body = await statusResp.json();
    if (body.status === "active") {
      clearPendingConnectionAuthState(opts.backendName, startBody.connection_id);
      return { kind: "complete", connection: body, isDuplicate: body.is_duplicate === true };
    }
    if (body.status === "error" || body.status === "revoked" || body.status === "expired") {
      return {
        kind: "failed",
        reason: "provider_error",
        message: body.error_message ?? `connection ${body.status}`
      };
    }
    if (await sleep$1(pollIntervalMs, opts.abortSignal) === "aborted") return cancelledResult();
  }
  return { kind: "failed", reason: "timeout" };
}
function cancelledResult() {
  return { kind: "failed", reason: "cancelled" };
}
function isAbortError(error, signal) {
  return signal?.aborted === true || error instanceof DOMException && error.name === "AbortError";
}
function abortFetchInit(signal) {
  return signal ? { signal } : {};
}
async function safeText(resp) {
  try {
    return await resp.text();
  } catch {
    return "";
  }
}
function sleep$1(ms, signal) {
  if (signal?.aborted) return Promise.resolve("aborted");
  return new Promise((resolve) => {
    let timer;
    const onAbort = () => {
      if (timer) clearTimeout(timer);
      resolve("aborted");
    };
    timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve("completed");
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
let oauthLauncherAbortController = new AbortController();
function currentOAuthLauncherSignal() {
  if (oauthLauncherAbortController.signal.aborted) {
    oauthLauncherAbortController = new AbortController();
  }
  return oauthLauncherAbortController.signal;
}
function abortOAuthLaunchers() {
  oauthLauncherAbortController.abort();
  oauthLauncherAbortController = new AbortController();
}
function registerBackendStatusHandlers() {
  electron.ipcMain.handle("backends:getStatus", (event) => {
    requireTrustedIpcSender(event);
    return backendStatusService.getStatus();
  });
  electron.ipcMain.handle("backends:getPollingError", (event) => {
    requireTrustedIpcSender(event);
    return backendStatusService.getPollingError();
  });
  electron.ipcMain.handle("backends:refresh", (event) => {
    requireTrustedIpcSender(event);
    return backendStatusService.refresh();
  });
  electron.ipcMain.handle("backends:authenticate", (event, backend) => {
    requireTrustedIpcSender(event);
    backendStatusService.authenticate(backend);
  });
  electron.ipcMain.handle("backends:loginGateway", async (event, username, password) => {
    requireTrustedIpcSender(event);
    return backendStatusService.loginGateway(username, password);
  });
  electron.ipcMain.handle("backends:logoutGateway", async (event) => {
    requireTrustedIpcSender(event);
    abortOAuthLaunchers();
    clearPendingOAuthStates();
    return backendStatusService.logoutGateway();
  });
  electron.ipcMain.handle(
    "backends:authenticateOAuth",
    async (event, backend, profileName) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { kind: "failed", reason: "gateway_error", message: "invalid backend name" };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      console.log(
        `[oauth] authenticateOAuth invoked: backend=${backend} profileName=${profileName ?? "(default)"} sfBaseUrl=${sfBaseUrl ?? "NULL"}`
      );
      if (!sfBaseUrl) {
        return {
          kind: "failed",
          reason: "gateway_error",
          message: "SF server is not running"
        };
      }
      const result = await runOAuthLauncher({
        sfBaseUrl,
        backendName: backend,
        profileName,
        headers: desktopSecretHeader(),
        allowedOAuthRedirectPorts: currentGatewayRedirectPorts(),
        abortSignal: currentOAuthLauncherSignal()
      });
      console.log(`[oauth] launcher result:`, result);
      return result;
    }
  );
  electron.ipcMain.handle(
    "backends:authenticateOAuthConnection",
    async (event, backend, label) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { kind: "failed", reason: "gateway_error", message: "invalid backend name" };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return {
          kind: "failed",
          reason: "gateway_error",
          message: "SF server is not running"
        };
      }
      return await runOAuthConnectionLauncher({
        sfBaseUrl,
        backendName: backend,
        label,
        headers: desktopSecretHeader(),
        allowedOAuthRedirectPorts: currentGatewayRedirectPorts(),
        abortSignal: currentOAuthLauncherSignal()
      });
    }
  );
  electron.ipcMain.handle(
    "backends:getPendingAuthState",
    (event, backend, profileName) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) return null;
      return getPendingAuthState(backend, profileName);
    }
  );
  electron.ipcMain.handle(
    "backends:getPendingConnectionAuthState",
    (event, backend, connectionId) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend) || !connectionId || !isSafeOAuthConnectionId(connectionId)) {
        return null;
      }
      return getPendingConnectionAuthState(backend, connectionId);
    }
  );
  electron.ipcMain.handle(
    "backends:exchangeOAuthCode",
    async (event, backend, code, profileName) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, message: `invalid backend name: ${backend}` };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, message: "SF server is not running" };
      }
      const state = getPendingAuthState(backend, profileName);
      if (!state) {
        return { ok: false, message: "No in-flight OAuth flow for this backend/profile" };
      }
      try {
        const resp = await fetch(`${sfBaseUrl}/${backend}/auth/exchange-code`, {
          method: "POST",
          headers: { ...desktopSecretHeader(), "content-type": "application/json" },
          body: JSON.stringify({ code, state })
        });
        if (resp.ok) {
          clearPendingAuthState(backend, profileName);
          return { ok: true };
        }
        let message;
        try {
          const body = await resp.json();
          message = body.detail?.message ?? body.detail?.code;
        } catch {
        }
        return { ok: false, status: resp.status, message };
      } catch (e) {
        return { ok: false, message: e instanceof Error ? e.message : String(e) };
      }
    }
  );
  electron.ipcMain.handle(
    "backends:exchangeOAuthConnectionCode",
    async (event, backend, connectionId, code) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, message: `invalid backend name: ${backend}` };
      }
      if (!isSafeOAuthConnectionId(connectionId)) {
        return { ok: false, message: "invalid connection id" };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, message: "SF server is not running" };
      }
      const state = getPendingConnectionAuthState(backend, connectionId);
      if (!state) {
        return { ok: false, message: "No in-flight OAuth flow for this connection" };
      }
      try {
        const resp = await fetch(`${sfBaseUrl}/${backend}/auth/exchange-code`, {
          method: "POST",
          headers: { ...desktopSecretHeader(), "content-type": "application/json" },
          body: JSON.stringify({ code, state })
        });
        if (resp.ok) {
          clearPendingConnectionAuthState(backend, connectionId);
          return { ok: true };
        }
        return { ok: false, status: resp.status, message: await responseMessage(resp) };
      } catch (e) {
        return { ok: false, message: e instanceof Error ? e.message : String(e) };
      }
    }
  );
  electron.ipcMain.handle("backends:listProfiles", async (event, backend) => {
    requireTrustedIpcSender(event);
    if (!isSafeBackendName(backend)) {
      return { profiles: [], error: "invalid_backend" };
    }
    const sfBaseUrl = backendStatusService.getServerUrl();
    if (!sfBaseUrl) {
      return { profiles: [], error: "gateway_unreachable" };
    }
    try {
      const resp = await fetch(`${sfBaseUrl}/${backend}/auth/profiles`, {
        headers: desktopSecretHeader()
      });
      if (!resp.ok) {
        return { profiles: [], error: "gateway_unreachable" };
      }
      const body = await resp.json();
      return { profiles: body.profiles ?? [] };
    } catch {
      return { profiles: [], error: "gateway_unreachable" };
    }
  });
  electron.ipcMain.handle("backends:listConnections", async (event, backend) => {
    requireTrustedIpcSender(event);
    if (!isSafeBackendName(backend)) {
      return { connections: [], error: "invalid_backend" };
    }
    const sfBaseUrl = backendStatusService.getServerUrl();
    if (!sfBaseUrl) {
      return { connections: [], error: "gateway_unreachable" };
    }
    try {
      const resp = await fetch(`${sfBaseUrl}/${backend}/auth/connections`, {
        headers: desktopSecretHeader()
      });
      if (!resp.ok) {
        return { connections: [], error: "gateway_unreachable" };
      }
      const body = await resp.json();
      return { connections: body.connections ?? [] };
    } catch {
      return { connections: [], error: "gateway_unreachable" };
    }
  });
  electron.ipcMain.handle("backends:deleteProfile", async (event, backend, profileName) => {
    requireTrustedIpcSender(event);
    if (!isSafeBackendName(backend)) {
      return { ok: false, status: 400 };
    }
    const sfBaseUrl = backendStatusService.getServerUrl();
    if (!sfBaseUrl) {
      return { ok: false, status: 0 };
    }
    try {
      const resp = await fetch(
        `${sfBaseUrl}/${backend}/auth/profiles/${encodeURIComponent(profileName)}`,
        { method: "DELETE", headers: desktopSecretHeader() }
      );
      if (resp.status === 204) return { ok: true };
      return { ok: false, status: resp.status };
    } catch {
      return { ok: false, status: 0 };
    }
  });
  electron.ipcMain.handle(
    "backends:setProfileApiKey",
    async (event, backend, profileName, apiKey) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, status: 400, message: "invalid backend name" };
      }
      if (typeof apiKey !== "string" || apiKey.trim().length < 8) {
        return { ok: false, status: 400, message: "API key is missing or too short" };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0, message: "SF server is not running" };
      }
      try {
        const resp = await fetch(
          `${sfBaseUrl}/${backend}/auth/profiles/${encodeURIComponent(profileName)}/api-key`,
          {
            method: "PUT",
            headers: { ...desktopSecretHeader(), "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey.trim() })
          }
        );
        if (resp.ok) return { ok: true };
        let message;
        try {
          const body = await resp.json();
          message = body.detail?.message ?? body.detail?.code;
        } catch {
        }
        return { ok: false, status: resp.status, message };
      } catch {
        return { ok: false, status: 0, message: "gateway unreachable" };
      }
    }
  );
  electron.ipcMain.handle(
    "backends:createConnectionApiKey",
    async (event, backend, label, apiKey) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, status: 400, message: "invalid backend name" };
      }
      if (typeof apiKey !== "string" || apiKey.trim().length < 8) {
        return { ok: false, status: 400, message: "API key is missing or too short" };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0, message: "SF server is not running" };
      }
      try {
        const body = { api_key: apiKey.trim() };
        const trimmedLabel = label?.trim();
        if (trimmedLabel) body.label = trimmedLabel;
        const resp = await fetch(`${sfBaseUrl}/${backend}/auth/connections/api-key`, {
          method: "POST",
          headers: { ...desktopSecretHeader(), "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
        if (resp.ok) return { ok: true };
        return { ok: false, status: resp.status, message: await responseMessage(resp) };
      } catch {
        return { ok: false, status: 0, message: "gateway unreachable" };
      }
    }
  );
  electron.ipcMain.handle(
    "backends:setConnectionApiKey",
    async (event, backend, connectionId, apiKey) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, status: 400, message: "invalid backend name" };
      }
      if (!isSafeOAuthConnectionId(connectionId)) {
        return { ok: false, status: 400, message: "invalid connection id" };
      }
      if (typeof apiKey !== "string" || apiKey.trim().length < 8) {
        return { ok: false, status: 400, message: "API key is missing or too short" };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0, message: "SF server is not running" };
      }
      try {
        const resp = await fetch(
          `${sfBaseUrl}/${backend}/auth/connections/${encodeURIComponent(connectionId)}/api-key`,
          {
            method: "PUT",
            headers: { ...desktopSecretHeader(), "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey.trim() })
          }
        );
        if (resp.ok) return { ok: true };
        return { ok: false, status: resp.status, message: await responseMessage(resp) };
      } catch {
        return { ok: false, status: 0, message: "gateway unreachable" };
      }
    }
  );
  electron.ipcMain.handle(
    "backends:deleteConnection",
    async (event, backend, connectionId) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, status: 400 };
      }
      if (!isSafeOAuthConnectionId(connectionId)) {
        return { ok: false, status: 400 };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0 };
      }
      try {
        const resp = await fetch(
          `${sfBaseUrl}/${backend}/auth/connections/${encodeURIComponent(connectionId)}`,
          {
            method: "DELETE",
            headers: desktopSecretHeader()
          }
        );
        if (resp.status === 204) return { ok: true };
        return { ok: false, status: resp.status };
      } catch {
        return { ok: false, status: 0 };
      }
    }
  );
  electron.ipcMain.handle(
    "backends:refreshConnection",
    async (event, backend, connectionId) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, status: 400, message: "invalid_backend" };
      }
      if (!isSafeOAuthConnectionId(connectionId)) {
        return { ok: false, status: 400, message: "invalid_connection_id" };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0, message: "gateway_unreachable" };
      }
      try {
        const resp = await fetch(
          `${sfBaseUrl}/${backend}/auth/connections/${encodeURIComponent(connectionId)}/refresh`,
          {
            method: "POST",
            headers: desktopSecretHeader()
          }
        );
        if (resp.ok) return { ok: true, status: resp.status, connection: await resp.json() };
        return { ok: false, status: resp.status, message: await responseMessage(resp) };
      } catch (e) {
        return { ok: false, status: 0, message: e instanceof Error ? e.message : String(e) };
      }
    }
  );
  backendStatusService.on("statusChanged", (status) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("backends:statusChanged", status);
    }
  });
  backendStatusService.on("pollingError", (error) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("backends:pollingError", error);
    }
  });
  backendStatusService.on("alert", (alert) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("backends:alert", alert);
    }
  });
}
function currentGatewayRedirectPorts() {
  const status = backendStatusService.getStatus();
  if (!isStatusV2(status)) return [];
  try {
    const url2 = new URL(status.gateway.url);
    return url2.port ? [url2.port] : [];
  } catch {
    return [];
  }
}
async function responseMessage(resp) {
  try {
    const body = await resp.json();
    const detail = body.detail;
    if (Array.isArray(detail)) {
      return detail[0]?.msg ?? detail[0]?.message ?? detail[0]?.code;
    }
    return detail?.message ?? detail?.code;
  } catch {
    return void 0;
  }
}
function registerAigwSessionHandlers() {
  electron.ipcMain.handle("aigw-session:get-state", (event) => {
    requireTrustedIpcSender(event);
    return aigwSessionService.getState();
  });
  electron.ipcMain.handle("aigw-session:get-jwt", async (event) => {
    requireTrustedIpcSender(event);
    return aigwSessionService.getJwt();
  });
  electron.ipcMain.handle("aigw-session:is-logged-in", (event) => {
    requireTrustedIpcSender(event);
    return aigwSessionService.isLoggedIn();
  });
  electron.ipcMain.handle(
    "aigw-session:login",
    async (event, username, password, options) => {
      requireTrustedIpcSender(event);
      const result = await aigwSessionService.login({ username, password }, options);
      if (result.ok) void backendStatusService.refresh();
      return result;
    }
  );
  electron.ipcMain.handle("aigw-session:logout", async (event) => {
    requireTrustedIpcSender(event);
    const snapshot = await aigwSessionService.logout();
    void backendStatusService.refresh();
    return snapshot;
  });
  electron.ipcMain.handle("aigw-session:set-gateway-url", (event, gatewayUrl) => {
    requireTrustedIpcSender(event);
    const snapshot = aigwSessionService.setGatewayUrl(gatewayUrl);
    void backendStatusService.refresh();
    return snapshot;
  });
  aigwSessionService.on("changed", (snapshot) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("aigw-session:changed", snapshot);
    }
  });
  aigwSessionService.on("expired", (snapshot) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("aigw-session:expired", snapshot);
    }
  });
  backendStatusService.on("statusChanged", (status) => {
    if (!isStatusV2(status)) return;
    if (status.gateway.mode !== "external" || status.action !== "login_gateway") return;
    void aigwSessionService.ensureLoggedIn();
  });
}
const DEFAULT_SCOREBOARD_URL = "https://scoreboard.screamingface.ai";
const DEFAULT_PORTAL_URL = "https://screamingface.ai/portal/";
function configString(key) {
  try {
    const value = configService.read()[key];
    return typeof value === "string" && value.length > 0 ? value : void 0;
  } catch {
    return void 0;
  }
}
function resolveUrl(envKey, configKey, fallback) {
  const fromEnv = process.env[envKey];
  if (fromEnv && fromEnv.length > 0) return fromEnv;
  return configString(configKey) ?? fallback;
}
function resolvePublishContext() {
  return {
    scoreboardUrl: resolveUrl("SF_SCOREBOARD_URL", "scoreboard_url", DEFAULT_SCOREBOARD_URL),
    portalUrl: resolveUrl("SF_PORTAL_URL", "portal_url", DEFAULT_PORTAL_URL),
    client: {
      name: "screamingface-desktop",
      version: electron.app.getVersion(),
      platform: process.platform
    }
  };
}
const MAX_BACKLOG = 200;
const buffer = [];
const emitter = new events.EventEmitter();
emitter.setMaxListeners(0);
function publishLog(message) {
  log(message);
  const line = `[${(/* @__PURE__ */ new Date()).toISOString()}] ${message}`;
  buffer.push(line);
  if (buffer.length > MAX_BACKLOG) buffer.splice(0, buffer.length - MAX_BACKLOG);
  emitter.emit("line", line);
}
function getPublishLog() {
  return [...buffer];
}
function onPublishLog(listener) {
  emitter.on("line", listener);
  return () => emitter.off("line", listener);
}
const TIMEOUT_MS$1 = 1e4;
const BACKOFF_MS = [1e3, 2e3, 4e3];
function detailFromBody(body) {
  let detail;
  try {
    detail = JSON.parse(body).detail;
  } catch {
    return null;
  }
  if (typeof detail === "string") return detail || null;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const field = loc.length > 0 ? String(loc[loc.length - 1]) : "";
      const msg = String(item.msg ?? "").replace(/^Value error,\s*/, "");
      if (!msg) return "";
      return field && !msg.includes(field) ? `${field}: ${msg}` : msg;
    }).filter(Boolean);
    return parts.length > 0 ? parts.join("; ") : null;
  }
  if (detail && typeof detail === "object") {
    const { field, message } = detail;
    if (message) return field && !message.includes(field) ? `${field}: ${message}` : message;
  }
  return null;
}
function errorForStatus(status, body) {
  const detail = detailFromBody(body);
  switch (status) {
    case 404:
      return detail ? `The scoreboard rejected the submission — ${detail}. Coordinate with the scoreboard owner before publishing.` : "That benchmark is not registered on the scoreboard yet. Coordinate with the scoreboard owner before publishing.";
    case 400:
    case 422:
      return detail ? `The scoreboard rejected the submission — ${detail}.` : "The submission did not match the scoreboard contract. This is a bug — please report it.";
    default:
      return `Scoreboard returned HTTP ${status}: ${body.slice(0, 200)}`;
  }
}
function buildBody(request, client) {
  const total = request.totalQuestions ?? 0;
  const correct = request.correctQuestions ?? 0;
  const accuracy = total > 0 ? correct / total : 0;
  const submittedBy = request.submittedBy && request.submittedBy.trim().length > 0 ? request.submittedBy.trim() : null;
  return {
    version: 1,
    benchmark_id: request.benchmarkId,
    spec_id: request.specId,
    url4_expression: request.url4Expression,
    submitted_by: submittedBy,
    accuracy,
    total_questions: total,
    correct_questions: correct,
    ran_with_providers: request.providers,
    ran_at_local: request.ranAtLocal,
    client: { name: client.name, version: client.version, platform: client.platform },
    // Carry the client-derived benchmark content signature (SF-300) so the
    // scoreboard can pin benchmark_id to the exact eval content this run used.
    // SERVER FOLLOW-UP: verify this signature against the source dataset bytes
    // server-side (the client cannot — it holds only reconstructed rows, not the
    // original jsonl). Until then it is recorded as metadata for auditing.
    // `metadata` is a free-form object in the scoreboard contract; null when no
    // signature is available so we never send an empty-string hash.
    metadata: request.benchmarkSignature ? { benchmark_signature: request.benchmarkSignature, signature_alg: "sha256" } : null
  };
}
async function postOnce(url2, body, idempotencyKey) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS$1);
  try {
    return await fetch(`${url2.replace(/\/$/, "")}/v1/scores`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
      signal: controller.signal
    });
  } finally {
    clearTimeout(timer);
  }
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function submitScore(request) {
  const ctx = resolvePublishContext();
  const body = buildBody(request, ctx.client);
  const idempotencyKey = request.runId;
  const target = `${ctx.scoreboardUrl.replace(/\/$/, "")}/v1/scores`;
  publishLog(
    `publish: POST ${target} run=${request.runId} benchmark=${request.benchmarkId} spec=${request.specId} total=${request.totalQuestions} correct=${request.correctQuestions} providers=${request.providers.join("+") || "-"}`
  );
  let lastErr = null;
  for (let attempt = 0; attempt <= BACKOFF_MS.length; attempt += 1) {
    if (attempt > 0) await sleep(BACKOFF_MS[attempt - 1]);
    const label = `attempt ${attempt + 1}/${BACKOFF_MS.length + 1}`;
    let res;
    try {
      res = await postOnce(ctx.scoreboardUrl, body, idempotencyKey);
    } catch (e) {
      lastErr = "Could not reach the scoreboard. Check your connection and try again.";
      publishLog(`publish: ${label} network/abort error: ${e.message}`);
      continue;
    }
    if (res.ok) {
      const data = await res.json();
      publishLog(`publish: ${label} -> HTTP ${res.status} ok, score=${data.id}`);
      const portalLink = `${ctx.scoreboardUrl.replace(/\/$/, "")}/benchmark.html?id=${encodeURIComponent(data.benchmark_id)}`;
      const value = {
        id: data.id,
        benchmarkId: data.benchmark_id,
        specId: data.spec_id,
        portalLink
      };
      return { ok: true, value };
    }
    const text = await res.text();
    publishLog(`publish: ${label} -> HTTP ${res.status}: ${text.slice(0, 500)}`);
    if (res.status >= 500) {
      lastErr = errorForStatus(res.status, text);
      continue;
    }
    return { ok: false, error: errorForStatus(res.status, text) };
  }
  publishLog(`publish: giving up after ${BACKOFF_MS.length + 1} attempts: ${lastErr ?? "unknown"}`);
  return { ok: false, error: lastErr ?? "Publishing failed after several attempts." };
}
const TIMEOUT_MS = 8e3;
async function listBenchmarks() {
  const ctx = resolvePublishContext();
  const url2 = `${ctx.scoreboardUrl.replace(/\/$/, "")}/v1/benchmarks`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url2, { signal: controller.signal });
    if (!res.ok) {
      publishLog(`benchmarks: GET ${url2} -> HTTP ${res.status}`);
      return null;
    }
    const data = await res.json();
    const rows = Array.isArray(data.benchmarks) ? data.benchmarks : [];
    return rows.filter(
      (b) => typeof b?.id === "string" && b.id.length > 0
    ).map((b) => ({
      id: b.id,
      displayName: typeof b.display_name === "string" && b.display_name.length > 0 ? b.display_name : b.id
    }));
  } catch (e) {
    publishLog(`benchmarks: GET ${url2} failed: ${e.message}`);
    return null;
  } finally {
    clearTimeout(timer);
  }
}
function isHttpUrl(value) {
  try {
    const url2 = new URL(value);
    return url2.protocol === "http:" || url2.protocol === "https:";
  } catch {
    return false;
  }
}
function registerPublishHandlers() {
  electron.ipcMain.handle("publish:getContext", (event) => {
    requireTrustedIpcSender(event);
    return resolvePublishContext();
  });
  electron.ipcMain.handle(
    "publish:submitScore",
    (event, request) => {
      requireTrustedIpcSender(event);
      return submitScore(request);
    }
  );
  electron.ipcMain.handle("publish:getLogs", (event) => {
    requireTrustedIpcSender(event);
    return getPublishLog();
  });
  electron.ipcMain.handle("publish:listBenchmarks", (event) => {
    requireTrustedIpcSender(event);
    return listBenchmarks();
  });
  onPublishLog((line) => {
    for (const win of electron.BrowserWindow.getAllWindows()) {
      win.webContents.send("publish:log", line);
    }
  });
  electron.ipcMain.handle("publish:openExternal", async (event, url2) => {
    requireTrustedIpcSender(event);
    if (!isHttpUrl(url2)) return;
    await electron.shell.openExternal(url2);
  });
}
function registerAllHandlers() {
  registerConfigHandlers();
  registerVenvHandlers();
  registerServerHandlers();
  registerPluginHandlers();
  registerSessionHandlers();
  registerAigwSessionHandlers();
  registerBackendStatusHandlers();
  registerPublishHandlers();
}
let mainWindow = null;
let phoenixWindow = null;
function showMainWindow(reason) {
  if (!mainWindow || mainWindow.isDestroyed() || mainWindow.isVisible()) return;
  log(`[main] show window (${reason})`);
  mainWindow.show();
}
function registerMainWindowDiagnostics(window) {
  window.on("ready-to-show", () => {
    log(`[main] ready-to-show`);
  });
  window.on("unresponsive", () => {
    log(`[main] window unresponsive`);
  });
  window.webContents.on("dom-ready", () => {
    log(`[renderer] dom-ready`);
    showMainWindow("dom-ready");
  });
  window.webContents.on("did-finish-load", () => {
    log(`[renderer] did-finish-load`);
  });
  window.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    log(
      `[renderer] did-fail-load code=${errorCode} description=${errorDescription} url=${validatedURL}`
    );
    showMainWindow("did-fail-load");
  });
  window.webContents.on("render-process-gone", (_event, details) => {
    log(`[renderer] render-process-gone reason=${details.reason} exitCode=${details.exitCode}`);
  });
  window.webContents.on("preload-error", (_event, preloadPath, error) => {
    log(`[renderer] preload-error path=${preloadPath} message=${error.message}`);
  });
  window.webContents.on("console-message", (event) => {
    log(
      `[renderer:console:${event.level}] ${event.message} (${event.sourceId}:${event.lineNumber})`
    );
  });
}
function createWindow() {
  mainWindow = new electron.BrowserWindow({
    width: 1120,
    height: 750,
    minWidth: 860,
    minHeight: 600,
    show: false,
    titleBarStyle: "hiddenInset",
    backgroundColor: "#14121a",
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      sandbox: false
    }
  });
  log(`[main] BrowserWindow created`);
  registerMainWindowDiagnostics(mainWindow);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  mainWindow.webContents.setWindowOpenHandler(({ url: url2 }) => {
    if (isAllowedExternalBrowserUrl(url2)) {
      void electron.shell.openExternal(url2);
    }
    return { action: "deny" };
  });
  if (utils.is.dev && process.env["ELECTRON_RENDERER_URL"]) {
    mainWindow.loadURL(process.env["ELECTRON_RENDERER_URL"]);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
}
function registerPopupHandlers() {
  electron.ipcMain.handle("popup:open", (event, url2, title) => {
    requireTrustedIpcSender(event);
    if (!isAllowedPopupUrl(url2)) return;
    if (phoenixWindow && !phoenixWindow.isDestroyed()) {
      phoenixWindow.loadURL(url2);
      phoenixWindow.focus();
      return;
    }
    phoenixWindow = new electron.BrowserWindow({
      width: 1200,
      height: 800,
      minWidth: 600,
      minHeight: 400,
      title: title || "Debug",
      backgroundColor: "#14121a",
      parent: mainWindow || void 0,
      webPreferences: {
        sandbox: true,
        contextIsolation: true
      }
    });
    phoenixWindow.loadURL(url2);
    phoenixWindow.on("closed", () => {
      phoenixWindow = null;
    });
  });
  electron.ipcMain.handle("popup:close", (event) => {
    requireTrustedIpcSender(event);
    if (phoenixWindow && !phoenixWindow.isDestroyed()) {
      phoenixWindow.close();
      phoenixWindow = null;
    }
  });
}
electron.app.on("certificate-error", (event, _webContents, url2, _error, _cert, callback) => {
  const parsed = new URL(url2);
  if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
    event.preventDefault();
    callback(true);
  } else {
    callback(false);
  }
});
log(`[main] module loaded`);
electron.app.whenReady().then(async () => {
  log(`[main] app.whenReady()`);
  electron.session.defaultSession.setCertificateVerifyProc((request, callback) => {
    if (request.hostname === "localhost" || request.hostname === "127.0.0.1") {
      callback(0);
    } else {
      callback(-3);
    }
  });
  await aigwSessionService.init();
  registerAllHandlers();
  registerPopupHandlers();
  createWindow();
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});
let isQuitting = false;
electron.app.on("before-quit", (event) => {
  if (isQuitting) return;
  isQuitting = true;
  event.preventDefault();
  Promise.allSettled([sessionManager.terminateAll(), serverProcess.stop()]).finally(() => {
    electron.app.quit();
  });
});
electron.app.on("window-all-closed", () => {
  if (process.platform !== "darwin" || utils.is.dev) {
    electron.app.quit();
  }
});
function getMainWindow() {
  return mainWindow;
}
exports.getMainWindow = getMainWindow;
