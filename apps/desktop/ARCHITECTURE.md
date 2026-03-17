# Desktop Packaging Architecture

## ADR: Production Build, Bundle Layout & First-Launch Bootstrap

**Status:** Accepted
**Date:** 2026-03-17
**Context:** The desktop app bundles a full Python server (FastAPI + plugins) alongside an Electron shell. The app bundle must be self-contained: users double-click the `.app` and the server bootstraps automatically. This document records exactly how that works.

---

## 1. Build Pipeline

Three tools run sequentially to produce the final `.app`:

```
electron-vite build          npm run build
        |
        v
electron-builder --mac       npx electron-builder --mac --arm64
        |
        v
dist/mac-arm64/ScreamingFace.app
```

### Step 1: `electron-vite build`

Compiles three Vite targets defined in `electron.vite.config.ts`:

```
src/main/index.ts        -->  out/main/index.js       (Node/Electron main process)
src/preload/index.ts     -->  out/preload/index.js    (context-bridge preload)
src/renderer/index.html  -->  out/renderer/            (React SPA: index.html + assets/)
```

Each target is an independent Vite build. The main and preload targets use `externalizeDepsPlugin()` to keep `electron` and Node built-ins as external requires. The renderer target bundles React, Tailwind, shadcn/ui, and all frontend deps into a single JS + CSS pair.

### Step 2: `electron-builder`

Reads the `"build"` key from `package.json`. It:

1. Packs `out/` + `node_modules` (production deps) into `app.asar`
2. Copies `extraResources` to `Contents/Resources/` (outside the asar)
3. Wraps everything in the Electron framework shell
4. Signs (ad-hoc) and produces `.dmg` + `.zip`

---

## 2. Bundle Layout (`.app` on disk)

```
ScreamingFace.app/Contents/
+-- MacOS/
|   +-- ScreamingFace                # Electron binary
+-- Frameworks/
|   +-- ScreamingFace Helper*.app/   # GPU, Renderer, Utility processes
+-- Resources/
    +-- app.asar                     # Electron app code (main + preload + renderer)
    |   out/
    |   +-- main/index.js            #   Main process bundle
    |   +-- preload/index.js         #   Preload script
    |   +-- renderer/                #   React SPA (index.html, assets/)
    |   node_modules/                #   Production npm dependencies
    |   package.json
    |
    +-- server/                      # extraResources (NOT in asar, plain files)
        +-- src/                     #   Python source (screamingface package)
        |   +-- screamingface/       #     cli/, core/, plugins/, etc.
        +-- pyproject.toml           #   Project manifest (entry points, deps)
        +-- uv.lock                  #   Locked dependency versions
        +-- sf.json                  #   Default server config template
        +-- bin/
        |   +-- uv                   #   Bundled uv binary (~33MB, platform-specific)
        +-- python/
        |   +-- bin/python3.12       #   Bundled CPython interpreter
        |   +-- lib/python3.12/      #   Standard library
        +-- cache.tar.gz             #   Pre-built wheel cache (~146MB)
```

**Why `extraResources` instead of `asar`?**
The Python runtime, uv binary, and cache tarball are native binaries / large archives. They must be directly executable and `tar`-extractable from the filesystem. The asar archive is a virtual filesystem that doesn't support `execFile()` or `spawn()` on its contents.

---

## 3. Read-Only vs Writable Directories

The `.app` bundle (`Contents/Resources/`) is **read-only** after installation. All mutable state lives in `userData`:

```
~/Library/Application Support/screamingface-desktop/   (= app.getPath('userData'))
+-- .venv/                   # Python virtual environment (created by uv)
|   +-- bin/
|   |   +-- python           #   Symlink to bundled python3.12
|   |   +-- sf               #   CLI entry point (installed by pip install)
|   |   +-- uvicorn, ...     #   All dependency executables
|   +-- lib/python3.12/
|       +-- site-packages/   #   Installed packages
+-- uv-cache/                # Extracted wheel cache (from cache.tar.gz)
+-- pyproject.toml           # Copied from bundle (uv sync needs it here)
+-- uv.lock                  # Copied from bundle
+-- sf.json                  # Server config (copied from template on first run)
+-- .sf-version              # Version stamp ("0.1.0") for re-sync detection
+-- debug.log                # File-based debug log (truncated each launch)
+-- Cookies, Session Storage, ...  # Chromium/Electron browser data
```

**Key invariant:** Every `spawn()` / `execFileSync()` call in production uses either:

- **Bundled binaries** from `process.resourcesPath` (uv, python) -- read-only, never modified
- **Venv binaries** from `userData/.venv/bin/` -- created during bootstrap, writable

---

## 4. First-Launch Bootstrap Sequence

On first launch (or after clearing `.venv`), the renderer and main process coordinate a multi-step bootstrap. The timeline below is from actual production logs:

```
Time(ms)  Event
--------  --------------------------------------------------------
+0        Main process module loaded
+26       app.whenReady()
+91       BrowserWindow created (show: false, bg: #14121a)
+134      ready-to-show -> window.show()
+195      Renderer mounts, useVenvStatus calls venv:detect IPC
+196      venv:detect -> pythonBin exists=false -> status: missing
          Returns { autoBootstrap: true }
+205      Renderer calls venv:create IPC
```

### Bootstrap State Machine (Main Process)

