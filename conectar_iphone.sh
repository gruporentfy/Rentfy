#!/bin/bash
# Conecta Jarvis con tu iPhone y tu Apple Watch desde cualquier sitio, gratis y de forma privada,
# usando Tailscale (una red privada solo entre tus dispositivos).
#
# Antes de ejecutarlo:
#   1. Instala Tailscale en el Mac (App Store o https://tailscale.com/download) e inicia sesión.
#   2. Instala Tailscale en el iPhone e inicia sesión con la MISMA cuenta.
set -e
cd "$(dirname "$0")"
[ -f .env ] && source .env

TS=""
for c in tailscale /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then TS="$c"; break; fi
done
if [ -z "$TS" ]; then
  echo "No encuentro Tailscale. Instálalo desde la App Store o https://tailscale.com/download,"
  echo "inicia sesión y vuelve a ejecutar este script."
  exit 1
fi

PUERTO="${JARVIS_PUERTO:-8765}"
echo "== Publicando Jarvis en tu red privada de Tailscale =="
echo "(Si te pide activar HTTPS en tu cuenta de Tailscale, abre el enlace que muestre y acepta.)"
"$TS" serve --bg "$PUERTO"

DOMINIO=$("$TS" status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
URL="https://$DOMINIO/?token=$JARVIS_TOKEN"

cat > iphone.txt <<TXT
JARVIS EN TU IPHONE Y APPLE WATCH
=================================

1) App en el iPhone
   Abre este enlace en Safari (con Tailscale activado en el iPhone):
   $URL
   Después: botón Compartir -> "Añadir a pantalla de inicio".

2) Avisos en el iPhone (resumen de la mañana, recordatorios...)
   Instala la app gratuita "ntfy" desde la App Store, pulsa + y suscríbete al tema:
   ${JARVIS_NTFY}

3) Atajo de Siri "Jarvis" (iPhone y Apple Watch)
   App Atajos -> + -> añade estas acciones:
     a. "Dictar texto"            (Idioma: Español (España); Dejar de escuchar: Tras pausa)
     b. "Obtener contenido de URL"
          URL:      https://$DOMINIO/api/siri
          Método:   POST
          Cabeceras: Authorization = Bearer $JARVIS_TOKEN
          Cuerpo:   JSON -> clave "texto" (Texto) = Texto dictado
     c. "Leer texto"  -> Contenido de la URL
   Llama al atajo "Jarvis" y activa "Mostrar en el Apple Watch" en sus detalles.
   Uso: "Oye Siri, Jarvis" -> hablas -> te responde.
TXT

echo
cat iphone.txt
echo
echo "(Guardado también en iphone.txt; no lo compartas: contiene tu contraseña.)"

if [ -n "$JARVIS_NTFY" ]; then
  curl -s -H "Title: Jarvis" -H "Click: $URL" -d "Pulsa aquí para abrir Jarvis en el iPhone" \
    "${JARVIS_NTFY_SERVIDOR:-https://ntfy.sh}/$JARVIS_NTFY" >/dev/null \
    && echo "Si ya tienes ntfy suscrito, te he enviado el enlace al iPhone."
fi
