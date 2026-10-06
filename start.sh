#!/data/data/com.termux/files/usr/bin/bash
# ==========================================================================
# DERB MOBILE - start script
# Usage:  bash start.sh          (or)  ./start.sh
# Optional:  DERB_PORT=8080 bash start.sh
# ==========================================================================
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python}"

echo "DERB MOBILE - checking environment..."

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "ERROR: python not found. In Termux run: pkg install python"
  exit 1
fi

if ! "$PY" -c "import flask" >/dev/null 2>&1; then
  echo "Flask is not installed. Installing (needs internet once)..."
  "$PY" -m pip install --only-binary=:all: -r requirements.txt
fi

echo "Starting DERB MOBILE..."
exec "$PY" app.py
