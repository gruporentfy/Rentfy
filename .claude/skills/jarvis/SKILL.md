---
name: jarvis
description: Construir, instalar, arrancar, depurar y ampliar Jarvis, el asistente personal por voz de este repositorio (Cerebro + especialistas con memoria propia, voz local en macOS, app web). Úsala para cualquier tarea sobre Jarvis o Cerebro, como instalarlo en el Mac, arreglar errores de instalación o del micrófono, ajustar la voz, añadir un especialista, avanzar a la siguiente fase de la hoja de ruta (iPhone/Apple Watch, rutinas, memoria, integraciones) o cambiar su personalidad.
---

# Jarvis

Asistente personal por voz al estilo J.A.R.V.I.S. de Iron Man. El usuario es Héctor: vive en
Bilbao (zona Europe/Madrid), usa un **Mac M2**, un **iPhone** y un **Apple Watch**. Escribe
en español: respóndele en español, claro y sin jerga técnica.

## Reglas de trabajo con el usuario

- **Antes de construir algo nuevo, enséñale el plan** (un diagrama sencillo y los pasos) y
  espera su visto bueno. Un arreglo pequeño o un error de instalación se resuelve directamente.
- **Prioridad: que sea gratis.** Lo único de pago es la API de Claude. Para todo lo demás (voz,
  oído, activación, conexión remota) elige primero una opción local o gratuita.
- **Nunca clones la voz de una persona real sin su consentimiento.** Eso incluye a actores o
  dobladores, como la voz de JARVIS en las películas. Sí se puede clonar la voz del propio
  usuario o de alguien que dé su permiso.
- Haz commit y push al terminar cada cambio que funcione, y mantén el README al día (sobre todo
  la tabla de la hoja de ruta).

## Arquitectura

```
cerebro/
  cerebro.py         Cerebro = Jarvis: personalidad (INSTRUCCIONES_CEREBRO), herramienta
                     `delegar`, historial de la sesión con un lock (voz, web y reloj comparten
                     una sola conversación). separar_detalle() divide en (hablado, "DETALLE:")
  agente.py          Agente base: bucle manual de tool use con Claude, herramientas de memoria
                     (guardar_aprendizaje, buscar_memoria, olvidar), las tool calls de un mismo
                     turno se ejecutan en paralelo, y Rechazo para stop_reason == "refusal"
  memoria.py         SQLite por agente en datos/<agente>/memoria.db: aprendizajes, historial
                     y feedback. contexto() se inyecta en el system prompt
  especialistas.py   ESPECIALISTAS = {nombre: {rol, instrucciones}}: agenda, negocios,
                     marketing, finanzas, entrenamiento, estudios
  config.py          Config (dataclass) leída de variables de entorno JARVIS_* y CEREBRO_*
  servidor.py        FastAPI: GET /, GET /api/estado, POST /api/mensaje {texto},
                     POST /api/audio (archivo), POST /api/voz {texto} -> WAV, POST /api/nueva
  web/index.html     App web: el reactor se mantiene pulsado (o la barra espaciadora) para
                     hablar; usa la voz del navegador si no hay voz local
  voz/oido.py        faster-whisper (modelo "small", int8, CPU, idioma "es")
  voz/habla.py       `say` de macOS + filtro, con elección automática de la mejor voz es_ES
                     instalada; decir() prepara la frase siguiente mientras suena la actual
  voz/filtro.py      Efecto "IA de película" en numpy (peine, paso alto y sala); no imita a nadie
  voz/activacion.py  openWakeWord "hey_jarvis" + grabación por energía con ruido adaptativo
                     + modo conversación de unos 5 s después de cada respuesta
  jarvis.py          Arranque: uvicorn + hilo de escucha + saludo; modo `texto` -> cli.py
instalar_mac.sh      Crea .venv (usa uv con Python 3.12 si el Python del sistema es menor
                     que 3.10), instala ".[voz]", descarga los modelos y guarda la clave en .env
jarvis.sh            Activa .venv, carga .env y ejecuta `python -m cerebro "$@"`
```

### Decisiones de la API de Claude (no las cambies sin motivo)

- Modelo `claude-opus-5-5`, `thinking: {type: "adaptive"}` y `output_config.effort`: `low` para
  Cerebro (rapidez en voz) y `medium` para los especialistas.
- `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`.
- **No uses** `tool_choice` `any`/`tool` (en Opus 5.5 devuelve 400) ni `budget_tokens`, y no
  desactives el thinking.
- El system prompt va en dos bloques: el estable con `cache_control` y la memoria detrás.
- Añade siempre `response.content` completo al historial, no solo el texto.
- Ante cualquier duda sobre la API, carga la skill `claude-api` antes de escribir código.