```
                    venv:detect
                        |
          .venv/bin/python exists?
         /                        \
       YES                        NO
        |                          |
  python --version          status = 'missing'
    OK?                    autoBootstrap = !is.dev  (prod only)
   /    \                       |
  v      v               venv:create
ready   error          (suppressReady)
  |                         |
  |     .sf-version     uv venv .venv
  |      matches?       --python bundled
  |     /      \             |
  |   YES      NO         (success, stays at 'creating')
  |    |        |            |
  v    v        v       venv:sync
 done  |    venv:sync        |
       |        |       +---------+
       v        |       | Step 1  | Copy pyproject.toml + uv.lock to userData
     (skip)     |       | Step 2  | Extract cache.tar.gz -> uv-cache/
                |       | Step 3  | uv sync --no-install-project (UV_OFFLINE=1)
                |       |         |   (installs deps from cache, suppressReady)
                |       | Step 4  | uv pip install --no-deps <bundled-server>
                |       |         |   (builds wheel via hatchling, installs sf entry point)
                |       |         |   (THIS emits status='ready')
                |       | Step 5  | Write .sf-version stamp
                |       +---------+
                |            |
                v            v
              status = 'ready'
                      |
              DashboardView useEffect:
              venv.status === 'ready' && server.status === 'stopped'
                      |
              server.start() -> spawn sf run --subprocess --config-json {...}
                      |
              Server emits {"event":"ready","port":8002,"scheme":"https"}
                      |
              Health checks begin (10s interval)
```

### Why `--no-install-project` + separate `pip install`?

`uv sync` runs from `userData/` (writable) with copied `pyproject.toml` + `uv.lock`. But the Python source code (`src/screamingface/`) is only in the read-only bundle. Two-step approach:

1. `uv sync --no-install-project` -- installs all dependencies from the offline cache. Runs with `UV_OFFLINE=1` to avoid network. Fast (~400ms with cache).

2. `uv pip install --no-deps <bundle>/server` -- builds the project wheel using hatchling (downloaded on first run, ~550ms), installs the `screamingface` package + `sf` entry point into `.venv/bin/`. Runs WITHOUT `UV_OFFLINE` because hatchling is a build dependency not in the wheel cache.

### Race Condition Prevention

The `ready` status triggers the server auto-start in the renderer:

```typescript
// DashboardView.tsx
useEffect(() => {
  if (venv.status === 'ready' && server.status === 'stopped') {
    server.start(); // spawns .venv/bin/sf
  }
}, [venv.status]);
```

If `ready` fires before `sf` is installed, server start fails with ENOENT. Solution: `runUvCommand()` accepts `{ suppressReady: true }` to prevent premature status transitions:

```
create()           -> suppressReady: true       (venv exists but no packages yet)
sync (uv sync)     -> suppressReady: !is.dev   (in prod: deps installed but no sf yet)
sync (pip install)  -> suppressReady: false      (sf installed, FINAL ready signal)
```

---

## 5. Path Resolution Summary

| What                            | Dev (`is.dev`)                    | Production                                       |
| ------------------------------- | --------------------------------- | ------------------------------------------------ |
| `serverDir`                     | `apps/server/` (monorepo sibling) | `process.resourcesPath/server/` (bundle)         |
| `projectDir` (uv cwd)           | Same as serverDir                 | `app.getPath('userData')`                        |
| `venvDir`                       | `apps/server/.venv/`              | `userData/.venv/`                                |
| `sfBin`                         | `apps/server/.venv/bin/sf`        | `userData/.venv/bin/sf`                          |
| `uvBin`                         | `which uv` or known paths         | `resourcesPath/server/bin/uv` (bundled first)    |
| `pythonBin` (for venv creation) | System python via uv              | `resourcesPath/server/python/bin/python3.12`     |
| `configPath` (sf.json)          | `apps/server/sf.json`             | `userData/sf.json` (copied from bundle template) |

---

## 6. Update & Re-sync

On subsequent launches, if `.venv` already exists:

```
detect() -> pythonBin exists -> python --version OK -> status: ready
         -> read .sf-version stamp
         -> compare with app.getVersion()
         -> mismatch? -> needsSync: true -> renderer calls sync()
```

`sync()` re-runs the full uv sync + pip install flow, then writes the new version stamp. This handles dependency changes between app versions.

---

## 7. Files That Participate

| File                                        | Role                                                 |
| ------------------------------------------- | ---------------------------------------------------- |
| `package.json` `"build"`                    | electron-builder config: extraResources, targets     |
| `electron.vite.config.ts`                   | Three-target Vite build (main, preload, renderer)    |
| `build-assets/${os}/${arch}/`               | Platform-specific binaries: uv, python, cache.tar.gz |
| `src/main/index.ts`                         | App lifecycle, window creation, ready-to-show        |
| `src/main/debug-log.ts`                     | File-based logger (userData/debug.log)               |
| `src/main/services/config-service.ts`       | Resolves serverDir, configPath (dev vs prod)         |
| `src/main/services/uv-resolver.ts`          | Finds uv binary (bundled in prod, PATH in dev)       |
| `src/main/services/venv-manager.ts`         | Bootstrap orchestrator: detect/create/sync           |
| `src/main/services/server-process.ts`       | Spawns `sf run`, health checks, auto-restart         |
| `src/main/ipc/venv-manager.ipc.ts`          | IPC bridge: renderer <-> VenvManager                 |
| `src/renderer/src/hooks/use-venv-status.ts` | React hook: auto-bootstrap trigger                   |
| `src/renderer/src/views/DashboardView.tsx`  | Auto-start server when venv ready                    |
| `apps/server/pyproject.toml`                | `[project.scripts] sf = ...` defines entry point     |
