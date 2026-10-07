"""Agente base: un modelo de Claude con su propia memoria y herramientas."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

import anthropic

from .config import Config
from .memoria import Memoria

Manejador = Callable[[dict], str]

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class Rechazo(Exception):
    """El modelo declinó la petición (stop_reason == "refusal")."""

INSTRUCCIONES_MEMORIA = """
# Tu memoria
Tienes una memoria propia y persistente. Úsala para mejorar cada día:
- Cuando el usuario revele una preferencia, objetivo, hábito, dato relevante o te corrija,
  guárdalo con `guardar_aprendizaje` (frases cortas y concretas, sin duplicar lo ya sabido).
- Si necesitas recordar algo que no aparece abajo, usa `buscar_memoria`.
- Si un recuerdo quedó obsoleto o es incorrecto, elimínalo con `olvidar`.
- Ten en cuenta las valoraciones del usuario para ajustar tu estilo.
Responde siempre en español, de forma práctica y accionable.
"""

HERRAMIENTAS_MEMORIA = [
    {
        "name": "guardar_aprendizaje",
        "description": "Guarda en tu memoria algo que aprendiste del usuario para usarlo en el futuro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "categoria": {
                    "type": "string",
                    "description": "Etiqueta corta: preferencia, objetivo, habito, dato, correccion, etc.",
                },
                "contenido": {"type": "string", "description": "Lo aprendido, en una frase."},
                "importancia": {
                    "type": "integer",
                    "description": "1 (detalle) a 5 (fundamental).",
                },
            },
            "required": ["categoria", "contenido", "importancia"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "buscar_memoria",
        "description": "Busca en tu memoria recuerdos relacionados con una consulta.",
        "input_schema": {
            "type": "object",
            "properties": {"consulta": {"type": "string"}},
            "required": ["consulta"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "olvidar",
        "description": "Elimina un recuerdo obsoleto o incorrecto por su id (el número entre corchetes).",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


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
    ):
        self.nombre = nombre
        self.rol = rol
        self.instrucciones = instrucciones
        self.config = config
        self.cliente = cliente or anthropic.Anthropic()
        self.esfuerzo = esfuerzo or config.esfuerzo
        self.memoria = Memoria(nombre, config.directorio_datos)
        self.herramientas: list[dict] = list(HERRAMIENTAS_MEMORIA)
        self.manejadores: dict[str, Manejador] = {
            "guardar_aprendizaje": self._guardar_aprendizaje,
            "buscar_memoria": self._buscar_memoria,
            "olvidar": self._olvidar,
        }

    # --- herramientas de memoria --------------------------------------------

    def _guardar_aprendizaje(self, entrada: dict) -> str:
        id_ = self.memoria.guardar_aprendizaje(
            entrada["categoria"], entrada["contenido"], entrada.get("importancia", 3)
        )
        return f"Guardado como recuerdo [{id_}]."

    def _buscar_memoria(self, entrada: dict) -> str:
        filas = self.memoria.buscar(entrada["consulta"])
        if not filas:
            return "No encontré recuerdos relacionados."
        return "\n".join(f"[{f['id']}] ({f['categoria']}) {f['contenido']}" for f in filas)

    def _olvidar(self, entrada: dict) -> str:
        return "Recuerdo eliminado." if self.memoria.olvidar(entrada["id"]) else "No existe ese recuerdo."

    # --- prompt ---------------------------------------------------------------

    def _system(self) -> list[dict]:
        # Bloque estable primero (se cachea); la memoria cambia, va después.
        ahora = datetime.now(ZoneInfo(self.config.zona_horaria))
        estable = f"Eres {self.nombre}: {self.rol}\n\n{self.instrucciones}\n{INSTRUCCIONES_MEMORIA}"
        dinamico = (
            f"Fecha y hora actual: {DIAS[ahora.weekday()]} {ahora:%d/%m/%Y %H:%M} ({self.config.ciudad})\n\n"
            f"# Contenido de tu memoria\n{self.memoria.contexto()}"
        )
        return [
            {"type": "text", "text": estable, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dinamico},
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

    def conversar(self, mensajes: list[dict]) -> str:
        """Ejecuta el bucle agéntico sobre ``mensajes`` (se modifica en el sitio)."""
        while True:
            respuesta = self.cliente.beta.messages.create(
                model=self.config.modelo,
                max_tokens=self.config.max_tokens,
                system=self._system(),
                tools=self.herramientas,
                messages=mensajes,
                thinking={"type": "adaptive"},
                output_config={"effort": self.esfuerzo},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )

            if respuesta.stop_reason == "refusal":
                raise Rechazo()

            mensajes.append({"role": "assistant", "content": respuesta.content})

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

            resultados = [
                {"type": "tool_result", "tool_use_id": b.id, "content": contenido, "is_error": es_error}
                for b, (contenido, es_error) in zip(llamadas, salidas)
            ]
            mensajes.append({"role": "user", "content": resultados})

    def atender(self, tarea: str) -> str:
        """Recibe una tarea (de Cerebro o del usuario), la resuelve y la registra."""
        try:
            respuesta = self.conversar([{"role": "user", "content": tarea}])
        except Rechazo:
            return f"{self.nombre} no puede ayudar con esa petición."
        self.memoria.registrar(tarea, respuesta)
        return respuesta
