#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "${SCRIPT_DIR}"

usage() {
  printf '%s\n' "Usage: ./dev.sh [start|restart|down|status|logs]" >&2
  exit 2
}

if (( $# > 1 )); then
  usage
fi

command="${1:-start}"

start_stack() {
  # INVARIANT: Detached startup decouples service lifetime from the invoking terminal, while
  # Compose health waiting makes a successful return meaningful to notebooks and scripts.
  docker compose up --build --detach --wait --wait-timeout 180
}

case "${command}" in
  start)
    start_stack
    ;;
  restart)
    # INVARIANT: Never pass --volumes here; provider credentials live in the named Gateway volume.
    docker compose down --remove-orphans
    start_stack
    ;;
  down)
    docker compose down --remove-orphans
    ;;
  status)
    docker compose ps
    ;;
  logs)
    exec docker compose logs --follow --tail 100
    ;;
  *)
    usage
    ;;
esac
