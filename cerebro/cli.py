"""Interfaz de línea de comandos para hablar con Cerebro."""

from __future__ import annotations

import anthropic

from .cerebro import Cerebro, separar_detalle

AYUDA = """
Comandos:
  /agentes                         Lista los agentes y lo que saben
  /memoria <agente>                Muestra la memoria de un agente
  /ensenar <agente> <texto>        Enseña algo directamente a un agente
  /olvidar <agente> <id>           Borra un recuerdo
  /feedback <agente> <1-5> [texto] Valora el trabajo de un agente para que mejore
  /directo <agente> <mensaje>      Habla con un especialista sin pasar por Cerebro
  /nueva                           Empieza una conversación nueva (la memoria se mantiene)
  /ayuda                           Muestra esta ayuda
  /salir                           Termina
Cualquier otro texto se envía a Jarvis.
"""


def _comando(cerebro: Cerebro, linea: str) -> bool:
    """Ejecuta un comando. Devuelve False si hay que salir."""
    partes = linea.split(maxsplit=3)
    cmd = partes[0].lower()
    try:
        if cmd in ("/salir", "/exit"):
            return False
        if cmd == "/ayuda":
            print(AYUDA)
        elif cmd == "/nueva":
            cerebro.nueva_sesion()
            print("Conversación reiniciada.")
        elif cmd == "/agentes":
            for nombre in ["cerebro", *cerebro.especialistas]:
                print(f"  {nombre:<14} {cerebro.agente(nombre).memoria.estadisticas()}")
        elif cmd == "/memoria":
            print(cerebro.agente(partes[1]).memoria.contexto())
        elif cmd == "/ensenar":
            texto = linea.split(maxsplit=2)[2]
            id_ = cerebro.agente(partes[1]).memoria.guardar_aprendizaje("dato", texto, 4)
            print(f"Guardado como [{id_}].")
        elif cmd == "/olvidar":
            ok = cerebro.agente(partes[1]).memoria.olvidar(int(partes[2]))
            print("Borrado." if ok else "No existe ese recuerdo.")
        elif cmd == "/feedback":
            comentario = partes[3] if len(partes) > 3 else ""
            cerebro.agente(partes[1]).memoria.registrar_feedback(int(partes[2]), comentario)
            print("Gracias, lo tendrá en cuenta.")
        elif cmd == "/directo":
            mensaje = linea.split(maxsplit=2)[2]
            print(f"\n{partes[1]}> {cerebro.agente(partes[1]).atender(mensaje)}\n")
        else:
            print("Comando desconocido. Escribe /ayuda.")
    except (IndexError, ValueError):
        print("Uso incorrecto. Escribe /ayuda.")
    except KeyError:
        print("Ese agente no existe. Usa /agentes para verlos.")
    return True


def main() -> None:
    cerebro = Cerebro()
    cerebro.al_delegar = lambda nombre, orden: print(f"  -> Cerebro ordena a {nombre}: {orden[:100]}...")
    print("Jarvis listo (modo texto). Escribe /ayuda para ver los comandos.\n")
    while True:
        try:
            linea = input("tú> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not linea:
            continue
        if linea.startswith("/"):
            if not _comando(cerebro, linea):
                break
            continue
        try:
            hablado, detalle = separar_detalle(cerebro.pensar(linea))
            print(f"\njarvis> {hablado}\n" + (f"\n{detalle}\n" if detalle else ""))
        except anthropic.AuthenticationError:
            print("Error de autenticación: configura ANTHROPIC_API_KEY.")
        except anthropic.RateLimitError:
            print("Límite de uso alcanzado; inténtalo en un momento.")
        except anthropic.APIConnectionError:
            print("No hay conexión con la API de Claude.")
        except anthropic.APIStatusError as e:
            print(f"Error de la API ({e.status_code}): {e.message}")
