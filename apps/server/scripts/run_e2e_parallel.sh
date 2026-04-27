#!/usr/bin/env bash
# Run e2e tests partitioned by provider:
#   Phase 1 — claude / codex / gemini queues run in parallel (each sequential
#             internally to respect provider rate limits).
#   Phase 2 — multi-provider + provider-agnostic tests run after Phase 1.
#
# Usage:  scripts/run_e2e_parallel.sh [extra pytest args...]
#
# Exit code is non-zero if any phase failed.
# Compatible with bash 3.2 (default on macOS) — no associative arrays.

cd "$(dirname "$0")/.."

LOG_DIR="${LOG_DIR:-/tmp/sf-e2e-$$}"
mkdir -p "$LOG_DIR"
echo "Logs: $LOG_DIR"

EXTRA=("$@")

run_phase() {
  local provider=$1
  local log="$LOG_DIR/$provider.log"
  echo "[start] $provider -> $log"
  if [ ${#EXTRA[@]} -gt 0 ]; then
    uv run pytest tests/e2e --provider="$provider" -v "${EXTRA[@]}" > "$log" 2>&1
  else
    uv run pytest tests/e2e --provider="$provider" -v > "$log" 2>&1
  fi
  local rc=$?
  echo "[done ] $provider rc=$rc"
  return $rc
}

# --- Phase 1: parallel provider queues ---
run_phase claude  & PID_CLAUDE=$!
run_phase codex   & PID_CODEX=$!
run_phase gemini  & PID_GEMINI=$!

PHASE1_RC=0
wait "$PID_CLAUDE" || { PHASE1_RC=1; echo "[fail ] claude — see $LOG_DIR/claude.log"; }
wait "$PID_CODEX"  || { PHASE1_RC=1; echo "[fail ] codex  — see $LOG_DIR/codex.log"; }
wait "$PID_GEMINI" || { PHASE1_RC=1; echo "[fail ] gemini — see $LOG_DIR/gemini.log"; }

# --- Phase 2: multi/other (only after Phase 1 done) ---
echo "[start] phase2 (multi)"
run_phase multi
PHASE2_RC=$?

# --- Summary ---
echo
echo "=== Summary ==="
for p in claude codex gemini multi; do
  if [ -f "$LOG_DIR/$p.log" ]; then
    tail -n 3 "$LOG_DIR/$p.log" | sed "s|^|[$p] |"
  fi
done

if [ $PHASE1_RC -ne 0 ] || [ $PHASE2_RC -ne 0 ]; then
  echo "FAIL (phase1=$PHASE1_RC phase2=$PHASE2_RC). Logs in $LOG_DIR"
  exit 1
fi
echo "PASS. Logs in $LOG_DIR"
