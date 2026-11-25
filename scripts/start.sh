#!/usr/bin/env bash
# Arranca el servidor en http://localhost:8000 (solo 127.0.0.1) y abre el navegador.
# NO_BROWSER=1 scripts/start.sh  para no abrir el navegador.
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
command -v uv >/dev/null 2>&1 || {
  echo "Falta uv: ejecuta scripts/setup.sh"
  exit 1
}

PORT="$(grep -E '^PORT=' .env | head -1 | cut -d= -f2- || true)"
PORT="${PORT:-8000}"

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "El puerto $PORT está ocupado. Mira qué proceso lo usa con:  lsof -iTCP:$PORT -sTCP:LISTEN"
  echo "Ciérralo (kill <PID>) o cambia PORT en .env."
  exit 1
fi

if [[ ! -f frontend/dist/index.html ]]; then
  echo "· Compilando el frontend"
  (cd frontend && npm run build >/dev/null)
fi

URL="http://localhost:$PORT"
open_browser() {
  case "$(uname -s)" in
    Darwin) open "$1" ;;
    Linux) xdg-open "$1" >/dev/null 2>&1 || true ;;
    MINGW* | MSYS* | CYGWIN*) cmd.exe /c start "" "$1" >/dev/null 2>&1 || true ;;
  esac
}

if [[ "${NO_BROWSER:-0}" != "1" ]]; then
  (
    for _ in $(seq 1 80); do
      if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
        open_browser "$URL"
        exit 0
      fi
      sleep 0.5
    done
  ) &
fi

echo "Asistencia biométrica en $URL  (panel: $URL/admin). Ctrl+C para detener."
cd backend
exec uv run python -m app --port "$PORT"
