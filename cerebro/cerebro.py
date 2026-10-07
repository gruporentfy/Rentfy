"""Cerebro: la mente de Jarvis, que coordina y da órdenes a los especialistas."""

from __future__ import annotations

import threading

import anthropic

from .agente import Agente, Rechazo
from .config import Config
from .especialistas import ESPECIALISTAS

INSTRUCCIONES_CEREBRO = """
Tu nombre de cara al usuario es Jarvis. Eres su asistente personal, inspirado en el J.A.R.V.I.S.
de Iron Man: un mayordomo digital brillante, leal, sereno y eficiente, con un humor seco y
elegante. Tratas al usuario de "señor" (si te pide otro trato, guárdalo en memoria y úsalo).
Vive en {ciudad}. Gestionas su día a día, sus negocios, entrenamientos, estudios y finanzas.

# Cómo hablas
La mayoría de tus respuestas se leen en voz alta:
- Frases cortas y naturales, como se hablaría. Ve al grano: primero la respuesta, luego el detalle.
- Nada de markdown, asteriscos, tablas ni emojis. Si hay pasos, enuméralos con palabras
  ("primero", "después") y como mucho tres o cuatro.
- Números, horas y fechas escritos como se dicen ("a las once y media", "unos dos mil euros").
- Si el resultado de un especialista es largo (un plan, un texto para publicar), resume lo
  esencial en voz y di que el detalle queda en pantalla, añadiéndolo al final tras una línea
  que diga exactamente "DETALLE:".
- Una pizca de ingenio está bien; nunca a costa de la utilidad.

# Cómo trabajas
- Tienes un equipo de especialistas, cada uno con su propia memoria. Decide si respondes tú
  o das la orden con `delegar`. Ellos no ven esta conversación: dales todo el contexto.
- Si la petición toca varias áreas, delega a varios a la vez en el mismo turno.
- Si el usuario comparte un dato propio de un área, pásaselo a ese especialista para que lo
  memorice. Tú guardas lo transversal: quién es, sus prioridades, cómo quiere que le hables.
- Si te falta un dato imprescindible, pregúntalo en una sola frase.

# Tu equipo
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
            "la mente central que gestiona y coordina todo.",
            INSTRUCCIONES_CEREBRO.format(equipo=equipo, ciudad=config.ciudad),
            config,
            cliente,
            esfuerzo=config.esfuerzo_cerebro,
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
        # Varias entradas (voz, web, reloj) comparten una sola conversación: de una en una.
        self._turno = threading.Lock()

    def _delegar(self, entrada: dict) -> str:
        nombre = entrada["especialista"]
        if nombre not in self.especialistas:
            raise ValueError(f"No existe el especialista '{nombre}'")
        if self.al_delegar:
            self.al_delegar(nombre, entrada["orden"])
        return self.especialistas[nombre].atender(entrada["orden"])

    def agente(self, nombre: str) -> Agente:
        if nombre in (self.nombre, "jarvis"):
            return self
        return self.especialistas[nombre]

    def pensar(self, mensaje: str) -> str:
        """Procesa un mensaje del usuario manteniendo la conversación de la sesión."""
        with self._turno:
            inicio = len(self.historial)
            self.historial.append({"role": "user", "content": mensaje})
            try:
                respuesta = self.conversar(self.historial)
            except Rechazo:
                del self.historial[inicio:]  # deshacemos el turno para no dejar la conversación rota
                return "Me temo que no puedo ayudarle con eso, señor."
            except Exception:
                del self.historial[inicio:]
                raise
            self.memoria.registrar(mensaje, respuesta)
            return respuesta

    def nueva_sesion(self) -> None:
        with self._turno:
            self.historial.clear()


def separar_detalle(respuesta: str) -> tuple[str, str]:
    """Divide la respuesta en (lo que se dice en voz alta, el detalle para la pantalla)."""
    hablado, _, detalle = respuesta.partition("DETALLE:")
    return hablado.strip(), detalle.strip()
