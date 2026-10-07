# Jarvis 🧠🎙️

Tu asistente personal por voz, al estilo del J.A.R.V.I.S. de Iron Man. Le hablas, te responde
con su voz y gestiona tu día a día, tus negocios, entrenamientos, estudios y finanzas.

Por dentro, **Cerebro** es la mente de Jarvis: entiende lo que necesitas y da órdenes a un
equipo de especialistas. Cada uno tiene **su propia memoria**, aprende de ti y mejora cada día.

```
     🗣️ "Hey Jarvis..."           🖥️ Mac (siempre escuchando)   📱 iPhone   ⌚ Apple Watch (fase 2)
                 │
   ┌─────────────┴──────────────────────────────────────────────┐
   │  👂 Oído: Whisper (local, gratis)                           │
   │  🧠 CEREBRO ── delegar ──► agenda · negocios · marketing     │
   │                           finanzas · entrenamiento · estudios│
   │  🔊 Voz: voces de macOS + filtro "IA de película" (gratis)   │
   │  🗄️ Una memoria propia por agente (datos/<agente>/)          │
   └─────────────────────────────────────────────────────────────┘
```

## Instalación en Mac

```bash
git clone https://github.com/gruporentfy/Rentfy.git jarvis
cd jarvis
bash instalar_mac.sh     # instala todo, descarga los modelos y te pide la clave de Claude
./jarvis.sh              # arranca Jarvis
```

La primera vez macOS pedirá permiso para usar el micrófono: acéptalo.

Necesitas una clave de la API de Claude (https://platform.claude.com). Es lo único de pago,
según el uso. El oído, la voz y la palabra de activación funcionan en tu Mac, gratis y sin
internet.

**Voz más natural (gratis):** Ajustes del Sistema → Accesibilidad → Contenido leído → Voz del
sistema → Gestionar voces → Español (España) → descarga **Jorge (Mejorada)**. Jarvis la usará
automáticamente.

## Cómo se usa

- **Manos libres:** di **"Hey Jarvis"**, espera el pitido y habla. Cuando te responda, tienes
  unos segundos para seguir hablando sin repetir su nombre.
- **App web** (se abre sola en `http://localhost:8765`): mantén pulsado el reactor o la barra
  espaciadora para hablar, o escribe. Las respuestas largas (planes, textos) aparecen en
  "Ver detalle".
- **Modo texto en la terminal:** `./jarvis.sh texto`. Incluye comandos para ver y editar la
  memoria de cada agente (`/memoria marketing`, `/ensenar`, `/feedback`, `/olvidar`...).

Opciones: `./jarvis.sh --sin-escucha` (sin micrófono siempre activo), `--sin-navegador`.

## Cómo aprende cada agente

Cada agente guarda en `datos/<agente>/memoria.db`:

| Tabla          | Qué guarda                                                  |
| -------------- | ----------------------------------------------------------- |
| `aprendizajes` | Preferencias, objetivos, hábitos y datos que aprendió de ti |
| `historial`    | Las tareas que recibió y lo que respondió                   |
| `feedback`     | Tus valoraciones (1-5) para ajustar su forma de trabajar    |

En cada petición el agente lee su memoria, y decide solo qué guardar, buscar u olvidar.
`datos/` no se sube a GitHub: tus memorias se quedan en tu Mac.

## Configuración

Variables de entorno (puedes añadirlas a `.env` con `export NOMBRE=valor`):

| Variable                   | Por defecto       | Para qué                                               |
| -------------------------- | ----------------- | ------------------------------------------------------ |
| `JARVIS_VOZ`               | `Jorge`           | Voz de macOS (`say -v '?'` para verlas)                |
| `JARVIS_VELOCIDAD`         | `180`             | Palabras por minuto                                    |
| `JARVIS_EFECTO`            | `0.6`             | Filtro "IA" de 0 (voz natural) a 1 (muy robótica)      |
| `JARVIS_ACTIVACION`        | `hey_jarvis`      | Palabra de activación, o ruta a un modelo `.onnx` propio |
| `JARVIS_UMBRAL`            | `0.5`             | Sensibilidad de activación (más bajo = más sensible)   |
| `JARVIS_WHISPER`           | `small`           | Modelo del oído: `base` (rápido) … `medium` (preciso)  |
| `JARVIS_CIUDAD`            | `Bilbao`          |                                                        |
| `JARVIS_ZONA_HORARIA`      | `Europe/Madrid`   |                                                        |
| `CEREBRO_MODELO`           | `claude-opus-5-5` | Modelo de Claude                                       |
| `CEREBRO_ESFUERZO_CEREBRO` | `low`             | Cuánto piensa Jarvis antes de contestar (rapidez)      |
| `CEREBRO_ESFUERZO`         | `medium`          | Cuánto piensan los especialistas                       |

## Añadir un especialista

Añade una entrada en `cerebro/especialistas.py`; Cerebro lo detecta, le crea su memoria y ya
puede darle órdenes.

## Hoja de ruta

| Fase | Contenido                                                                 | Estado     |
| ---- | ------------------------------------------------------------------------- | ---------- |
| 1    | Jarvis en el Mac: "Hey Jarvis", oído, voz con filtro, app web              | ✅ Hecha    |
| 2    | iPhone y Apple Watch ("Oye Siri, Jarvis") desde cualquier sitio            | Pendiente  |
| 3    | Rutinas: resumen 7:30, repaso 21:30, revisión semanal (editables)         | Pendiente  |
| 4    | Memoria mejorada, registros (entrenos, gastos, estudio), recordatorios, panel | Pendiente |
| 5    | Google Calendar, Gmail, internet, especialistas nuevos por voz            | Pendiente  |
| —    | Palabra de activación "Oye, Jarvis" (modelo propio)                        | Pendiente  |
| —    | Voz clonada (solo de alguien que dé su permiso)                           | Opcional   |

## Estructura

```
cerebro/
  cerebro.py         Cerebro / Jarvis: personalidad, coordina y delega
  agente.py          Agente base: bucle con Claude + herramientas de memoria
  memoria.py         Almacenamiento SQLite por agente
  especialistas.py   El equipo
  servidor.py        API y app web
  web/index.html     La app (reactor para hablar)
  voz/oido.py        Voz -> texto (Whisper)
  voz/habla.py       Texto -> voz (macOS) 
  voz/filtro.py      Filtro "IA de película"
  voz/activacion.py  "Hey Jarvis" y escucha continua
  jarvis.py          Arranque
tests/               Pruebas (sin micrófono ni llamadas reales a la API)
```

## Pruebas

```bash
pip install -e ".[dev]" && pytest
```