## Comandos

```bash
bash instalar_mac.sh            # instalar o reinstalar
./jarvis.sh                     # todo: web + "Hey Jarvis" + voz
./jarvis.sh --sin-escucha       # solo la app web
./jarvis.sh texto               # terminal con /memoria, /ensenar, /feedback, /olvidar, /directo
source .venv/bin/activate && pip install -e ".[dev]" && pytest   # pruebas
say -v '?' | grep es_           # voces en español instaladas
```

Las pruebas no usan micrófono, macOS ni la API real: `tests/test_cerebro.py` define
`ClienteFalso`, `resp()`, `texto()` y `herramienta()` para guionizar respuestas de Claude.
Toda funcionalidad nueva lleva su prueba con ese patrón.

## Diagnóstico de problemas frecuentes en el Mac

| Síntoma | Causa y solución |
| --- | --- |
| "Necesitas Python 3.10" o `.venv/bin/activate: No such file` | Falló la instalación: `git pull && bash instalar_mac.sh` |
| "Falta la clave de Claude" | Edita `.env` con `export ANTHROPIC_API_KEY="..."` (permisos 600) |
| No reacciona a "Hey Jarvis" | Ajustes → Privacidad → Micrófono → activar Terminal; bajar `JARVIS_UMBRAL` (p. ej. 0.3) |
| Se activa solo | Subir `JARVIS_UMBRAL` (0.6–0.7) |
| Corta la frase o espera demasiado | `silencio_fin` / `espera_inicio` en `Escucha.grabar_frase` |
| La voz suena mal o en otro idioma | Descargar "Jorge (Mejorada)" en Accesibilidad → Contenido leído; `JARVIS_VOZ` |
| Demasiado robótico o demasiado plano | `JARVIS_EFECTO` entre 0 y 1 |
| Tarda en contestar | `JARVIS_WHISPER=base`; `CEREBRO_ESFUERZO_CEREBRO=low`; revisar si está delegando |
| Puerto ocupado | `JARVIS_PUERTO=8766 ./jarvis.sh` |

Para diagnosticar, ejecuta el comando que falla y lee la salida completa antes de cambiar código.

## Añadir un especialista

1. Añade una entrada en `ESPECIALISTAS` (`cerebro/especialistas.py`) con `rol` (una línea) e
   `instrucciones`: qué hace, qué debe aprender del usuario y en qué formato entrega.
2. No hace falta nada más: Cerebro lo añade al enum de `delegar` y `Memoria` crea su carpeta.
3. Ejecuta las pruebas; el test de estado del servidor lista los agentes.

## Hoja de ruta (estado en el README)

1. ✅ **Fase 1:** Jarvis en el Mac (voz, oído, "Hey Jarvis", app web).
2. **Fase 2, iPhone y Apple Watch:**
   - Acceso remoto gratis con **Tailscale** (`tailscale serve` para tener HTTPS, necesario para
     el micrófono en Safari).
   - **Token** obligatorio en la API en cuanto deje de escuchar solo en `127.0.0.1`.
   - **Atajo de Siri "Jarvis":** Dictar texto → Obtener contenido de URL
     (POST `/api/mensaje`) → Leer en voz alta `respuesta`. Funciona en el Watch.
   - App web instalable en el iPhone (manifest + iconos).
3. **Fase 3, rutinas:**
   - Resumen a las 7:30 (tiempo de Bilbao con Open-Meteo, gratis y sin clave), repaso a las
     21:30 y revisión los domingos.
   - Horarios editables por voz; se guardan en la memoria de Cerebro o en un archivo de config.
   - Avisos: voz en el Mac y notificación (web push o ntfy).
4. **Fase 4, memoria mejorada:**
   - Perfil compartido entre agentes.
   - Registros con números: entrenos, gastos, ventas y horas de estudio.
   - "Sueño" nocturno: cada agente consolida, deduplica y saca conclusiones del feedback.
   - Recordatorios y panel de progreso.
5. **Fase 5, integraciones:**
   - Google Calendar y Gmail.
   - Búsqueda web (`web_search_20260209`) para marketing y estudios.
   - Crear especialistas nuevos por voz.

**Extras:**
- **"Oye, Jarvis":** entrenar un modelo propio de openWakeWord (cuaderno oficial en Colab) y
  apuntar `JARVIS_ACTIVACION` a su `.onnx`.
- **Voz clonada:** solo con consentimiento (F5-TTS-MLX o XTTS-v2 en local); implementarla como
  otra clase con la interfaz de `Voz` (`sintetizar`, `decir`).
