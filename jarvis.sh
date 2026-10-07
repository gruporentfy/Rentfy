#!/bin/bash
# Arranca Jarvis. La primera vez macOS pedirá permiso para usar el micrófono: acéptalo.
cd "$(dirname "$0")"
source .venv/bin/activate
[ -f .env ] && source .env
exec python -m cerebro "$@"
