# Jarvis 🧠🎙️

Tu asistente personal por voz, al estilo del J.A.R.V.I.S. de Iron Man. Le hablas desde el Mac,
el iPhone o el Apple Watch, te responde con su voz y gestiona tu día a día, tus negocios,
entrenamientos, estudios y finanzas. Y también te habla él primero: resumen por la mañana,
repaso por la noche y recordatorios.

Por dentro, **Cerebro** es la mente de Jarvis: entiende lo que necesitas y da órdenes a un
equipo de especialistas. Cada uno tiene **su propia memoria**, aprende de ti y mejora cada día.

```
  🖥️ Mac "Hey Jarvis"      📱 iPhone (app + avisos)      ⌚ Apple Watch "Oye Siri, Jarvis"
          │                        └──── Tailscale (red privada, gratis) ────┘
  ┌───────┴────────────────────────────────────────────────────────────────┐
  │ TU MAC                                                                  │
  │  👂 Whisper (local)   🔊 voz de macOS + filtro "IA"   🔒 contraseña       │
  │  🧠 CEREBRO ── delegar ──► agenda · negocios · marketing · finanzas      │
  │        │                   entrenamiento · estudios · (+ los que crees)  │
  │        ├─ perfil compartido · recordatorios · tiempo · tu calendario     │
  │  ⏰ Rutinas: 07:30 resumen · 21:30 repaso · domingo revisión · 03:30 sueño│
  │  🗄️ Una memoria propia por agente: recuerdos, registros, valoraciones     │
  └─────────────────────────────────────────────────────────────────────────┘
```

## 1. Instalación en el Mac

```bash
git clone -b claude/friendly-noether-jsll8e https://github.com/gruporentfy/Rentfy.git jarvis
cd jarvis
bash instalar_mac.sh     # instala todo (también Python si hace falta) y te pide la clave de Claude
./jarvis.sh              # arranca Jarvis
```

- La primera vez macOS pedirá permiso para usar el micrófono: acéptalo.
- La clave de Claude se crea en https://platform.claude.com (API Keys). Es lo único de pago,
  según el uso. Oído, voz, activación, avisos y conexión con el iPhone son gratis.
- **Voz más natural (gratis):** Ajustes del Sistema → Accesibilidad → Contenido leído → Voz del
  sistema → Gestionar voces → Español (España) → **Jorge (Mejorada)**.
- **Que arranque solo al encender el Mac** (recomendado para no perderse las rutinas):
  `bash arranque_automatico.sh` (para quitarlo: `bash arranque_automatico.sh quitar`). Con el
  arranque automático activo no lances además `./jarvis.sh` (ocuparían el mismo puerto).

## 2. iPhone y Apple Watch

1. Instala **Tailscale** (gratis) en el Mac y en el iPhone, con la misma cuenta.
2. En el Mac: `bash conectar_iphone.sh`. Te muestra (y guarda en `iphone.txt`) tu enlace
   privado y los pasos para:
   - **App en el iPhone:** abre el enlace en Safari → Compartir → Añadir a pantalla de inicio.
   - **Avisos push:** app gratuita **ntfy** → suscribirse al tema que te indica.
   - **Apple Watch / Siri:** un atajo "Jarvis" de 3 acciones (Dictar texto → Obtener contenido
     de URL → Leer texto). Luego: *"Oye Siri, Jarvis"*.

## 3. Cómo se usa

- **Manos libres en el Mac:** di **"Hey Jarvis"**, espera el pitido y habla. Tras responder,
  tienes unos segundos para seguir sin repetir su nombre.
- **App** (Mac: `http://localhost:8765`, o la del iPhone): mantén pulsado el reactor (o la barra
  espaciadora) para hablar, o escribe. Los planes largos aparecen en "Ver detalle".
- **Panel** (enlace arriba a la derecha): rutinas y horarios editables, recordatorios, tu perfil
  y lo que sabe cada agente (puedes borrar recuerdos).
- **Terminal:** `./jarvis.sh texto`, con comandos `/memoria`, `/ensenar`, `/feedback`...

Cosas que puedes pedirle:

| Dile… | Qué hace |
| --- | --- |
| "Recuérdame llamar al gestor el jueves a las diez" | Recordatorio con voz y aviso al móvil |
| "Cambia el resumen de la mañana a las ocho" | Edita la rutina |
| "Cada viernes a las seis recuérdame revisar las ventas" | Crea una rutina nueva |
| "Hoy hice sentadilla 5x5 con 100 kilos" | Entrenamiento lo registra y sigue tu progreso |
| "¿Cómo voy con la sentadilla este mes?" | Consulta tus registros |
| "Gasté 45 euros en la cena" | Finanzas lo registra |
| "Crea un especialista de viajes" | Nuevo agente con su propia memoria |
| "¿Qué tiempo hace?" / "¿Qué tengo hoy?" | Tiempo de Bilbao / tu calendario |
| "Ideas de posts para Rentfy con las tendencias de esta semana" | Marketing busca en internet |

