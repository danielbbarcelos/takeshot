#!/usr/bin/env bash
# takeshot installer — suporta instalação limpa E reinstalação/upgrade.
#
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/danielbbarcelos/takeshot/main/install.sh | bash
#   ./install.sh --dev        (a partir de um checkout local, para desenvolvimento)
#
# Rodar de novo (curl | bash de novo, ou ./install.sh de novo) ATUALIZA para a
# última versão: git pull (ou re-sync em --dev), re-renderiza ícones/.desktop,
# reinstala dependências que estejam faltando, e substitui uma instância
# residente antiga pela nova (--replace) para o upgrade valer na hora, sem
# precisar sair e entrar na sessão. Todo passo é idempotente.
set -euo pipefail

REPO_URL="https://github.com/danielbbarcelos/takeshot.git"
APP_ID="com.danielbarcelos.Takeshot"
APT_PACKAGES="python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-glib-2.0"

PREFIX="${TAKESHOT_PREFIX:-$HOME/.local}"
DEV_MODE=0
NO_SHORTCUT=0
NO_AUTOSTART=0
FORCE=0
ASSUME_YES=0

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31mERRO\033[0m %s\n' "$*" >&2; }

usage() {
  cat <<'EOF'
Uso: install.sh [opções]

  --dev            instala a partir deste checkout local (symlink), em vez de
                    clonar/atualizar do GitHub — para desenvolvimento
  --no-shortcut    não instala/atualiza o atalho de teclado global
  --no-autostart   não registra o daemon residente para iniciar com a sessão
  --force          assume o binding Print mesmo em conflito com outro app
  --yes            instala dependências apt sem perguntar
  --prefix=DIR     instala em DIR em vez de ~/.local
  -h, --help       mostra esta ajuda
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dev) DEV_MODE=1 ;;
    --no-shortcut) NO_SHORTCUT=1 ;;
    --no-autostart) NO_AUTOSTART=1 ;;
    --force) FORCE=1 ;;
    --yes) ASSUME_YES=1 ;;
    --prefix=*) PREFIX="${arg#--prefix=}" ;;
    -h|--help) usage; exit 0 ;;
    *) err "opção desconhecida: $arg"; usage; exit 1 ;;
  esac
done

INSTALL_DIR="$PREFIX/share/takeshot"
BIN_DIR="$PREFIX/bin"
BIN_PATH="$BIN_DIR/takeshot"
ICON_DEST="$PREFIX/share/icons/hicolor"
APPLICATIONS_DIR="$PREFIX/share/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

# ---------------------------------------------------------------------------
# 1. guards

[ "$(uname -s)" = "Linux" ] || { err "takeshot só roda em Linux."; exit 1; }
[ "${EUID:-$(id -u)}" -ne 0 ] || { err "não rode como root — a instalação é só para o seu \$HOME."; exit 1; }

PYTHON_BIN="$(command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || { err "python3 não encontrado no PATH."; exit 1; }
PY_OK="$("$PYTHON_BIN" -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')"
[ "$PY_OK" = "1" ] || { err "python3 >= 3.10 é necessário ($("$PYTHON_BIN" --version 2>&1) encontrado)."; exit 1; }
log "python3 OK: $("$PYTHON_BIN" --version 2>&1)"

# ---------------------------------------------------------------------------
# 2. sessão (avisa, não aborta)

SESSION_TYPE="${XDG_SESSION_TYPE:-desconhecido}"
DESKTOP="${XDG_CURRENT_DESKTOP:-desconhecido}"
if [ "$SESSION_TYPE" != "wayland" ] || ! printf '%s' "$DESKTOP" | grep -qi gnome; then
  warn "sessão atual: tipo=$SESSION_TYPE desktop=$DESKTOP — takeshot foi desenhado para Wayland+GNOME."
  warn "a captura via portal XDG deve funcionar em outros compositores Wayland;"
  warn "se a captura não-interativa for negada, use: takeshot --portal-interactive capture ..."
else
  log "sessão: Wayland+GNOME confirmado."
fi

# ---------------------------------------------------------------------------
# 3. dependências — checa e, se faltando, oferece instalar via apt

check_deps() {
  "$PYTHON_BIN" - <<'PYEOF'
import sys
ok = True
try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk  # noqa: F401
except Exception:
    ok = False
try:
    import cairo  # noqa: F401
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PYEOF
}

