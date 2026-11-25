#!/usr/bin/env bash
# Modo desarrollo: backend con recarga (puerto 8000) + Vite con recarga en caliente (puerto 5173, proxy /api).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for dir in "$HOME/.local/bin" "$HOME/.cargo/bin" "/opt/homebrew/bin" "/usr/local/bin"; do
  [[ -x "$dir/uv" || -x "$dir/uv.exe" ]] && export PATH="$dir:$PATH"
done
[[ -f .env ]] || {
  echo "Falta .env: ejecuta primero scripts/setup.sh"
  exit 1
}

(cd backend && uv run python -m app --reload --port 8000) &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM

echo "Backend en http://127.0.0.1:8000, frontend en http://127.0.0.1:5173 (kiosco) y /admin"
cd frontend
npm run dev -- --open
