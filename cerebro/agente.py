"""Agente base: un modelo de Claude con su propia memoria y herramientas."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Callable
from zoneinfo import ZoneInfo

import anthropic

from .config import Config
from .memoria import Memoria

if TYPE_CHECKING:
    from .compartido import Perfil

Manejador = Callable[[dict], str]

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

BETAS = ["server-side-fallback-2026-07-01", "thinking-binding-controls-2026-08-01"]
# Si alguna vez el historial cambiara, la API descarta el razonamiento previo en vez de fallar.
THINKING = {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}


class Rechazo(Exception):
    """El modelo declinó la petición (stop_reason == "refusal")."""


INSTRUCCIONES_MEMORIA = """
# Tu memoria
Tienes una memoria propia y persistente. Úsala para mejorar cada día:
- Cuando el usuario revele una preferencia, objetivo, hábito, dato relevante o te corrija,
  guárdalo con `guardar_aprendizaje` (frases cortas y concretas, sin duplicar lo ya sabido).
- Cuando haya un dato con números que convenga seguir en el tiempo (peso levantado, kilómetros,
  horas de estudio, gastos, ventas...), guárdalo con `registrar_dato` y usa `consultar_registros`
  para ver la evolución antes de opinar sobre su progreso.
- Si necesitas recordar algo que no aparece abajo, usa `buscar_memoria`.
- Si un recuerdo quedó obsoleto o es incorrecto, elimínalo con `olvidar`.
- Ten en cuenta las valoraciones del usuario para ajustar tu estilo.
Cada mensaje del usuario empieza con la fecha y hora actuales entre corchetes.
Responde siempre en español, de forma práctica y accionable.
"""


def _herramienta(nombre: str, descripcion: str, propiedades: dict) -> dict:
    return {
        "name": nombre,
        "description": descripcion,
        "input_schema": {
            "type": "object",
            "properties": propiedades,
            "required": list(propiedades),
            "additionalProperties": False,
        },
        "strict": True,
    }


HERRAMIENTAS_MEMORIA = [
    _herramienta(
        "guardar_aprendizaje",
        "Guarda en tu memoria algo que aprendiste del usuario para usarlo en el futuro.",
        {
            "categoria": {"type": "string", "description": "preferencia, objetivo, habito, dato, correccion..."},
            "contenido": {"type": "string", "description": "Lo aprendido, en una frase."},
            "importancia": {"type": "integer", "description": "1 (detalle) a 5 (fundamental)."},
        },
    ),
    _herramienta("buscar_memoria", "Busca en tu memoria recuerdos relacionados.", {"consulta": {"type": "string"}}),
    _herramienta(
        "olvidar", "Elimina un recuerdo obsoleto o incorrecto por su id (número entre corchetes).",
        {"id": {"type": "integer"}},
    ),
    _herramienta(
        "registrar_dato",
        "Guarda un dato medible con fecha para seguir su evolución (entrenos, gastos, ventas, estudio...).",
        {
            "tipo": {"type": "string", "description": "Nombre corto y estable, p. ej. 'sentadilla', 'gasto comida'."},
            "valor": {"type": "number"},
            "unidad": {"type": "string", "description": "kg, km, €, horas, repeticiones..."},
            "nota": {"type": "string", "description": "Contexto opcional ('' si no hay)."},
        },
    ),
    _herramienta(
        "consultar_registros",
        "Devuelve los datos registrados de un tipo (o todos si tipo es '') en los últimos días.",
        {"tipo": {"type": "string"}, "dias": {"type": "integer"}},
    ),
]

BUSQUEDA_WEB = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}


class Agente:
    """Un agente especialista. Cerebro hereda de esta clase."""

    def __init__(
        self,
        nombre: str,
        rol: str,
        instrucciones: str,
        config: Config,
        cliente: anthropic.Anthropic | None = None,
        esfuerzo: str | None = None,
        perfil: Perfil | None = None,
        web: bool = False,
    ):
        self.nombre = nombre
        self.rol = rol
        self.instrucciones = instrucciones
        self.config = config
        self.cliente = cliente or anthropic.Anthropic()
        self.esfuerzo = esfuerzo or config.esfuerzo
        self.perfil = perfil
        self.memoria = Memoria(nombre, config.directorio_datos)
        self.herramientas: list[dict] = list(HERRAMIENTAS_MEMORIA)
        if web:
            self.herramientas.append(BUSQUEDA_WEB)
        self.manejadores: dict[str, Manejador] = {
            "guardar_aprendizaje": self._guardar_aprendizaje,
            "buscar_memoria": self._buscar_memoria,
            "olvidar": self._olvidar,
            "registrar_dato": self._registrar_dato,
            "consultar_registros": self._consultar_registros,
        }

    def anadir_herramienta(self, definicion: dict, manejador: Manejador) -> None:
        self.herramientas.append(definicion)
        self.manejadores[definicion["name"]] = manejador

    # --- herramientas de memoria --------------------------------------------

    def _guardar_aprendizaje(self, e: dict) -> str:
        id_ = self.memoria.guardar_aprendizaje(e["categoria"], e["contenido"], e.get("importancia", 3))
        return f"Guardado como recuerdo [{id_}]."

    def _buscar_memoria(self, e: dict) -> str:
        filas = self.memoria.buscar(e["consulta"])
        if not filas:
            return "No encontré recuerdos relacionados."
        return "\n".join(f"[{f['id']}] ({f['categoria']}) {f['contenido']}" for f in filas)

    def _olvidar(self, e: dict) -> str:
        return "Recuerdo eliminado." if self.memoria.olvidar(e["id"]) else "No existe ese recuerdo."

    def _registrar_dato(self, e: dict) -> str:
        id_ = self.memoria.registrar_dato(e["tipo"], e["valor"], e.get("unidad", ""), e.get("nota", ""))
        return f"Registrado [{id_}]."

    def _consultar_registros(self, e: dict) -> str:
        filas = self.memoria.consultar_registros(e.get("tipo", ""), e.get("dias") or 30)
        if not filas:
            return "No hay registros en ese periodo."
        return "\n".join(
            f"{f['fecha'][:16]} {f['tipo']}: {f['valor']:g} {f['unidad']} {f['nota']}".rstrip() for f in filas
        )

    # --- prompt ---------------------------------------------------------------

    def ahora(self) -> datetime:
        return datetime.now(ZoneInfo(self.config.zona_horaria))

    def marca_temporal(self) -> str:
        a = self.ahora()
        return f"[{DIAS[a.weekday()]} {a:%d/%m/%Y %H:%M}, {self.config.ciudad}]"

    def construir_system(self) -> list[dict]:
        """Instrucciones + memoria. Se congela al empezar cada conversación: cambiarlas a mitad
        invalidaría el razonamiento previo del modelo y la caché."""
        estable = f"Eres {self.nombre}: {self.rol}\n\n{self.instrucciones}\n{INSTRUCCIONES_MEMORIA}"
        perfil = f"# Perfil del usuario (compartido por todo el equipo)\n{self.perfil.texto()}\n\n" if self.perfil else ""
        return [
            {"type": "text", "text": estable, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"{perfil}# Contenido de tu memoria\n{self.memoria.contexto()}"},
        ]

    # --- bucle de herramientas ------------------------------------------------

    def _ejecutar_herramienta(self, nombre: str, entrada: dict) -> tuple[str, bool]:
        manejador = self.manejadores.get(nombre)
        if manejador is None:
            return f"Herramienta desconocida: {nombre}", True
        try:
            return manejador(entrada), False
        except Exception as e:  # el error vuelve al modelo para que se corrija
            return f"Error ejecutando {nombre}: {e}", True

    def _pedir(self, system: list[dict], tools: list[dict], mensajes: list[dict], formato: dict | None = None):
        output_config = {"effort": self.esfuerzo}
        if formato:
            output_config["format"] = formato
        return self.cliente.beta.messages.create(
            model=self.config.modelo,
            max_tokens=self.config.max_tokens,
            system=system,
            tools=tools,
            messages=mensajes,
            thinking=THINKING,
            output_config=output_config,
            betas=BETAS,
            fallbacks="default",
        )

    def conversar(self, mensajes: list[dict], system: list[dict] | None = None,
                  tools: list[dict] | None = None) -> str:
        """Ejecuta el bucle agéntico sobre ``mensajes`` (se modifica en el sitio, solo añadiendo)."""
        system = system or self.construir_system()
        tools = tools if tools is not None else list(self.herramientas)
        continuaciones = 0
        while True:
            respuesta = self._pedir(system, tools, mensajes)
            if respuesta.stop_reason == "refusal":
                raise Rechazo()

            mensajes.append({"role": "assistant", "content": respuesta.content})

            if respuesta.stop_reason == "pause_turn" and continuaciones < 5:
                continuaciones += 1  # la búsqueda web va por partes: se reanuda sola
                continue
            if respuesta.stop_reason != "tool_use":
                texto = "\n".join(b.text for b in respuesta.content if b.type == "text").strip()
                if respuesta.stop_reason == "max_tokens":
                    texto += "\n\n[Respuesta cortada por longitud]"
                return texto

            # Las herramientas pedidas en el mismo turno se ejecutan en paralelo
            # (p. ej. Cerebro dando órdenes a marketing y finanzas a la vez).
            llamadas = [b for b in respuesta.content if b.type == "tool_use"]

            def ejecutar(bloque):
                entrada = bloque.input if isinstance(bloque.input, dict) else json.loads(bloque.input)
                return self._ejecutar_herramienta(bloque.name, entrada)

            with ThreadPoolExecutor(max_workers=max(1, len(llamadas))) as pool:
                salidas = list(pool.map(ejecutar, llamadas))

            mensajes.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": b.id, "content": contenido, "is_error": es_error}
                    for b, (contenido, es_error) in zip(llamadas, salidas)
                ],
            })

    def atender(self, tarea: str) -> str:
        """Recibe una tarea (de Cerebro o del usuario), la resuelve y la registra."""
        try:
            respuesta = self.conversar([{"role": "user", "content": f"{self.marca_temporal()}\n{tarea}"}])
        except Rechazo:
            return f"{self.nombre} no puede ayudar con esa petición."
        self.memoria.registrar(tarea, respuesta)
        return respuesta

    # --- "sueño": consolidar la memoria ---------------------------------------

    def consolidar(self) -> str:
        """Revisa la memoria: fusiona duplicados, borra lo obsoleto y saca conclusiones del feedback."""
        aprendizajes = self.memoria.aprendizajes(limite=200)
        if len(aprendizajes) < 3 and not self.memoria.feedback_reciente():
            return "Nada que consolidar."
        esquema = {
            "type": "object",
            "properties": {
                "borrar": {"type": "array", "items": {"type": "integer"}},
                "nuevos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "categoria": {"type": "string"},
                            "contenido": {"type": "string"},
                            "importancia": {"type": "integer"},
                        },
                        "required": ["categoria", "contenido", "importancia"],
                        "additionalProperties": False,
                    },
                },
                "resumen": {"type": "string"},
            },
            "required": ["borrar", "nuevos", "resumen"],
            "additionalProperties": False,
        }
        tarea = (
            "Es de noche y toca ordenar tu memoria. Revisa tus recuerdos, valoraciones e historial:\n"
            "- Fusiona recuerdos duplicados o solapados (borra los viejos y crea uno mejor).\n"
            "- Borra lo obsoleto o contradicho por información más reciente.\n"
            "- Si las valoraciones o el historial revelan un patrón (qué le gusta, qué no funciona), "
            "crea un aprendizaje nuevo de categoría 'leccion'.\n"
            "- No borres nada importante sin sustituirlo. Si todo está bien, devuelve listas vacías.\n"
            "En 'resumen', una frase con lo que cambiaste."
        )
        respuesta = self._pedir(
            self.construir_system(), [], [{"role": "user", "content": tarea}],
            formato={"type": "json_schema", "schema": esquema},
        )
        if respuesta.stop_reason == "refusal":
            return "Consolidación rechazada."
        datos = json.loads(next(b.text for b in respuesta.content if b.type == "text"))
        validos = {a["id"] for a in aprendizajes}
        for id_ in datos["borrar"]:
            if id_ in validos:
                self.memoria.olvidar(id_)
        for n in datos["nuevos"]:
            self.memoria.guardar_aprendizaje(n["categoria"], n["contenido"], n["importancia"])
        return datos["resumen"]