ask_yes_no() {
  local prompt="$1" reply=""
  if [ -t 0 ]; then
    printf '%s [s/N] ' "$prompt"
    read -r reply
  elif [ -r /dev/tty ]; then
    printf '%s [s/N] ' "$prompt" > /dev/tty
    read -r reply < /dev/tty
  else
    reply="n"
  fi
  case "$reply" in
    s|S|sim|SIM|y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

if ! check_deps; then
  warn "dependências Python/GTK faltando: $APT_PACKAGES"
  if command -v apt >/dev/null 2>&1; then
    if [ "$ASSUME_YES" = "1" ] || ask_yes_no "Instalar agora via 'sudo apt install $APT_PACKAGES'?"; then
      log "instalando dependências via apt..."
      sudo apt update
      # shellcheck disable=SC2086
      sudo apt install -y $APT_PACKAGES
    else
      err "dependências ausentes — instale manualmente e rode este script de novo:"
      err "  sudo apt install $APT_PACKAGES"
      exit 1
    fi
  else
    err "'apt' não encontrado — instale manualmente os pacotes equivalentes a: $APT_PACKAGES"
    exit 1
  fi
  check_deps || { err "dependências ainda ausentes após a instalação — verifique a saída do apt acima."; exit 1; }
fi
log "dependências Python (gi / GTK4 / libadwaita / cairo) OK."

# ---------------------------------------------------------------------------
# 4. destino: git clone/pull (padrão) OU symlink do checkout local (--dev)
#    Isto é o que torna o script capaz de REINSTALAR/ATUALIZAR: rodar de novo
#    sempre converge para o código mais recente, em vez de falhar por já existir.

mkdir -p "$PREFIX/share" "$BIN_DIR"

if [ "$DEV_MODE" = "1" ]; then
  if [ "${BASH_SOURCE[0]}" = "bash" ] || [ ! -f "${BASH_SOURCE[0]}" ]; then
    err "--dev exige rodar este script localmente (./install.sh --dev), não via curl | bash."
    exit 1
  fi
  SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
  [ -f "$SCRIPT_DIR/pyproject.toml" ] || { err "--dev precisa rodar a partir de um checkout do takeshot (pyproject.toml ausente em $SCRIPT_DIR)."; exit 1; }

  if [ -L "$INSTALL_DIR" ]; then
    rm -f "$INSTALL_DIR"
  elif [ -d "$INSTALL_DIR" ]; then
    warn "$INSTALL_DIR já existia como diretório real — movendo para ${INSTALL_DIR}.bak antes de ligar o --dev"
    rm -rf "${INSTALL_DIR:?}.bak"
    mv "$INSTALL_DIR" "${INSTALL_DIR}.bak"
  fi
  ln -s "$SCRIPT_DIR" "$INSTALL_DIR"
  log "modo dev: $INSTALL_DIR -> $SCRIPT_DIR (symlink)"
else
  if [ -L "$INSTALL_DIR" ]; then
    warn "$INSTALL_DIR era um symlink de --dev — trocando por um clone real"
    rm -f "$INSTALL_DIR"
  fi
  if [ -d "$INSTALL_DIR/.git" ]; then
    log "instalação existente encontrada — atualizando (git pull)..."
    git -C "$INSTALL_DIR" pull --ff-only
  elif [ -d "$INSTALL_DIR" ]; then
    warn "$INSTALL_DIR existe mas não é um repositório git — movendo para ${INSTALL_DIR}.bak"
    rm -rf "${INSTALL_DIR:?}.bak"
    mv "$INSTALL_DIR" "${INSTALL_DIR}.bak"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  else
    log "clonando takeshot em $INSTALL_DIR..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
fi

# ---------------------------------------------------------------------------
# 5. launcher

chmod +x "$INSTALL_DIR/bin/takeshot"
ln -sf "$INSTALL_DIR/bin/takeshot" "$BIN_PATH"
log "launcher: $BIN_PATH -> $INSTALL_DIR/bin/takeshot"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR não está no seu PATH — adicione ao rc do seu shell, ex.:"
     warn "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc" ;;
esac

# ---------------------------------------------------------------------------
# 6. ícones — PNGs pré-gerados e commitados, install.sh não depende de ImageMagick

for size in 16 24 32 48 64 128 256; do
  src="$INSTALL_DIR/assets/hicolor/${size}x${size}/apps/$APP_ID.png"
  if [ -f "$src" ]; then
    mkdir -p "$ICON_DEST/${size}x${size}/apps"
    cp -f "$src" "$ICON_DEST/${size}x${size}/apps/$APP_ID.png"
  fi
done
mkdir -p "$ICON_DEST/scalable/apps"
svg_src="$INSTALL_DIR/assets/hicolor/scalable/apps/$APP_ID.svg"
[ -f "$svg_src" ] && cp -f "$svg_src" "$ICON_DEST/scalable/apps/$APP_ID.svg"
gtk-update-icon-cache -f -t "$ICON_DEST" >/dev/null 2>&1 || true
log "ícones instalados em $ICON_DEST"

# ---------------------------------------------------------------------------
# 7. .desktop — renderiza @BIN@ -> caminho real (sem sed, um replace simples em Python)

render_template() {
  "$PYTHON_BIN" -c "
import pathlib, sys
src, dst, bin_path = sys.argv[1], sys.argv[2], sys.argv[3]
text = pathlib.Path(src).read_text(encoding='utf-8')
pathlib.Path(dst).write_text(text.replace('@BIN@', bin_path), encoding='utf-8')
" "$1" "$2" "$BIN_PATH"
}

mkdir -p "$APPLICATIONS_DIR"
render_template "$INSTALL_DIR/data/$APP_ID.desktop.in" "$APPLICATIONS_DIR/$APP_ID.desktop"
update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
log ".desktop instalado em $APPLICATIONS_DIR/$APP_ID.desktop"

# ---------------------------------------------------------------------------
# 8. autostart

if [ "$NO_AUTOSTART" = "1" ]; then
  rm -f "$AUTOSTART_DIR/$APP_ID.Daemon.desktop"
  log "autostart desabilitado (--no-autostart)"
else
  mkdir -p "$AUTOSTART_DIR"
  render_template "$INSTALL_DIR/data/$APP_ID.Daemon.desktop.in" "$AUTOSTART_DIR/$APP_ID.Daemon.desktop"
  log "autostart instalado em $AUTOSTART_DIR/$APP_ID.Daemon.desktop"
fi

# ---------------------------------------------------------------------------
# 9. atalho de teclado global — idempotente, indexado por comando (nunca sobrescreve outro app)

if [ "$NO_SHORTCUT" = "1" ]; then
  log "atalho de teclado pulado (--no-shortcut)"
else
  SHORTCUT_ARGS=()
  [ "$FORCE" = "1" ] && SHORTCUT_ARGS+=(--force)
  "$BIN_PATH" --standalone shortcut install "${SHORTCUT_ARGS[@]}" || warn "falha ao instalar o atalho — rode 'takeshot shortcut install' manualmente."
fi

# ---------------------------------------------------------------------------
# 10. aplica o upgrade a uma instância residente já rodando (sem logout/login)

RUNNING="$(PYTHONPATH="$INSTALL_DIR/src" "$PYTHON_BIN" -c "
from takeshot.bus import describe_owner
print('yes' if describe_owner('$APP_ID') else 'no')
" 2>/dev/null || echo no)"

if [ "$RUNNING" = "yes" ]; then
  log "substituindo a instância residente em execução pela versão atualizada..."
  nohup "$BIN_PATH" --replace --daemon >/dev/null 2>&1 &
  disown || true
elif [ "$NO_AUTOSTART" != "1" ]; then
  log "iniciando o daemon residente..."
  nohup "$BIN_PATH" --daemon >/dev/null 2>&1 &
  disown || true
fi

# ---------------------------------------------------------------------------
echo
log "takeshot instalado/atualizado com sucesso em $INSTALL_DIR."
echo "  • pressione Print para capturar uma região (ou o binding mostrado acima, se houve conflito)."
echo "  • 'takeshot doctor' diagnostica o ambiente caso algo não funcione."
echo "  • se o ícone não aparecer no dash/dock, saia e entre na sessão (cache do GNOME Shell)."
echo "  • para desinstalar: $INSTALL_DIR/uninstall.sh"
