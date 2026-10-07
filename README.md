# Cerebro 🧠

Un sistema de agentes de IA (con Claude) que te ayuda a gestionar tu día a día, tus negocios,
entrenamientos, estudios y finanzas.

**Cerebro** es el agente principal: entiende lo que necesitas y da órdenes a su equipo de
especialistas. Cada agente tiene **su propio almacenamiento** donde aprende de ti y mejora
con cada interacción.

```
                 ┌──────────────┐
      tú  ─────► │   CEREBRO    │  (memoria: quién eres, tus prioridades)
                 └──────┬───────┘
                        │ delegar(especialista, orden)
   ┌────────┬───────────┼───────────┬──────────────┬──────────┐
   ▼        ▼           ▼           ▼              ▼          ▼
 agenda  negocios  marketing    finanzas   entrenamiento  estudios
   │        │           │           │              │          │
  🗄️       🗄️          🗄️          🗄️             🗄️         🗄️   ← memoria propia de cada uno
```

## Cómo aprende cada agente

Cada agente guarda en `datos/<agente>/memoria.db` (SQLite):

| Tabla          | Qué guarda                                                        |
| -------------- | ----------------------------------------------------------------- |
| `aprendizajes` | Preferencias, objetivos, hábitos y datos que aprendió de ti       |
| `historial`    | Las tareas que recibió y lo que respondió                         |
| `feedback`     | Tus valoraciones (1-5) para que ajuste su forma de trabajar       |

En cada petición, el agente recibe un resumen de su memoria. Además tiene herramientas para
`guardar_aprendizaje`, `buscar_memoria` y `olvidar`, así que decide solo qué merece recordar.
La carpeta `datos/` está en `.gitignore`: tus memorias personales no se suben al repositorio.

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY="tu-clave"   # https://platform.claude.com
```

## Uso

```bash
python -m cerebro
```

```
tú> Quiero lanzar una promo de verano para Rentfy, ¿qué hago esta semana?
  -> Cerebro ordena a marketing: ...
  -> Cerebro ordena a finanzas: ...
  -> Cerebro ordena a agenda: ...
cerebro> Plan integrado...
```

Comandos:

| Comando                              | Para qué sirve                                         |
| ------------------------------------ | ------------------------------------------------------ |
| `/agentes`                           | Lista los agentes y cuánto saben                       |
| `/memoria <agente>`                  | Muestra lo que un agente sabe de ti                    |
| `/ensenar <agente> <texto>`          | Le enseñas algo directamente                           |
| `/olvidar <agente> <id>`             | Borra un recuerdo                                      |
| `/feedback <agente> <1-5> [texto]`   | Valoras su trabajo para que mejore                     |
| `/directo <agente> <mensaje>`        | Hablas con un especialista sin pasar por Cerebro       |
| `/nueva`                             | Nueva conversación (la memoria se mantiene)            |

## Configuración

Variables de entorno opcionales:

| Variable           | Por defecto        | Descripción                                   |
| ------------------ | ------------------ | --------------------------------------------- |
| `CEREBRO_MODELO`   | `claude-opus-5-5`  | Modelo de Claude                              |
| `CEREBRO_ESFUERZO` | `medium`           | `low`, `medium`, `high`, `xhigh` o `max`      |
| `CEREBRO_DATOS`    | `datos`            | Carpeta donde viven las memorias              |

## Añadir un nuevo especialista

Agrega una entrada en `cerebro/especialistas.py`:

```python
"viajes": {
    "rol": "organizador de viajes del usuario.",
    "instrucciones": "Planificas viajes, presupuestos y reservas. Aprende sus preferencias...",
},
```

Cerebro lo detecta automáticamente, le crea su memoria y podrá darle órdenes.

## Estructura

```
cerebro/
  cerebro.py         Agente principal (coordina y delega)
  agente.py          Agente base: bucle con Claude + herramientas de memoria
  memoria.py         Almacenamiento SQLite por agente
  especialistas.py   Definición del equipo
  config.py          Configuración
  cli.py             Interfaz de terminal
tests/               Pruebas (sin llamadas reales a la API)
```

## Pruebas

```bash
pytest
```
