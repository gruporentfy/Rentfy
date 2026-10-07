#!/bin/bash
# Instala Jarvis en un Mac (Apple Silicon). Ejecuta:  bash instalar_mac.sh
set -e
cd "$(dirname "$0")"

echo "== Instalando Jarvis =="

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    PY="$c"; break
  fi
done
rm -rf .venv
if [ -n "$PY" ]; then
  echo "Usando $($PY --version)"
  $PY -m venv .venv
else
  # El Python del Mac es antiguo: descargamos uno moderno solo para Jarvis con "uv"
  # (no necesita contraseña de administrador ni toca el resto del sistema).
  echo "Tu Python es antiguo; descargando Python 3.12 solo para Jarvis..."
  UV="$HOME/.local/bin/uv"
  if ! command -v uv >/dev/null && [ ! -x "$UV" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  fi
  command -v uv >/dev/null && UV="$(command -v uv)"
  "$UV" venv --seed --python 3.12 .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -e ".[voz]"

echo "== Descargando modelos (oído y palabra de activación) =="
python -c "import openwakeword; openwakeword.utils.download_models(['hey_jarvis_v0.1'])"
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

touch .env && chmod 600 .env
if ! grep -q ANTHROPIC_API_KEY .env; then
  echo
  echo "Pega tu clave de Claude (https://platform.claude.com > API Keys) y pulsa Enter:"
  read -rs CLAVE
  printf 'export ANTHROPIC_API_KEY="%s"\n' "$CLAVE" >> .env
fi
# Contraseña para entrar desde el iPhone y el reloj, y canal privado de notificaciones.
grep -q JARVIS_TOKEN .env || printf 'export JARVIS_TOKEN="%s"\n' "$(python -c 'import secrets; print(secrets.token_urlsafe(24))')" >> .env
grep -q JARVIS_NTFY= .env || printf 'export JARVIS_NTFY="jarvis-%s"\n' "$(python -c 'import secrets; print(secrets.token_hex(8))')" >> .env

echo
echo "== Voces en español instaladas =="
say -v '?' | grep ' es_' || true
echo
echo "Consejo: para una voz más natural, descarga 'Jorge (Mejorada)' en"
echo "Ajustes del Sistema > Accesibilidad > Contenido leído > Voz del sistema > Gestionar voces."
echo
echo "Listo. Arranca Jarvis con:  ./jarvis.sh"
