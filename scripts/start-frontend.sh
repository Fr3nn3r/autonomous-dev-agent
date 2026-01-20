#!/bin/bash
# ADA Frontend - React + Vite
# Binds to 0.0.0.0 for WSL accessibility from Windows host

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/ada-dashboard"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/frontend.pid"
LOG_FILE="$LOG_DIR/frontend.log"

# Default configuration
HOST="${ADA_FRONTEND_HOST:-0.0.0.0}"
PORT="${ADA_FRONTEND_PORT:-5173}"

mkdir -p "$LOG_DIR"

# Check if frontend directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "Error: Frontend directory not found: $FRONTEND_DIR"
    exit 1
fi

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Frontend already running (PID: $PID)"
        echo "Stop it first with: ./scripts/stop-frontend.sh"
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

# Check if node_modules exists
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd "$FRONTEND_DIR"
    npm install
fi

echo "Starting ADA frontend..."
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Log: $LOG_FILE"

# Start vite in background
cd "$FRONTEND_DIR"
nohup npx vite --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
sleep 2

# Verify it started
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo ""
    echo "Frontend started successfully (PID: $(cat "$PID_FILE"))"
    echo ""
    echo "Access from:"
    echo "  WSL:     http://localhost:$PORT"
    echo "  Windows: http://$(hostname -I | awk '{print $1}'):$PORT"
else
    echo "Failed to start frontend. Check $LOG_FILE for errors."
    rm -f "$PID_FILE"
    exit 1
fi
