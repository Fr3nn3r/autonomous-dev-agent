#!/bin/bash
# Stop all ADA services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Stopping ADA services..."
echo ""

"$SCRIPT_DIR/stop-frontend.sh"
"$SCRIPT_DIR/stop-backend.sh"

echo ""
echo "All services stopped."
