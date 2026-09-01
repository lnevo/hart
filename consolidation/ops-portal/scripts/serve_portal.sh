#!/usr/bin/env bash
# Serve the operator portal (JSON fetch needs HTTP, not file://).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8760}"
cd "$ROOT"
echo "HART operator portal → http://127.0.0.1:${PORT}/ops-portal/"
echo "(Ctrl+C to stop)"
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$(cd .. && pwd)"
