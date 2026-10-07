"""Servidor de Jarvis: la app web y la API que usarán el móvil y el Apple Watch."""

from __future__ import annotations

import logging
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from .cerebro import Cerebro, separar_detalle

WEB = Path(__file__).parent / "web"
log = logging.getLogger("jarvis")


class Mensaje(BaseModel):
    texto: str


def crear_app(cerebro: Cerebro, oido=None, voz=None) -> FastAPI:
    """``oido`` y ``voz`` son opcionales: sin ellos la app funciona solo con texto."""
    app = FastAPI(title="Jarvis")

    def responder(texto: str) -> dict:
        texto = texto.strip()
        if not texto:
            raise HTTPException(400, "Mensaje vacío")
        try:
            respuesta = cerebro.pensar(texto)
        except anthropic.AuthenticationError:
            raise HTTPException(502, "Falta la clave de Claude: configure ANTHROPIC_API_KEY, señor.")
        except anthropic.APIConnectionError:
            raise HTTPException(502, "No puedo conectar con mis sistemas, señor. ¿Hay internet?")
        except anthropic.APIError as e:
            log.exception("Error de la API")
            raise HTTPException(502, f"Mis sistemas han devuelto un error: {e}")
        hablado, detalle = separar_detalle(respuesta)
        return {"tu": texto, "respuesta": hablado, "detalle": detalle}

    @app.get("/", response_class=HTMLResponse)
    def inicio():
        return (WEB / "index.html").read_text(encoding="utf-8")

    @app.get("/api/estado")
    def estado():
        return {
            "voz": voz is not None,
            "oido": oido is not None,
            "agentes": {
                n: cerebro.agente(n).memoria.estadisticas() for n in ["cerebro", *cerebro.especialistas]
            },
        }

    @app.post("/api/mensaje")
    def mensaje(m: Mensaje):
        """Texto -> respuesta. Es lo que usará el atajo de Siri en el Apple Watch."""
        return responder(m.texto)

    @app.post("/api/audio")
    def audio(archivo: UploadFile = File(...)):
        """Audio grabado en el navegador -> transcripción -> respuesta."""
        if oido is None:
            raise HTTPException(503, "El oído no está instalado (pip install -e '.[voz]')")
        texto = oido.transcribir(archivo.file.read())
        if not texto:
            return {"tu": "", "respuesta": "", "detalle": ""}
        return responder(texto)

    @app.post("/api/voz")
    def hablar(m: Mensaje):
        """Texto -> WAV con la voz de Jarvis."""
        if voz is None:
            raise HTTPException(503, "La voz local no está disponible")
        return Response(voz.sintetizar(m.texto), media_type="audio/wav")

    @app.post("/api/nueva")
    def nueva():
        cerebro.nueva_sesion()
        return {"ok": True}

    return app
