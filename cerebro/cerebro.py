"""Cerebro: la mente de Jarvis, que coordina y da órdenes a los especialistas."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime

import anthropic

from . import externos
from .agente import Agente, Rechazo, _herramienta
from .compartido import Avisos, Perfil, Recordatorios, Rutinas
from .config import Config
from .especialistas import ESPECIALISTAS

INSTRUCCIONES_CEREBRO = """
Tu nombre de cara al usuario es Jarvis. Eres su asistente personal, inspirado en el J.A.R.V.I.S.
de Iron Man: un mayordomo digital brillante, leal, sereno y eficiente, con un humor seco y
elegante. Tratas al usuario de "señor" (si te pide otro trato, guárdalo en memoria y úsalo).
Vive en {ciudad}. Gestionas su día a día, sus negocios, entrenamientos, estudios y finanzas.

# Cómo hablas
La mayoría de tus respuestas se leen en voz alta (en el Mac, el iPhone o el Apple Watch):
- Frases cortas y naturales, como se hablaría. Ve al grano: primero la respuesta, luego el detalle.
- Nada de markdown, asteriscos, tablas ni emojis. Si hay pasos, enuméralos con palabras
  ("primero", "después") y como mucho tres o cuatro.
- Números, horas y fechas escritos como se dicen ("a las once y media", "unos dos mil euros").
- Si el resultado es largo (un plan, un texto para publicar), resume lo esencial en voz y añade
  el detalle al final tras una línea que diga exactamente "DETALLE:"; se mostrará en pantalla.
- Una pizca de ingenio está bien; nunca a costa de la utilidad.

# Cómo trabajas
- Tienes un equipo de especialistas, cada uno con su propia memoria. Decide si respondes tú o
  das la orden con `delegar`. Ellos no ven esta conversación: dales todo el contexto.
- Si la petición toca varias áreas, delega a varios a la vez en el mismo turno.
- Si el usuario comparte un dato propio de un área (un entreno, un gasto, una venta), pásaselo
  a ese especialista para que lo registre y memorice.
- Datos básicos que todo el equipo debe conocer (nombre, negocios, horarios fijos, objetivos
  principales) van al perfil con `actualizar_perfil`. Lo transversal sobre cómo tratarle va a
  tu memoria.
- "Recuérdame…" -> `crear_recordatorio`. "Cambia el resumen de la mañana a las 8" o "añade una
  rutina…" -> `configurar_rutina`. "Necesito un especialista en…" -> `crear_especialista`.
- Para el tiempo usa `ver_tiempo`; para su agenda, `ver_calendario`.
- Si te falta un dato imprescindible, pregúntalo en una sola frase.

# Mensajes automáticos
Los mensajes que empiezan por "[RUTINA" no los escribe el usuario: son tareas programadas tuyas.
Prepara lo que se pide como si le hablaras tú por iniciativa propia (empieza por un saludo
acorde a la hora) y sé breve: se leerá en voz alta y llegará como notificación al móvil.

