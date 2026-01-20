#!/bin/bash
# Check status of ADA services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"

BACKEND_PORT="${ADA_BACKEND_PORT:-8000}"
FRONTEND_PORT="${ADA_FRONTEND_PORT:-5173}"

echo "========================================"
echo "  ADA Service Status"
echo "========================================"
echo ""

# Backend status
echo "Backend (port $BACKEND_PORT):"
if [ -f "$LOG_DIR/backend.pid" ]; then
    PID=$(cat "$LOG_DIR/backend.pid")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Status: RUNNING (PID: $PID)"
    else
        echo "  Status: STOPPED (stale PID file)"
    fi
else
    echo "  Status: STOPPED"
fi

# Frontend status
echo ""
echo "Frontend (port $FRONTEND_PORT):"
if [ -f "$LOG_DIR/frontend.pid" ]; then
    PID=$(cat "$LOG_DIR/frontend.pid")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Status: RUNNING (PID: $PID)"
    else
        echo "  Status: STOPPED (stale PID file)"
    fi
else
    echo "  Status: STOPPED"
fi

# Port check
echo ""
echo "Port usage:"
echo "  Port $BACKEND_PORT: $(ss -tlnp 2>/dev/null | grep -q ":$BACKEND_PORT " && echo "IN USE" || echo "FREE")"
echo "  Port $FRONTEND_PORT: $(ss -tlnp 2>/dev/null | grep -q ":$FRONTEND_PORT " && echo "IN USE" || echo "FREE")"

# WSL IP
echo ""
WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -n "$WSL_IP" ]; then
    echo "WSL IP: $WSL_IP"
    echo ""
    echo "Access URLs (from Windows):"
    echo "  Frontend: http://$WSL_IP:$FRONTEND_PORT"
    echo "  Backend:  http://$WSL_IP:$BACKEND_PORT"
    echo "  API docs: http://$WSL_IP:$BACKEND_PORT/docs"
fi

# Recent logs
echo ""
echo "Recent log activity:"
if [ -f "$LOG_DIR/backend.log" ]; then
    echo "  Backend: $(tail -1 "$LOG_DIR/backend.log" 2>/dev/null | head -c 60)..."
fi
if [ -f "$LOG_DIR/frontend.log" ]; then
    echo "  Frontend: $(tail -1 "$LOG_DIR/frontend.log" 2>/dev/null | head -c 60)..."
fi
