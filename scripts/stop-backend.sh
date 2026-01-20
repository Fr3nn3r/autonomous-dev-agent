#!/bin/bash
# Stop ADA Backend

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/backend.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping backend (PID: $PID)..."
        kill "$PID"
        sleep 1

        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing..."
            kill -9 "$PID" 2>/dev/null
        fi

        echo "Backend stopped"
    else
        echo "Backend not running (stale PID file)"
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file found. Backend may not be running."
    echo "Check manually: ss -tlnp | grep :8000"
fi
