#!/usr/bin/env bash
# Build ScreamingFace Electron app locally using Docker (Linux target).
# Mirrors the GitHub Actions release workflow for pre-push testing.
#
# Usage:
#   ./scripts/local-build.sh              # build linux/x64
#   ./scripts/local-build.sh --arch arm64 # build linux/arm64 (needs QEMU)
#   ./scripts/local-build.sh --no-cache   # rebuild without Docker cache

set -euo pipefail

ARCH="x64"
DOCKER_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch)     ARCH="$2"; shift 2 ;;
    --no-cache) DOCKER_ARGS+=(--no-cache); shift ;;
    *)          echo >&2 "Unknown arg: $1"; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/release"
mkdir -p "$OUT_DIR"

echo "==> Building ScreamingFace for linux/$ARCH"
echo "    Output: $OUT_DIR/"

docker build \
  -f "$REPO_ROOT/Dockerfile.build" \
  --build-arg ARCH="$ARCH" \
  ${DOCKER_ARGS[@]+"${DOCKER_ARGS[@]}"} \
  -t sf-build \
  "$REPO_ROOT"

docker run --rm -v "$OUT_DIR:/out" sf-build

echo ""
echo "==> Build complete. Artifacts:"
ls -lh "$OUT_DIR/"
