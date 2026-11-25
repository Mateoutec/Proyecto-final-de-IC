#!/usr/bin/env bash
# Instalación completa: idempotente y no interactiva. Se puede ejecutar las veces que haga falta.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OS="$(uname -s)"

ok() { printf "\033[32m✓\033[0m %s\n" "$*"; }
info() { printf "· %s\n" "$*"; }
fail() {
  printf "\033[31m✗ %s\033[0m\n" "$*" >&2
  exit 1
}

echo "Asistencia biométrica v1: instalación"
echo

# 1. Requisitos -----------------------------------------------------------------
if [[ "$OS" == "Darwin" ]]; then
  xcode-select -p >/dev/null 2>&1 || fail "Faltan las Xcode Command Line Tools. Instálalas con:  xcode-select --install"
  ok "Xcode Command Line Tools"
fi

for dir in "$HOME/.local/bin" "$HOME/.cargo/bin" "/opt/homebrew/bin" "/usr/local/bin"; do
  [[ -x "$dir/uv" || -x "$dir/uv.exe" ]] && export PATH="$dir:$PATH"
done
if ! command -v uv >/dev/null 2>&1; then
  if [[ "$OS" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    info "Instalando uv con Homebrew"
    brew install uv
  else
    fail "Falta uv. Instálalo con:  brew install uv   (sin Homebrew: curl -LsSf https://astral.sh/uv/install.sh | sh)"
  fi
fi
ok "uv $(uv --version | awk '{print $2}')"

uv python install 3.11 >/dev/null 2>&1 || fail "uv no pudo instalar Python 3.11. Prueba:  uv python install 3.11"
ok "Python 3.11 (gestionado por uv)"

command -v node >/dev/null 2>&1 || fail "Falta Node.js 20 o superior. Instálalo con:  brew install node@22"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" -ge 20 ]] || fail "Node $(node --version) es muy antiguo; se necesita 20+. Actualiza con:  brew install node@22"
ok "Node $(node --version)"

# 2. Dependencias de Python ------------------------------------------------------
info "Instalando dependencias de Python (puede tardar la primera vez)"
(
  cd backend
  if ! uv sync --extra fingerprint >/dev/null 2>&1; then
    info "La librería opcional del lector de huellas no se instaló; se continúa sin ella"
    uv sync >/dev/null
  fi
)
ok "Dependencias de Python"

# 3. .env (nunca sobrescribe claves existentes) ----------------------------------
[[ -f .env ]] && info ".env ya existe: se conservan sus valores"
(cd backend && uv run python -m app.cli env-init)

# 4. Modelos ----------------------------------------------------------------------
info "Descargando modelos (solo la primera vez)"
if ! (cd backend && uv run python -m app.cli download-models); then
  info "Algún modelo no se descargó. El sistema arrancará con el motor que tenga disponible."
fi

# 5. Base de datos y motor --------------------------------------------------------
(cd backend && uv run python -m app.cli init-db)
if (cd backend && uv run python -m app.cli check-engine >/dev/null 2>&1); then
  ok "Motor facial cargado correctamente"
else
  info "No se pudo cargar el motor facial; revisa data/logs/app.log"
fi

# 6. Frontend ---------------------------------------------------------------------
info "Instalando y compilando el frontend"
(
  cd frontend
  if [[ -f package-lock.json ]]; then
    npm ci --no-fund --no-audit >/dev/null 2>&1 || npm install --no-fund --no-audit >/dev/null
  else
    npm install --no-fund --no-audit >/dev/null
  fi
  npm run build >/dev/null
)
ok "Frontend compilado en frontend/dist"

# 7. Permisos restrictivos --------------------------------------------------------
chmod 700 data 2>/dev/null || true
chmod 600 .env 2>/dev/null || true

PASSWORD="$(grep -E '^ADMIN_PASSWORD=' .env | head -1 | cut -d= -f2-)"
echo
ok "Instalación completa"
echo "  Arrancar:          scripts/start.sh"
echo "  Kiosco:            http://localhost:8000"
echo "  Panel de RR.HH.:   http://localhost:8000/admin"
echo "  Contraseña panel:  $PASSWORD"
