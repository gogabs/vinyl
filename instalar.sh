#!/bin/bash
# Empacota o Vinyl com a biblioteca Python do Mage Core e instala no console.
#
#   ./instalar.sh [host-ssh] [pasta-do-sdk]
#   padrão: r36s e ../r36s-a11y-sdk (clone de github.com/gogabs/r36s-a11y-sdk),
#   ou a cópia de reserva em r36s_a11y/ (veja SDK-ORIGIN.md)
#
# O mpv vem do instalador da plataforma (r36s-a11y, instalar/console/setup.sh).
# Com o Vinyl aberto, não instala.
set -euo pipefail
HOST=${1:-r36s}
HERE=$(cd "$(dirname "$0")" && pwd)
if [ "$#" -ge 2 ]; then
  SDK_PY="$2/python/r36s_a11y"
else
  SDK_PY="$HERE/../r36s-a11y-sdk/python/r36s_a11y"
  [ -d "$SDK_PY" ] || SDK_PY="$HERE/r36s_a11y"
fi
[ -d "$SDK_PY" ] || { echo "Mage Core não encontrado: $SDK_PY"; exit 1; }
echo "Mage Core selecionado: $SDK_PY"

if ssh "$HOST" 'for p in /proc/[0-9]*; do readlink "$p/cwd"; done 2>/dev/null | grep -Eq "^/(roms|opt)/a11y/games/vinyl(/|$)"'; then
  echo "O Vinyl está aberto no console. Feche e rode de novo."
  exit 1
fi

PKG=$(mktemp -d)
trap 'rm -rf "$PKG"' EXIT
mkdir -p "$PKG/vinyl"
cp -r "$HERE/game.json" "$HERE/main.py" "$HERE/vinyl" "$SDK_PY" "$PKG/vinyl/"
find "$PKG" -name __pycache__ -prune -exec rm -rf {} +

tar -C "$PKG" -czf - vinyl | ssh "$HOST" '
  set -e; mkdir -p /roms/a11y/games /roms/audiolivros /roms/musica; cd /roms/a11y/games
  rm -rf .vinyl.novo && mkdir .vinyl.novo
  tar -xzmf - -C .vinyl.novo
  rm -rf vinyl && mv .vinyl.novo/vinyl . && rmdir .vinyl.novo
  if command -v mpv >/dev/null; then echo "mpv: $(mpv --version | head -1)"; else echo "Aviso: falta o mpv no console"; fi
  echo "Vinyl instalado"; df -h /roms | tail -1'
