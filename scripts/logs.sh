#!/bin/bash
# View ADA service logs
# Usage: ./scripts/logs.sh [backend|frontend|all] [--follow|-f]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"

SERVICE="${1:-all}"
FOLLOW=""

# Check for follow flag
for arg in "$@"; do
    if [ "$arg" = "-f" ] || [ "$arg" = "--follow" ]; then
        FOLLOW="-f"
    fi
done

case "$SERVICE" in
    backend)
        if [ -f "$LOG_DIR/backend.log" ]; then
            tail $FOLLOW -n 50 "$LOG_DIR/backend.log"
        else
            echo "No backend log found"
        fi
        ;;
    frontend)
        if [ -f "$LOG_DIR/frontend.log" ]; then
            tail $FOLLOW -n 50 "$LOG_DIR/frontend.log"
        else
            echo "No frontend log found"
        fi
        ;;
    all|*)
        echo "=== Backend Log ==="
        if [ -f "$LOG_DIR/backend.log" ]; then
            tail -n 20 "$LOG_DIR/backend.log"
        else
            echo "(no log)"
        fi
        echo ""
        echo "=== Frontend Log ==="
        if [ -f "$LOG_DIR/frontend.log" ]; then
            tail -n 20 "$LOG_DIR/frontend.log"
        else
            echo "(no log)"
        fi

        if [ -n "$FOLLOW" ]; then
            echo ""
            echo "Following all logs (Ctrl+C to stop)..."
            tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log" 2>/dev/null
        fi
        ;;
esac
