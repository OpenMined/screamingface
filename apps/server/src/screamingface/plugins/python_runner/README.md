# python_runner

Runs user-authored Python scripts in a sandboxed subprocess. Used by the
`/python` URL4 backend dispatch path.

## Sandboxing

On **darwin**, every script invocation is wrapped with `sandbox-exec` using
the profile at `sandbox/macos.sb`:

- All network is denied (`(deny network*)`).
- Filesystem writes are confined to `/tmp`, `/private/tmp`, `/var/folders`.
- Filesystem reads are restricted to the Python interpreter prefix
  (`PY_PREFIX`), the venv root (`VENV_PREFIX`), the system stdlib, and the
  script's cache directory (`SPEC_ROOT`).
- The subprocess environment is stripped to `{"PATH": "/usr/bin",
  "HOME": "/tmp"}`.

The profile imports Apple's private `system.sb` for the dyld/libsystem
bootstrap rights a sandboxed process needs before it can even reach
`main()`. The deny-network and write-outside-`/tmp` rules are layered on
top and override the parts of `system.sb` they conflict with.

On **non-darwin** platforms the runner currently has **no sandbox** and
logs a one-shot warning on first use. Linux sandboxing (e.g. via `nsjail`
or `bubblewrap`) is tracked separately as part of the Linux packaging
story.

## Disabling the sandbox (debugging only)

Set `SF_PYTHON_RUNNER__SANDBOX=off` to bypass the sandbox wrapper. This is
for local debugging; do not ship configurations with the sandbox disabled.

## Deprecation risk

`sandbox-exec(1)` has been deprecated by Apple since macOS 10.7 but
remains functional and is widely used by Homebrew, npm, and others.
If/when Apple removes it, candidate replacements are:

- `nsjail` (Linux primarily, runnable on macOS under a VM).
- Pure-Python partial fallback via `resource.setrlimit` + `os.chroot`
  (does not cover network).

Until then, the profile here is the only enforced security boundary in
the demo — AST validation is deliberately out of scope (DEMO-031).
