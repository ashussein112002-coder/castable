#!/bin/bash
# PARAR-SCOUT.command — stop the Scout server started by ARRANCAR-SCOUT.command.
cd "$(dirname "$0")"
PID="data/scout.pid"
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
  kill "$(cat "$PID")" && echo "stopped pid $(cat "$PID")"
else
  pkill -f "uvicorn app.main:app --host 127.0.0.1 --port ${SCOUT_PORT:-8787}" && echo "stopped by pattern" || echo "nothing running"
fi
rm -f "$PID"
