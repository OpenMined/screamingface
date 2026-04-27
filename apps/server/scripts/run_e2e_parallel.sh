#!/usr/bin/env bash
# Run e2e tests partitioned by provider:
#   Phase 1 — claude / codex / gemini queues run in parallel (each sequential
#             internally to respect provider rate limits).
#   Phase 2 — multi-provider + provider-agnostic tests run after Phase 1.
#
# Usage:  scripts/run_e2e_parallel.sh [extra pytest args...]
#
# Exit code is non-zero if any phase failed.

set -u

cd "$(dirname "$0")/.."

LOG_DIR="${LOG_DIR:-/tmp/sf-e2e-$$}"
mkdir -p "$LOG_DIR"
echo "Logs: $LOG_DIR"

EXTRA=("$@")

run_phase() {
  local provider=$1
  local log="$LOG_DIR/$provider.log"
  echo "[start] $provider -> $log"
  uv run pytest tests/e2e --provider="$provider" -v "${EXTRA[@]}" \
    > "$log" 2>&1
  local rc=$?
  echo "[done ] $provider rc=$rc"
  return $rc
}

# --- Phase 1: parallel provider queues ---
declare -A PIDS
for p in claude codex gemini; do
  run_phase "$p" &
  PIDS[$p]=$!
done

PHASE1_RC=0
for p in claude codex gemini; do
  if ! wait "${PIDS[$p]}"; then
    PHASE1_RC=1
    echo "[fail ] $p — see $LOG_DIR/$p.log"
  fi
done

# --- Phase 2: multi/other (only after Phase 1 done) ---
echo "[start] phase2 (multi)"
run_phase "multi"
PHASE2_RC=$?

# --- Summary ---
echo
echo "=== Summary ==="
for p in claude codex gemini multi; do
  tail -n 3 "$LOG_DIR/$p.log" | sed "s|^|[$p] |"
done

if [[ $PHASE1_RC -ne 0 || $PHASE2_RC -ne 0 ]]; then
  echo "FAIL (phase1=$PHASE1_RC phase2=$PHASE2_RC). Logs in $LOG_DIR"
  exit 1
fi
echo "PASS. Logs in $LOG_DIR"
