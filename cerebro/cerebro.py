"""Cerebro: el agente principal que coordina y da órdenes a los especialistas."""

from __future__ import annotations

import anthropic

from .agente import Agente, Rechazo
from .config import Config
from .especialistas import ESPECIALISTAS

INSTRUCCIONES_CEREBRO = """
Eres el centro de mando de la vida del usuario: su día a día, sus negocios, entrenamientos,
estudios y finanzas. Tienes un equipo de agentes especialistas, cada uno con su propia memoria.

Cómo trabajas:
- Entiende qué necesita el usuario y decide qué especialista(s) deben actuar.
- Da órdenes claras a los especialistas con `delegar`: incluye todo el contexto relevante,
  porque ellos no ven esta conversación. Puedes delegar a varios a la vez si la petición toca
  varias áreas (p. ej. lanzar un producto -> negocios + marketing + finanzas).
- Integra sus respuestas en una respuesta final coherente, priorizada y breve.
- Si la petición es simple o general, respóndela tú directamente.
- Tú guardas en tu memoria lo transversal (quién es el usuario, sus prioridades vitales,
  cómo le gusta que le hables). Lo específico de un área lo aprende cada especialista.
- Si el usuario comparte un dato propio de un área, pásaselo a ese especialista para que lo
  memorice.

Tu equipo:
{equipo}
"""


class Cerebro(Agente):
    def __init__(self, config: Config | None = None, cliente: anthropic.Anthropic | None = None):
        config = config or Config()
        cliente = cliente or anthropic.Anthropic()
        self.especialistas: dict[str, Agente] = {
            nombre: Agente(nombre, d["rol"], d["instrucciones"], config, cliente)
            for nombre, d in ESPECIALISTAS.items()
        }
        equipo = "\n".join(f"- {n}: {a.rol}" for n, a in self.especialistas.items())
        super().__init__(
            "cerebro",
            "el cerebro central que gestiona y coordina todo.",
            INSTRUCCIONES_CEREBRO.format(equipo=equipo),
            config,
            cliente,
        )
        self.herramientas.append(
            {
                "name": "delegar",
                "description": (
                    "Da una orden a un agente especialista y devuelve su respuesta. "
                    "El especialista no ve esta conversación: incluye todo el contexto necesario."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "especialista": {"type": "string", "enum": list(self.especialistas)},
                        "orden": {"type": "string", "description": "La tarea, con su contexto."},
                    },
                    "required": ["especialista", "orden"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        )
        self.manejadores["delegar"] = self._delegar
        self.historial: list[dict] = []
        self.al_delegar = None  # callback opcional (especialista, orden) para la interfaz

    def _delegar(self, entrada: dict) -> str:
        nombre = entrada["especialista"]
        if nombre not in self.especialistas:
            raise ValueError(f"No existe el especialista '{nombre}'")
        if self.al_delegar:
            self.al_delegar(nombre, entrada["orden"])
        return self.especialistas[nombre].atender(entrada["orden"])

    def agente(self, nombre: str) -> Agente:
        if nombre == self.nombre:
            return self
        return self.especialistas[nombre]

    def pensar(self, mensaje: str) -> str:
        """Procesa un mensaje del usuario manteniendo la conversación de la sesión."""
        inicio = len(self.historial)
        self.historial.append({"role": "user", "content": mensaje})
        try:
            respuesta = self.conversar(self.historial)
        except Rechazo:
            del self.historial[inicio:]  # deshacemos el turno para no dejar la conversación rota
            return "No puedo ayudar con esa petición."
        except Exception:
            del self.historial[inicio:]
            raise
        self.memoria.registrar(mensaje, respuesta)
        return respuesta

    def nueva_sesion(self) -> None:
        self.historial.clear()
