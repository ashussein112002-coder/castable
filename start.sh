#!/bin/bash
# start.sh — Castable on Replit (and anywhere): mock Oriane when no key, then the app.
# Zero configuration: if ORIANE_API_KEY is absent, the bundled mock server starts on :8791 and the app
# points at it (the UI shows MOCK). With a key, the app talks to https://connect.oriane.xyz (LIVE).
set -u
cd "$(dirname "$0")"
PORT="${PORT:-8080}"
export SCOUT_DISCOVERY_LIMIT="${SCOUT_DISCOVERY_LIMIT:-40}" SCOUT_VET_TOP_K="${SCOUT_VET_TOP_K:-5}" \
       SCOUT_VET_VIDEOS_PER_CREATOR="${SCOUT_VET_VIDEOS_PER_CREATOR:-8}" SCOUT_MAX_RESULTS_PER_RUN="${SCOUT_MAX_RESULTS_PER_RUN:-160}"
if [ -z "${ORIANE_API_KEY:-}" ]; then
  echo "[castable] no ORIANE_API_KEY — starting the mock Oriane server on :8791 (UI will show MOCK)"
  python -m uvicorn scout.mock_server:app --host 127.0.0.1 --port 8791 --log-level warning &
  export ORIANE_BASE_URL="http://127.0.0.1:8791" ORIANE_API_KEY="demo" ORIANE_AUTH_STYLE="bearer"
  sleep 1
else
  echo "[castable] ORIANE_API_KEY present — LIVE against ${ORIANE_BASE_URL:-https://connect.oriane.xyz}"
fi
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
