#!/usr/bin/env bash
# Fleet Studio — One-Command Independent Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="python3"
if [ -f "$SCRIPT_DIR/../.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python"
elif [ -f "$SCRIPT_DIR/backend/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/backend/.venv/bin/python"
fi

echo "[*] Starting Fleet Studio Backend on port 8001..."
(cd "$SCRIPT_DIR/backend" && "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload) &
BACKEND_PID=$!

echo "[*] Starting Fleet Studio Frontend on port 3000..."
(cd "$SCRIPT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT INT TERM

echo ""
echo "===================================================="
echo "  Fleet Studio is launching!"
echo "  Web UI:    http://localhost:3000"
echo "  Backend:   http://localhost:8001"
echo "  API Docs:  http://localhost:8001/docs"
echo "===================================================="
echo "Press Ctrl+C to stop both services."

wait
