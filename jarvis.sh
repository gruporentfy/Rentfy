#!/bin/bash
# Arranca Jarvis. La primera vez macOS pedirá permiso para usar el micrófono: acéptalo.
cd "$(dirname "$0")"
if [ ! -f .venv/bin/activate ]; then
  echo "Jarvis no está instalado todavía. Ejecuta primero:  bash instalar_mac.sh"
  exit 1
fi
source .venv/bin/activate
[ -f .env ] && source .env
exec python -m cerebro "$@"
