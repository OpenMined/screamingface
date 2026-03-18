#!/bin/sh
# ScreamingFace installer — works via: curl -fsSL <url>/install.sh | sh
#
# Detects OS/arch, downloads the latest release from GitHub, and installs.
# Supports SF_INSTALL_DIR env var for custom install location.

set -eu

REPO="OpenMined/sf-installer"
APP_NAME="ScreamingFace"

# --- Helpers ---

info()  { printf '  \033[1;34m>\033[0m %s\n' "$*"; }
ok()    { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
err()   { printf '  \033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

need_cmd() {
  if ! command -v "$1" > /dev/null 2>&1; then
    err "Required command not found: $1"
  fi
}

# --- Detect platform ---

detect_os() {
  case "$(uname -s)" in
    Darwin) echo "mac" ;;
    Linux)  echo "linux" ;;
    *)      err "Unsupported OS: $(uname -s). Only macOS and Linux are supported." ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64)  echo "x64" ;;
    arm64|aarch64) echo "arm64" ;;
    *)             err "Unsupported architecture: $(uname -m)" ;;
  esac
}

# --- Fetch latest release tag ---

latest_tag() {
  # Use GitHub API to get the latest release tag
  curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep '"tag_name"' \
    | head -1 \
    | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/'
}

# --- Main ---

main() {
  need_cmd curl
  need_cmd tar

  OS="$(detect_os)"
  ARCH="$(detect_arch)"

  info "Detected platform: ${OS}/${ARCH}"

  # Determine version
  if [ -n "${SF_VERSION:-}" ]; then
    TAG="$SF_VERSION"
    info "Using specified version: ${TAG}"
  else
    info "Fetching latest release..."
    TAG="$(latest_tag)"
    if [ -z "$TAG" ]; then
      err "Could not determine latest release. Set SF_VERSION to install a specific version."
    fi
    info "Latest version: ${TAG}"
  fi

  VERSION="${TAG#v}"

  # Determine artifact name and install dir
  case "$OS" in
    mac)
      ARTIFACT="ScreamingFace-${VERSION}-${OS}-${ARCH}.zip"
      INSTALL_DIR="${SF_INSTALL_DIR:-/Applications}"
      ;;
    linux)
      ARTIFACT="ScreamingFace-${VERSION}-${OS}-${ARCH}.tar.gz"
      INSTALL_DIR="${SF_INSTALL_DIR:-${HOME}/.local/share/ScreamingFace}"
      ;;
  esac

  DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${TAG}/${ARTIFACT}"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT

  # Download
  info "Downloading ${ARTIFACT}..."
  curl -fsSL "$DOWNLOAD_URL" -o "${TMP_DIR}/${ARTIFACT}"
  ok "Downloaded $(du -sh "${TMP_DIR}/${ARTIFACT}" | cut -f1)"

  # Install
  case "$OS" in
    mac)
      info "Installing to ${INSTALL_DIR}/${APP_NAME}.app..."

      # Remove previous install
      if [ -d "${INSTALL_DIR}/${APP_NAME}.app" ]; then
        info "Removing previous installation..."
        rm -rf "${INSTALL_DIR}/${APP_NAME}.app"
      fi

      # Unzip to /Applications
      unzip -qo "${TMP_DIR}/${ARTIFACT}" -d "$INSTALL_DIR"

      # Remove quarantine attribute (app isn't signed yet)
      xattr -rd com.apple.quarantine "${INSTALL_DIR}/${APP_NAME}.app" 2>/dev/null || true

      ok "Installed to ${INSTALL_DIR}/${APP_NAME}.app"

      # Launch
      info "Launching ${APP_NAME}..."
      open "${INSTALL_DIR}/${APP_NAME}.app"
      ;;

    linux)
      info "Installing to ${INSTALL_DIR}..."
      mkdir -p "$INSTALL_DIR"

      # Extract
      tar -xzf "${TMP_DIR}/${ARTIFACT}" -C "$INSTALL_DIR" --strip-components=1

      # Symlink to PATH
      BIN_DIR="${HOME}/.local/bin"
      mkdir -p "$BIN_DIR"
      BINARY="$(find "$INSTALL_DIR" -maxdepth 1 -name 'screamingface' -o -name 'ScreamingFace' | head -1)"
      if [ -n "$BINARY" ]; then
        chmod +x "$BINARY"
        ln -sf "$BINARY" "${BIN_DIR}/screamingface"
        ok "Symlinked to ${BIN_DIR}/screamingface"
      fi

      ok "Installed to ${INSTALL_DIR}"
      info "Run 'screamingface' to launch (make sure ~/.local/bin is in your PATH)"
      ;;
  esac

  echo ""
  ok "ScreamingFace ${TAG} installed successfully!"
}

main "$@"