# Tu equipo
{equipo}
"""

NOMBRE_VALIDO = re.compile(r"^[a-z][a-z0-9_]{1,24}$")


class Cerebro(Agente):
    def __init__(self, config: Config | None = None, cliente: anthropic.Anthropic | None = None):
        config = config or Config()
        cliente = cliente or anthropic.Anthropic()
        datos = config.directorio_datos
        self.perfil_usuario = Perfil(datos / "perfil.json")
        self.recordatorios = Recordatorios(datos / "recordatorios.db")
        self.rutinas = Rutinas(datos / "rutinas.json")
        self.avisos = Avisos()
        self._especialistas_extra = Perfil(datos / "especialistas.json")  # mismo formato: dict en JSON

        self.especialistas: dict[str, Agente] = {}
        definiciones = {**ESPECIALISTAS, **self._especialistas_extra.datos}
        for nombre, d in definiciones.items():
            self._crear_agente(nombre, d, config, cliente)

        super().__init__(
            "cerebro", "la mente central que gestiona y coordina todo.", "", config, cliente,
            esfuerzo=config.esfuerzo_cerebro, perfil=self.perfil_usuario,
        )
        self._anadir_herramientas()

        self.historial: list[dict] = []
        self._system_sesion: list[dict] | None = None
        self._tools_sesion: list[dict] | None = None
        self._ultima_actividad = 0.0
        self.al_delegar = None  # callback opcional (especialista, orden) para la interfaz
        # Varias entradas (voz, web, reloj, rutinas) comparten una conversación: de una en una.
        self._turno = threading.RLock()

    # --- equipo ---------------------------------------------------------------

    def _crear_agente(self, nombre: str, d: dict, config: Config, cliente) -> Agente:
        agente = Agente(
            nombre, d["rol"], d["instrucciones"], config, cliente,
            perfil=self.perfil_usuario, web=d.get("web", False),
        )
        if d.get("calendario"):
            agente.anadir_herramienta(DEF_CALENDARIO, self._ver_calendario)
        self.especialistas[nombre] = agente
        return agente

    @property
    def instrucciones_actuales(self) -> str:
        equipo = "\n".join(f"- {n}: {a.rol}" for n, a in self.especialistas.items())
        return INSTRUCCIONES_CEREBRO.format(equipo=equipo, ciudad=self.config.ciudad)

    def construir_system(self) -> list[dict]:
        self.instrucciones = self.instrucciones_actuales
        system = super().construir_system()
        rutinas = "\n".join(
            f"- {n}: {r['hora']} ({r['dias']}){'' if r.get('activa', True) else ' [desactivada]'} — {r['descripcion']}"
            for n, r in self.rutinas.lista().items()
        )
        recordatorios = "\n".join(
            f"- [{r['id']}] {r['cuando']} ({r['repetir']}): {r['texto']}" for r in self.recordatorios.activos()
        ) or "Ninguno."
        system[1]["text"] += f"\n\n# Rutinas programadas\n{rutinas}\n\n# Recordatorios activos\n{recordatorios}"
        return system

    def _herramientas_sesion(self) -> list[dict]:
        delegar = _herramienta(
            "delegar",
            "Da una orden a un agente especialista y devuelve su respuesta. "
            "El especialista no ve esta conversación: incluye todo el contexto necesario.",
            {
                "especialista": {"type": "string", "enum": list(self.especialistas)},
                "orden": {"type": "string", "description": "La tarea, con su contexto."},
            },
        )
        return [delegar, *self.herramientas]

    # --- herramientas de Cerebro ---------------------------------------------

    def _anadir_herramientas(self) -> None:
        self.manejadores["delegar"] = self._delegar
        self.anadir_herramienta(_herramienta(
            "actualizar_perfil",
            "Guarda un dato básico del usuario en el perfil que comparte todo el equipo. "
            "Valor vacío para borrarlo.",
            {"clave": {"type": "string", "description": "p. ej. nombre, negocios, horario_trabajo"},
             "valor": {"type": "string"}},
        ), self._actualizar_perfil)
        self.anadir_herramienta(_herramienta(
            "crear_recordatorio",
            "Programa un aviso para el usuario (voz en el Mac y notificación al móvil).",
            {
                "texto": {"type": "string", "description": "Lo que hay que recordarle."},
                "cuando": {"type": "string", "description": "Fecha y hora local ISO: 2026-10-08T17:30"},
                "repetir": {"type": "string", "enum": ["no", "diario", "semanal", "laborables"]},
            },
        ), self._crear_recordatorio)
        self.anadir_herramienta(_herramienta(
            "borrar_recordatorio", "Cancela un recordatorio por su id.", {"id": {"type": "integer"}},
        ), self._borrar_recordatorio)
        self.anadir_herramienta(_herramienta(
            "configurar_rutina",
            "Crea o modifica una rutina automática (p. ej. resumen_manana, repaso_noche, revision_semanal, "
            "sueno, o una nueva). Usa '' en los campos que no cambian.",
            {
                "nombre": {"type": "string", "description": "Identificador en minúsculas con guiones bajos."},
                "hora": {"type": "string", "description": "HH:MM o ''"},
                "dias": {"type": "string", "description": "todos, laborables, nombres de días separados por comas, o ''"},
                "activa": {"type": "string", "enum": ["si", "no", ""]},
                "descripcion": {"type": "string", "description": "Qué debe hacer Jarvis en esa rutina, o ''"},
            },
        ), self._configurar_rutina)
        self.anadir_herramienta(_herramienta(
            "crear_especialista",
            "Incorpora un nuevo especialista al equipo con su propia memoria (disponible desde el "
            "siguiente mensaje).",
            {
                "nombre": {"type": "string", "description": "Una palabra en minúsculas, p. ej. viajes"},
                "rol": {"type": "string", "description": "Una línea: qué es para el usuario"},
                "instrucciones": {"type": "string", "description": "Qué hace, qué debe aprender, cómo entrega"},
                "web": {"type": "boolean", "description": "Si puede buscar en internet"},
            },
        ), self._crear_especialista)
        self.anadir_herramienta(_herramienta(
            "ver_tiempo", "Tiempo actual y previsión de hoy y mañana en la ciudad del usuario.", {},
        ), self._ver_tiempo)
        self.anadir_herramienta(DEF_CALENDARIO, self._ver_calendario)

    def _delegar(self, e: dict) -> str:
        nombre = e["especialista"]
        if nombre not in self.especialistas:
            raise ValueError(f"No existe el especialista '{nombre}'")
        if self.al_delegar:
            self.al_delegar(nombre, e["orden"])
        return self.especialistas[nombre].atender(e["orden"])

    def _actualizar_perfil(self, e: dict) -> str:
        self.perfil_usuario.poner(e["clave"].strip().lower().replace(" ", "_"), e["valor"].strip())
        return "Perfil actualizado."

    def _crear_recordatorio(self, e: dict) -> str:
        id_ = self.recordatorios.crear(e["texto"], e["cuando"], e.get("repetir", "no"))
        return f"Recordatorio [{id_}] programado para {e['cuando']}."

    def _borrar_recordatorio(self, e: dict) -> str:
        return "Cancelado." if self.recordatorios.borrar(e["id"]) else "No existe ese recordatorio."

    def _configurar_rutina(self, e: dict) -> str:
        nombre = e["nombre"].strip().lower().replace(" ", "_")
        activa = {"si": True, "no": False}.get(e.get("activa", ""))
        r = self.rutinas.configurar(
            nombre, hora=e.get("hora") or None, dias=e.get("dias") or None,
            activa=activa, descripcion=e.get("descripcion") or None,
        )
        return f"Rutina {nombre}: {json.dumps(r, ensure_ascii=False)}"

    def _crear_especialista(self, e: dict) -> str:
        nombre = e["nombre"].strip().lower()
        if not NOMBRE_VALIDO.match(nombre):
            raise ValueError("El nombre debe ser una palabra en minúsculas sin espacios")
        if nombre in self.especialistas or nombre in ("cerebro", "jarvis"):
            raise ValueError(f"Ya existe '{nombre}'")
        d = {"rol": e["rol"], "instrucciones": e["instrucciones"], "web": bool(e.get("web"))}
        self._especialistas_extra.poner(nombre, d)
        self._crear_agente(nombre, d, self.config, self.cliente)
        # Las herramientas de esta conversación no pueden cambiar a mitad: estará disponible
        # en cuanto empiece la siguiente.
        self._reiniciar_tras_turno = True
        return f"Especialista '{nombre}' creado con su propia memoria; disponible desde el próximo mensaje."

    def _ver_tiempo(self, e: dict) -> str:
        return externos.tiempo(self.config.latitud, self.config.longitud, self.config.zona_horaria,
                               self.config.ciudad)

    def _ver_calendario(self, e: dict) -> str:
        if not self.config.url_calendario:
            return ("El calendario no está conectado. Para conectarlo, el usuario debe poner su "
                    "dirección secreta iCal en JARVIS_CALENDARIO (ver README).")
        return externos.eventos_calendario(self.config.url_calendario, self.config.zona_horaria,
                                           dias=max(1, int(e.get("dias") or 1)))

    # --- conversación ---------------------------------------------------------

    def agente(self, nombre: str) -> Agente:
        if nombre in (self.nombre, "jarvis"):
            return self
        return self.especialistas[nombre]

    def _sesion_caducada(self) -> bool:
        return bool(self.historial) and time.monotonic() - self._ultima_actividad > self.config.minutos_sesion * 60

    def pensar(self, mensaje: str) -> str:
        """Procesa un mensaje del usuario manteniendo la conversación de la sesión."""
        with self._turno:
            if self._sesion_caducada():
                self._nueva_sesion()
            if self._system_sesion is None:
                # Instrucciones y herramientas fijas durante toda la conversación.
                self._system_sesion = self.construir_system()
                self._tools_sesion = self._herramientas_sesion()
            self._reiniciar_tras_turno = False
            inicio = len(self.historial)
            self.historial.append({"role": "user", "content": f"{self.marca_temporal()}\n{mensaje}"})
            try:
                respuesta = self.conversar(self.historial, self._system_sesion, self._tools_sesion)
            except Rechazo:
                del self.historial[inicio:]  # deshacemos el turno (solo quitamos del final)
                return "Me temo que no puedo ayudarle con eso, señor."
            except Exception:
                del self.historial[inicio:]
                raise
            finally:
                self._ultima_actividad = time.monotonic()
            self.memoria.registrar(mensaje, respuesta)
            if self._reiniciar_tras_turno:
                self._nueva_sesion()
            return respuesta

    def _nueva_sesion(self) -> None:
        self.historial.clear()
        self._system_sesion = self._tools_sesion = None

    def nueva_sesion(self) -> None:
        with self._turno:
            self._nueva_sesion()

    # --- rutinas ----------------------------------------------------------------

    def ejecutar_rutina(self, nombre: str) -> str:
        """Ejecuta una rutina programada y devuelve el mensaje para el usuario ('' si es silenciosa)."""
        if nombre == "sueno":
            resumenes = []
            for agente in [self, *self.especialistas.values()]:
                try:
                    resumenes.append(f"{agente.nombre}: {agente.consolidar()}")
                except Exception as e:
                    resumenes.append(f"{agente.nombre}: error ({e})")
            self.memoria.registrar("[RUTINA sueño]", "\n".join(resumenes))
            return ""
        rutina = self.rutinas.lista()[nombre]
        return self.pensar(f"[RUTINA {nombre}] {rutina['descripcion']}")

    def ahora_local(self) -> datetime:
        return self.ahora().replace(tzinfo=None)


DEF_CALENDARIO = _herramienta(
    "ver_calendario",
    "Eventos del calendario real del usuario desde hoy a las 00:00 durante los días indicados.",
    {"dias": {"type": "integer", "description": "1 = hoy, 7 = esta semana"}},
)


def separar_detalle(respuesta: str) -> tuple[str, str]:
    """Divide la respuesta en (lo que se dice en voz alta, el detalle para la pantalla)."""
    hablado, _, detalle = respuesta.partition("DETALLE:")
    return hablado.strip(), detalle.strip()
