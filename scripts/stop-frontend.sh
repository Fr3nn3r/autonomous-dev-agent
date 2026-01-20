#!/bin/bash
# Stop ADA Frontend

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/frontend.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping frontend (PID: $PID)..."
        kill "$PID"
        sleep 1

        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing..."
            kill -9 "$PID" 2>/dev/null
        fi

        echo "Frontend stopped"
    else
        echo "Frontend not running (stale PID file)"
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file found. Frontend may not be running."
    echo "Check manually: ss -tlnp | grep :5173"
fi
