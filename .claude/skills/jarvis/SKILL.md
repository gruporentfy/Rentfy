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
  cerebro.py         Cerebro = Jarvis: personalidad (INSTRUCCIONES_CEREBRO) y herramientas propias
                     (delegar, actualizar_perfil, crear/borrar_recordatorio, configurar_rutina,
                     crear_especialista, ver_tiempo, ver_calendario). Una sola conversación
                     compartida por voz, web, Siri y rutinas, protegida con un RLock.
                     ejecutar_rutina(): "sueno" consolida memorias; el resto llama a pensar("[RUTINA x] ...").
  agente.py          Agente base: bucle manual de tool use (con pause_turn), herramientas de memoria
                     y registros, búsqueda web opcional, tool calls en paralelo, consolidar() con
                     salida JSON estructurada
  memoria.py         SQLite por agente en datos/<agente>/memoria.db: aprendizajes, historial,
                     registros (datos con números) y feedback
  compartido.py      Perfil (datos/perfil.json), Rutinas (datos/rutinas.json), Recordatorios
                     (datos/recordatorios.db) y Avisos (en memoria, para la app)
  especialistas.py   ESPECIALISTAS = {nombre: {rol, instrucciones, web?, calendario?}}; los creados
                     por voz se guardan en datos/especialistas.json
  externos.py        tiempo() con Open-Meteo y eventos_calendario() con un enlace iCal
  programador.py     Hilo que cada 20 s dispara recordatorios vencidos y rutinas (ventana de 30 min)
  notificaciones.py  Avisa por la app (Avisos), una notificación del Mac (osascript), ntfy y la voz
  servidor.py        FastAPI con contraseña (Bearer, cookie o ?token=): /, /panel, /api/mensaje,
                     /api/siri (texto plano), /api/audio, /api/voz, /api/avisos, /api/panel,
                     /api/rutina, borrados; manifest e iconos públicos
  web/               index.html (reactor, avisos y app instalable) y panel.html
  voz/               oido.py (faster-whisper), habla.py (`say` + filtro, con lock), filtro.py,
                     activacion.py (openWakeWord "hey_jarvis" + modo conversación)
  jarvis.py          Arranque: programador + escucha + uvicorn
instalar_mac.sh      .venv (uv con Python 3.12 si hace falta), modelos y .env (clave,
                     JARVIS_TOKEN y JARVIS_NTFY generados)
conectar_iphone.sh   `tailscale serve`, enlace privado, ntfy y pasos del atajo de Siri (iphone.txt)
arranque_automatico.sh  LaunchAgent com.jarvis.asistente (log en datos/jarvis.log)
```

### Decisiones de la API de Claude (no las cambies sin motivo)

- Modelo `claude-opus-5-5`, effort `low` para Cerebro (rapidez en voz) y `medium` para los
  especialistas.
- `client.beta.messages.create` con `betas=["server-side-fallback-2026-07-01",
  "thinking-binding-controls-2026-08-01"]`, `fallbacks="default"` y
  `thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}`.
- **Pensamiento preservado:**
  - El `system` y las `tools` de Cerebro se congelan al empezar cada sesión
    (`_system_sesion` / `_tools_sesion`). Nunca los reconstruyas a mitad de sesión.
  - La hora va dentro de cada mensaje del usuario (`marca_temporal()`).
  - El historial solo crece; para "limpiar", empieza una sesión nueva. Pasa sola tras
    `JARVIS_MINUTOS_SESION` sin hablar, o tras crear un especialista.
- **No uses** `tool_choice` `any`/`tool` (en Opus 5.5 devuelve 400) ni `budget_tokens`, y no
  desactives el thinking.
- Añade siempre `response.content` completo al historial.
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
| Puerto ocupado | ¿Está el arranque automático activo? `bash arranque_automatico.sh quitar`, o `JARVIS_PUERTO=8766` |
| El iPhone no conecta | Tailscale activo en ambos y misma cuenta; repetir `bash conectar_iphone.sh`; HTTPS activado en Tailscale |
| 401 en el iPhone o en Siri | Volver a abrir el enlace con `?token=` de iphone.txt; cabecera `Authorization: Bearer <token>` en el atajo |
| No llegan avisos al iPhone | App ntfy suscrita al tema de `JARVIS_NTFY` (.env) |
| No suena la rutina | El Mac debe estar encendido a esa hora (ventana de 30 min); revisar el panel y datos/jarvis.log |
| El calendario no sale | Comprobar `JARVIS_CALENDARIO` (enlace secreto iCal; los webcal:// se aceptan) |

Para diagnosticar, ejecuta el comando que falla y lee la salida completa antes de cambiar código.

## Añadir un especialista

1. Añade una entrada en `ESPECIALISTAS` (`cerebro/especialistas.py`) con `rol` (una línea) e
   `instrucciones`: qué hace, qué debe aprender del usuario y en qué formato entrega.
2. No hace falta nada más: Cerebro lo añade al enum de `delegar` y `Memoria` crea su carpeta.
3. Ejecuta las pruebas; el test de estado del servidor lista los agentes.

## Hoja de ruta

Ya hechas las fases 1 a 5:
1. Voz en el Mac.
2. iPhone y Apple Watch con Tailscale, contraseña, app instalable y atajo de Siri.
3. Rutinas editables y avisos.
4. Perfil, registros, recordatorios, "sueño" y panel.
5. Tiempo, calendario iCal, búsqueda web y especialistas por voz.

Pendiente (propón el plan al usuario antes de empezar):
- **Gmail:** requiere OAuth en Google Cloud. Explícale los pasos y su coste, que es cero.
- **"Oye, Jarvis":** entrenar un modelo propio de openWakeWord (cuaderno oficial en Colab) y
  apuntar `JARVIS_ACTIVACION` a su `.onnx`.
- **Voz clonada:** solo con consentimiento (F5-TTS-MLX o XTTS-v2 en local). Va como otra clase
  con la interfaz de `Voz` (`sintetizar`, `decir`).
- **Respuestas en streaming:** para que empiece a hablar antes de terminar de pensar.
- **Pasarlo a la nube:** para que funcione con el Mac apagado.
