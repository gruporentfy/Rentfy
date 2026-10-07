#!/bin/bash
# Hace que Jarvis arranque solo cada vez que enciendes el Mac (para que no se pierda las rutinas).
#   bash arranque_automatico.sh          -> activar
#   bash arranque_automatico.sh quitar   -> desactivar
set -e
cd "$(dirname "$0")"
PLIST="$HOME/Library/LaunchAgents/com.jarvis.asistente.plist"

if [ "$1" = "quitar" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Arranque automático desactivado."
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" datos
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.jarvis.asistente</string>
  <key>ProgramArguments</key>
  <array><string>$PWD/jarvis.sh</string><string>--sin-navegador</string></array>
  <key>WorkingDirectory</key><string>$PWD</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$PWD/datos/jarvis.log</string>
  <key>StandardErrorPath</key><string>$PWD/datos/jarvis.log</string>
</dict>
</plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Listo: Jarvis arrancará solo al iniciar sesión en el Mac."
echo "Registro: datos/jarvis.log   ·   Para desactivarlo: bash arranque_automatico.sh quitar"
echo "Si macOS pide permiso de micrófono para 'python', acéptalo."
