#!/usr/bin/env bash
# Gera os ícones hicolor pré-empacotados a partir de assets/icon-source.png.
#
# Só roda em dev — install.sh NUNCA depende disto nem de ImageMagick no
# destino; os PNGs/SVG gerados aqui ficam commitados no repositório.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/icon-source.png"
OUT="$SCRIPT_DIR/hicolor"
APP_ID="com.danielbarcelos.Takeshot"

command -v convert >/dev/null 2>&1 || {
  echo "ImageMagick ('convert') não encontrado — instale para regenerar os ícones." >&2
  exit 1
}
[ -f "$SRC" ] || { echo "fonte não encontrada: $SRC" >&2; exit 1; }

for size in 16 24 32 48 64 128 256; do
  dir="$OUT/${size}x${size}/apps"
  mkdir -p "$dir"
  convert "$SRC" -filter Lanczos -resize "${size}x${size}" "$dir/$APP_ID.png"
  echo "gerado: $dir/$APP_ID.png"
done

mkdir -p "$OUT/scalable/apps"
B64="$(base64 -w0 "$SRC")"
cat > "$OUT/scalable/apps/$APP_ID.svg" <<SVG
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <image width="256" height="256" href="data:image/png;base64,$B64"/>
</svg>
SVG
echo "gerado: $OUT/scalable/apps/$APP_ID.svg"
echo
echo "pronto — commit os arquivos gerados em assets/hicolor/. install.sh nunca gera ícones em tempo de instalação."
