#!/usr/bin/env bash
# Download platform-specific build assets for Electron packaging.
# Usage: ./scripts/download-build-assets.sh [--os mac|linux] [--arch arm64|x64]
#
# Outputs to: apps/desktop/build-assets/{os}/{arch}/
# OS names match electron-builder's ${os} variable: mac, linux
#   uv          — uv binary
#   python/     — python-build-standalone interpreter
#   cache/      — pre-built wheel cache for offline uv sync

set -euo pipefail

UV_VERSION="0.6.12"
PYTHON_VERSION="3.12.9"
PBS_TAG="20250317"

# --- Detect platform ---

detect_os() {
  case "$(uname -s)" in
    Darwin) echo "mac" ;;
    Linux)  echo "linux" ;;
    *)      echo >&2 "Unsupported OS: $(uname -s)"; exit 1 ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "x64" ;;
    arm64|aarch64) echo "arm64" ;;
    *)             echo >&2 "Unsupported arch: $(uname -m)"; exit 1 ;;
  esac
}

TARGET_OS="${TARGET_OS:-$(detect_os)}"
TARGET_ARCH="${TARGET_ARCH:-$(detect_arch)}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --os)    TARGET_OS="$2"; shift 2 ;;
    --arch)  TARGET_ARCH="$2"; shift 2 ;;
    *)       echo >&2 "Unknown arg: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/apps/desktop/build-assets/$TARGET_OS/$TARGET_ARCH"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> Building assets for $TARGET_OS/$TARGET_ARCH"
echo "    Output: $OUT_DIR"
mkdir -p "$OUT_DIR"

# --- 1. Download uv ---

echo "==> Downloading uv $UV_VERSION..."

uv_os="$TARGET_OS"
uv_arch="$TARGET_ARCH"
# Map to uv's naming convention
case "$TARGET_OS" in
  mac) uv_os="apple-darwin" ;;
  linux)  uv_os="unknown-linux-gnu" ;;
esac
case "$TARGET_ARCH" in
  x64)   uv_arch="x86_64" ;;
  arm64) uv_arch="aarch64" ;;
esac

uv_filename="uv-${uv_arch}-${uv_os}.tar.gz"
uv_url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${uv_filename}"

curl -fsSL "$uv_url" -o "$TMP_DIR/uv.tar.gz"
tar -xzf "$TMP_DIR/uv.tar.gz" -C "$TMP_DIR"
# uv tarball extracts to uv-{arch}-{os}/uv
find "$TMP_DIR" -name "uv" -type f ! -name "uv.tar.gz" | head -1 | xargs -I{} cp {} "$OUT_DIR/uv"
chmod +x "$OUT_DIR/uv"
echo "    uv: $(du -sh "$OUT_DIR/uv" | cut -f1)"

# --- 2. Download python-build-standalone ---

echo "==> Downloading python-build-standalone $PYTHON_VERSION..."

pbs_arch="$uv_arch"
pbs_os=""
case "$TARGET_OS" in
  mac) pbs_os="apple-darwin" ;;
  linux)  pbs_os="unknown-linux-gnu" ;;
esac

pbs_filename="cpython-${PYTHON_VERSION}+${PBS_TAG}-${pbs_arch}-${pbs_os}-install_only_stripped.tar.gz"
pbs_url="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${pbs_filename}"

curl -fsSL "$pbs_url" -o "$TMP_DIR/python.tar.gz"
mkdir -p "$OUT_DIR/python"
tar -xzf "$TMP_DIR/python.tar.gz" -C "$OUT_DIR/python" --strip-components=1
echo "    python: $(du -sh "$OUT_DIR/python" | cut -f1)"

# --- 3. Pre-build wheel cache ---

echo "==> Building wheel cache..."

# Use the just-downloaded uv + python to populate the cache
export UV_CACHE_DIR="$OUT_DIR/cache"
mkdir -p "$UV_CACHE_DIR"

# Save existing server venv if present (uv sync will overwrite it)
SERVER_VENV="$REPO_ROOT/apps/server/.venv"
if [ -d "$SERVER_VENV" ]; then
  mv "$SERVER_VENV" "$TMP_DIR/saved-venv"
fi

"$OUT_DIR/uv" sync \
  --no-install-project \
  --python "$OUT_DIR/python/bin/python3.12" \
  --directory "$REPO_ROOT/apps/server" \
  || true  # Non-fatal: cache is an optimization, not a hard requirement

# Clean up the venv uv sync created, restore original if it existed
rm -rf "$SERVER_VENV"
if [ -d "$TMP_DIR/saved-venv" ]; then
  mv "$TMP_DIR/saved-venv" "$SERVER_VENV"
fi

# Package cache as tar.gz (smaller bundle, avoids macOS xattr issues with .app bundles)
echo "    cache (raw): $(du -sh "$OUT_DIR/cache" | cut -f1)"
COPYFILE_DISABLE=1 tar czf "$OUT_DIR/cache.tar.gz" -C "$OUT_DIR/cache" .
rm -rf "$OUT_DIR/cache"
echo "    cache.tar.gz: $(du -sh "$OUT_DIR/cache.tar.gz" | cut -f1)"

echo ""
echo "==> Done! Total: $(du -sh "$OUT_DIR" | cut -f1)"
echo "    $OUT_DIR/"
ls -la "$OUT_DIR/"
