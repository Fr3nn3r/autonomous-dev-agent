#!/bin/bash
# Start all ADA services
# Usage: ./scripts/start-all.sh [project_path]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH="${1:-.}"

echo "========================================"
echo "  Starting ADA Development Environment"
echo "========================================"
echo ""

# Start backend first (frontend proxies to it)
"$SCRIPT_DIR/start-backend.sh" "$PROJECT_PATH"
echo ""

# Start frontend
"$SCRIPT_DIR/start-frontend.sh"
echo ""

echo "========================================"
echo "  All services started!"
echo "========================================"
echo ""
echo "Ports:"
echo "  Backend (API):  ${ADA_BACKEND_PORT:-8000}"
echo "  Frontend (UI):  ${ADA_FRONTEND_PORT:-5173}"
echo ""
echo "Logs directory: ./logs/"
echo "  - backend.log"
echo "  - frontend.log"
echo ""
echo "To stop: ./scripts/stop-all.sh"
echo ""

# Show WSL IP for Windows access
WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -n "$WSL_IP" ]; then
    echo "Access from Windows host:"
    echo "  http://$WSL_IP:${ADA_FRONTEND_PORT:-5173}"
fi
