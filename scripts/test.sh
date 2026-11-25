#!/usr/bin/env bash
# Verificación completa: tests de backend, typecheck + lint + build del frontend, prueba de humo y E2E.
#   scripts/test.sh          todo
#   scripts/test.sh quick    solo pytest + frontend
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for dir in "$HOME/.local/bin" "$HOME/.cargo/bin" "/opt/homebrew/bin" "/usr/local/bin"; do
  [[ -x "$dir/uv" || -x "$dir/uv.exe" ]] && export PATH="$dir:$PATH"
done

echo "== pytest"
(cd backend && uv run pytest -q)
echo "== frontend: typecheck, lint y build"
(cd frontend && npm run typecheck && npm run lint && npm run build >/dev/null && echo "build OK")
[[ "${1:-}" == "quick" ]] && exit 0
echo "== prueba de humo por API (insightface y sface)"
(cd backend && uv run python scripts/smoke_api.py)
echo "== E2E (Playwright + Chromium con cámara falsa)"
(cd frontend && npx playwright install chromium >/dev/null && npx playwright test)
