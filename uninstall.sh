#!/usr/bin/env bash
# Remove o takeshot instalado por install.sh. Idempotente — pode rodar mesmo
# se a instalação já estiver parcialmente removida.
#
# Uso: uninstall.sh [--purge] [--prefix=DIR]
#   --purge   também remove config/estado (~/.config/takeshot, ~/.local/state/takeshot)
set -euo pipefail

APP_ID="com.danielbarcelos.Takeshot"
PREFIX="${TAKESHOT_PREFIX:-$HOME/.local}"
PURGE=0

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --prefix=*) PREFIX="${arg#--prefix=}" ;;
    -h|--help)
      echo "Uso: uninstall.sh [--purge] [--prefix=DIR]"
      echo "  --purge  também remove config/estado (~/.config/takeshot, ~/.local/state/takeshot)"
      exit 0
      ;;
    *) echo "opção desconhecida: $arg" >&2; exit 1 ;;
  esac
done

INSTALL_DIR="$PREFIX/share/takeshot"
BIN_PATH="$PREFIX/bin/takeshot"
ICON_DEST="$PREFIX/share/icons/hicolor"
APPLICATIONS_DIR="$PREFIX/share/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
PYTHON_BIN="$(command -v python3 || true)"

if [ -x "$BIN_PATH" ]; then
  log "removendo atalho de teclado..."
  "$BIN_PATH" --standalone shortcut remove || true

  if [ -n "$PYTHON_BIN" ] && [ -d "$INSTALL_DIR/src" ]; then
    log "encerrando instância residente, se houver..."
    PYTHONPATH="$INSTALL_DIR/src" "$PYTHON_BIN" -c "
import os, signal
from takeshot.bus import describe_owner
info = describe_owner('$APP_ID')
if info and info.get('pid'):
    os.kill(info['pid'], signal.SIGTERM)
" 2>/dev/null || true
  fi
fi

rm -f "$BIN_PATH"
rm -f "$APPLICATIONS_DIR/$APP_ID.desktop"
rm -f "$AUTOSTART_DIR/$APP_ID.Daemon.desktop"
for size in 16 24 32 48 64 128 256; do
  rm -f "$ICON_DEST/${size}x${size}/apps/$APP_ID.png"
done
rm -f "$ICON_DEST/scalable/apps/$APP_ID.svg"
gtk-update-icon-cache -f -t "$ICON_DEST" >/dev/null 2>&1 || true
update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true

if [ -L "$INSTALL_DIR" ]; then
  rm -f "$INSTALL_DIR"
  log "removido symlink de dev: $INSTALL_DIR"
elif [ -d "$INSTALL_DIR" ]; then
  rm -rf "$INSTALL_DIR"
  log "removido: $INSTALL_DIR"
else
  log "$INSTALL_DIR já não existia"
fi

if [ "$PURGE" = "1" ]; then
  rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/takeshot"
  rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/takeshot"
  log "config/estado removidos (--purge)"
else
  log "config preservada em ${XDG_CONFIG_HOME:-$HOME/.config}/takeshot (rode com --purge para remover)"
fi

echo
log "takeshot desinstalado."
