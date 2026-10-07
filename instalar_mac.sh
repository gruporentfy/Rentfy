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
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
  echo "Reutilizando el entorno de Jarvis ya creado ($(.venv/bin/python --version))"
elif [ -n "$PY" ]; then
  rm -rf .venv
  echo "Usando $($PY --version)"
  $PY -m venv .venv
else
  # El Python del Mac es antiguo: descargamos uno moderno solo para Jarvis con "uv"
  # (no necesita contraseña de administrador ni toca el resto del sistema).
  rm -rf .venv
  echo "Tu Python es antiguo; descargando Python 3.12 solo para Jarvis..."
  UV="$HOME/.local/bin/uv"
  if ! command -v uv >/dev/null && [ ! -x "$UV" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  fi
  command -v uv >/dev/null && UV="$(command -v uv)"
  "$UV" venv --seed --python 3.12 .venv
fi
source .venv/bin/activate
echo
echo "== Instalando librerías (la primera vez tarda 3-5 minutos; no cierres la ventana) =="
pip install -q --upgrade pip
pip install --progress-bar on -e ".[voz]" | grep -E "^(Collecting|Successfully installed)" || true
python -c "import cerebro, faster_whisper, openwakeword, sounddevice" \
  || { echo "La instalación de librerías falló. Copia lo que aparece arriba y pídeme ayuda."; exit 1; }

echo "== Descargando modelos (oído y palabra de activación) =="
python -c "import openwakeword; openwakeword.utils.download_models(['hey_jarvis_v0.1'])"
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

touch .env && chmod 600 .env
# Si quedó guardada una clave que no es válida (p. ej. texto pegado por error), la quitamos.
if grep -q ANTHROPIC_API_KEY .env && ! grep -q 'ANTHROPIC_API_KEY="sk-ant-' .env; then
  grep -v ANTHROPIC_API_KEY .env > .env.tmp || true
  mv .env.tmp .env && chmod 600 .env
fi
if ! grep -q ANTHROPIC_API_KEY .env; then
  # Descartar lo que se haya tecleado o pegado mientras se instalaba.
  while read -r -t 1 -n 10000 _ < /dev/tty; do :; done 2>/dev/null || true
  CLAVE=""
  until [[ "$CLAVE" == sk-ant-* ]]; do
    echo
    echo "Pega tu clave de Claude (https://platform.claude.com > API Keys, empieza por sk-ant-) y pulsa Enter."
    echo "(Por seguridad no se verá nada al pegarla.)"
    read -rs CLAVE < /dev/tty
    CLAVE="$(echo "$CLAVE" | tr -d '[:space:]')"
    [[ "$CLAVE" == sk-ant-* ]] || echo "Eso no parece una clave de Claude. Inténtalo de nuevo."
  done
  printf 'export ANTHROPIC_API_KEY="%s"\n' "$CLAVE" >> .env
  echo "Clave guardada."
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
