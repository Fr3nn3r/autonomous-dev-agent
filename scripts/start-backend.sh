#!/bin/bash
# ADA Backend - FastAPI + Uvicorn
# Binds to 0.0.0.0 for WSL accessibility from Windows host

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/backend.pid"
LOG_FILE="$LOG_DIR/backend.log"

# Default configuration
HOST="${ADA_BACKEND_HOST:-0.0.0.0}"
PORT="${ADA_BACKEND_PORT:-8000}"
PROJECT_PATH="${1:-.}"

mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Backend already running (PID: $PID)"
        echo "Stop it first with: ./scripts/stop-backend.sh"
        exit 1
    else
        rm "$PID_FILE"
    fi
fi

# Check if port is in use
if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
    echo "Error: Port $PORT is already in use"
    echo "Check with: ss -tlnp | grep :$PORT"
    exit 1
fi

echo "Starting ADA backend..."
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Project: $PROJECT_PATH"
echo "  Log: $LOG_FILE"

# Start uvicorn in background
cd "$PROJECT_ROOT"
nohup python -m uvicorn autonomous_dev_agent.api.main:app \
    --host "$HOST" \
    --port "$PORT" \
    >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
sleep 1

# Verify it started
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo ""
    echo "Backend started successfully (PID: $(cat "$PID_FILE"))"
    echo ""
    echo "Access from:"
    echo "  WSL:     http://localhost:$PORT"
    echo "  Windows: http://$(hostname -I | awk '{print $1}'):$PORT"
    echo "  API docs: http://localhost:$PORT/docs"
else
    echo "Failed to start backend. Check $LOG_FILE for errors."
    rm -f "$PID_FILE"
    exit 1
fi
