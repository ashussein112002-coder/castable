#!/bin/bash
# ARRANCAR-SCOUT.command — start Scout by VYRAL on this Mac (double-click, or run from Jarvis).
#
#   1. venv under .venv (python3 from Homebrew/Xcode; no sudo)
#   2. env: ~/jarvis-vault/.env.oriane (ORIANE_API_KEY) + ~/jarvis-agent/.env (ANTHROPIC_API_KEY only)
#   3. uvicorn on 127.0.0.1:8787, log to data/scout.log, pid to data/scout.pid
#   4. opens the browser unless SCOUT_NO_BROWSER=1
# Idempotent: if /api/health already answers, it just opens the page.
set -u
cd "$(dirname "$0")"
ROOT="$(pwd)"
LOG="$ROOT/data/scout.log"; PID="$ROOT/data/scout.pid"; mkdir -p "$ROOT/data"
say() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG"; }
PORT="${SCOUT_PORT:-8787}"
URL="http://127.0.0.1:$PORT"

if curl -s -m 2 "$URL/api/health" >/dev/null 2>&1; then
  say "Scout already up on $URL"
  [ "${SCOUT_NO_BROWSER:-0}" = 1 ] || open "$URL"
  exit 0
fi

# interpreter: a modern python (3.11+). Jarvis's own venv is a known-good one on this Mac.
PY=""
for cand in "$HOME/jarvis-agent/.venv/bin/python" /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 python3.12 python3.11 python3; do
  c="$(command -v "$cand" 2>/dev/null || echo "$cand")"
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { say "no python >= 3.11 found (brew install python@3.12)"; exit 1; }
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  say "creating venv with $PY"
  "$PY" -m venv "$ROOT/.venv" || { say "venv failed"; exit 1; }
fi
"$ROOT/.venv/bin/python" -c "import fastapi, httpx, jinja2, uvicorn" 2>/dev/null || {
  say "installing requirements"
  "$ROOT/.venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements.txt" 2>&1 | tail -2 | tee -a "$LOG"
}

# --- environment: keys never live in this repo ---------------------------------
load_env() { # $1 file, $2.. keys to import (all when none given)
  local f="$1"; shift
  [ -f "$f" ] || return 0
  if [ $# -eq 0 ]; then set -a; . "$f"; set +a; return 0; fi
  for k in "$@"; do
    local v; v="$(grep -E "^$k=" "$f" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
    [ -n "$v" ] && export "$k=$v"
  done
}
load_env "$HOME/jarvis-vault/.env.oriane"
load_env "$ROOT/.env"
export SCOUT_HOST=127.0.0.1 SCOUT_PORT="$PORT"
# Zero-spend rule: never the paid API or `claude -p` here. The local Ollama model writes the plan;
# if it is down, the report still completes deterministically.
export SCOUT_LLM_BACKEND="${SCOUT_LLM_BACKEND:-ollama}" SCOUT_OLLAMA_MODEL="${SCOUT_OLLAMA_MODEL:-qwen3.5:9b}" SCOUT_LLM_TIMEOUT_S="${SCOUT_LLM_TIMEOUT_S:-120}"
# credit discipline for the live API (override in ~/jarvis-vault/.env.oriane if the plan allows more)
export SCOUT_DISCOVERY_LIMIT="${SCOUT_DISCOVERY_LIMIT:-40}" SCOUT_VET_TOP_K="${SCOUT_VET_TOP_K:-5}" \
       SCOUT_VET_VIDEOS_PER_CREATOR="${SCOUT_VET_VIDEOS_PER_CREATOR:-8}" SCOUT_MAX_RESULTS_PER_RUN="${SCOUT_MAX_RESULTS_PER_RUN:-160}"
[ -n "${ORIANE_API_KEY:-}" ] && say "Oriane key: present" || say "Oriane key: MISSING (put ORIANE_API_KEY=... in ~/jarvis-vault/.env.oriane) — running against the real API will 401"
say "LLM: $SCOUT_LLM_BACKEND ($SCOUT_OLLAMA_MODEL) — local, free"

# --- start ---------------------------------------------------------------------
say "starting uvicorn on $URL"
nohup "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >>"$LOG" 2>&1 &
echo $! > "$PID"
for i in $(seq 1 30); do
  sleep 1
  if curl -s -m 2 "$URL/api/health" >/dev/null 2>&1; then
    say "Scout up (pid $(cat "$PID")) → $URL"
    [ "${SCOUT_NO_BROWSER:-0}" = 1 ] || open "$URL"
    exit 0
  fi
done
say "Scout did not come up in 30 s — last log lines:"; tail -20 "$LOG"
[ "${SCOUT_NO_TTY:-0}" = 1 ] || read -r -p "Enter to close" _
exit 1