## 4. Conectar tu calendario (opcional, gratis)

- **Google Calendar:** Configuración → tu calendario → *Dirección secreta en formato iCal* → copia.
- **iCloud:** app Calendario → clic derecho en el calendario → Compartir → *Calendario público* → copia.

Añade a `.env`: `export JARVIS_CALENDARIO="https://..."` y reinicia Jarvis.

## Cómo aprende

Cada agente guarda en `datos/<agente>/memoria.db` sus **aprendizajes** (preferencias,
objetivos, hábitos), **registros** con números (entrenos, gastos, ventas, horas de estudio),
**historial** y tus **valoraciones**. El perfil básico (`datos/perfil.json`) lo comparte todo el
equipo. Cada noche, en el **"sueño"**, cada agente fusiona recuerdos duplicados, borra lo
obsoleto y saca lecciones de tus valoraciones. `datos/` y `.env` nunca se suben a GitHub.

## Configuración

Variables en `.env` (`export NOMBRE="valor"`), todas opcionales:

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `JARVIS_VOZ` | `Jorge` | Voz de macOS (`say -v '?'` para verlas) |
| `JARVIS_VELOCIDAD` | `180` | Palabras por minuto |
| `JARVIS_EFECTO` | `0.6` | Filtro "IA" de 0 (voz natural) a 1 (muy robótica) |
| `JARVIS_UMBRAL` | `0.5` | Sensibilidad de "Hey Jarvis" (más bajo = más sensible) |
| `JARVIS_ACTIVACION` | `hey_jarvis` | Palabra de activación o ruta a un modelo `.onnx` propio |
| `JARVIS_WHISPER` | `small` | Oído: `base` (más rápido) … `medium` (más preciso) |
| `JARVIS_CALENDARIO` | — | Enlace iCal de tu calendario |
| `JARVIS_TOKEN` | (generado) | Contraseña para el iPhone y el reloj |
| `JARVIS_NTFY` | (generado) | Tema privado de ntfy para los avisos |
| `JARVIS_HABLAR_AVISOS` | `1` | `0` para que los avisos no se lean en voz alta en el Mac |
| `JARVIS_MINUTOS_SESION` | `30` | Minutos sin hablar tras los que empieza conversación nueva |
| `JARVIS_CIUDAD` / `JARVIS_LATITUD` / `JARVIS_LONGITUD` | Bilbao | Para el tiempo |
| `JARVIS_ZONA_HORARIA` | `Europe/Madrid` | |
| `CEREBRO_MODELO` | `claude-opus-5-5` | Modelo de Claude |
| `CEREBRO_ESFUERZO_CEREBRO` | `low` | Cuánto piensa Jarvis antes de contestar (rapidez) |
| `CEREBRO_ESFUERZO` | `medium` | Cuánto piensan los especialistas |

## Hoja de ruta

| | Contenido | Estado |
| --- | --- | --- |
| Fase 1 | Jarvis en el Mac: "Hey Jarvis", oído, voz con filtro, app web | ✅ |
| Fase 2 | iPhone (app instalable) y Apple Watch (Siri), con contraseña y Tailscale | ✅ |
| Fase 3 | Rutinas editables (voz y panel), avisos por voz, Mac, app y push (ntfy) | ✅ |
| Fase 4 | Perfil compartido, registros con números, recordatorios, "sueño", panel | ✅ |
| Fase 5 | Tiempo, calendario (iCal), búsqueda web, especialistas nuevos por voz | ✅ |
| Pendiente | Gmail (requiere configurar Google Cloud) | — |
| Pendiente | Palabra de activación "Oye, Jarvis" (entrenar modelo propio) | — |
| Opcional | Voz clonada (solo de alguien que dé su permiso) | — |

## Estructura

```
cerebro/
  cerebro.py         Jarvis/Cerebro: personalidad, delega, perfil, recordatorios, rutinas
  agente.py          Agente base: bucle con Claude, memoria, registros, "sueño"
  memoria.py         SQLite por agente
  compartido.py      Perfil, rutinas, recordatorios y avisos
  especialistas.py   El equipo
  externos.py        Tiempo (Open-Meteo) y calendario (iCal)
  programador.py     Lanza rutinas y recordatorios
  notificaciones.py  Voz, notificación del Mac, app y ntfy
  servidor.py        API, app web, panel, endpoint de Siri, contraseña
  iconos.py          Icono de la app
  web/               index.html (reactor) y panel.html
  voz/               oido.py (Whisper), habla.py (macOS), filtro.py, activacion.py ("Hey Jarvis")
  jarvis.py          Arranque
instalar_mac.sh · jarvis.sh · conectar_iphone.sh · arranque_automatico.sh
tests/               Pruebas (sin micrófono ni llamadas reales a la API)
```

## Pruebas

```bash
source .venv/bin/activate && pip install -e ".[dev]" && pytest
```
