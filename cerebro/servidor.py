"""Servidor de Jarvis: la app web, el panel y la API que usan el iPhone y el Apple Watch."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from .cerebro import Cerebro, separar_detalle
from .iconos import icono

WEB = Path(__file__).parent / "web"
log = logging.getLogger("jarvis")
VERSION = "0.3.1"
# Que el navegador cargue siempre la última versión de la app tras actualizar Jarvis.
SIN_CACHE = {"Cache-Control": "no-store"}
PUBLICAS = {"/manifest.webmanifest", "/icono-180.png", "/icono-512.png"}


class Mensaje(BaseModel):
    texto: str


class CambioRutina(BaseModel):
    nombre: str
    hora: str | None = None
    activa: bool | None = None


def crear_app(cerebro: Cerebro, oido=None, voz=None, token: str = "") -> FastAPI:
    """``oido`` y ``voz`` son opcionales: sin ellos la app funciona solo con texto.
    Con ``token``, cada petición debe traerlo (cabecera Bearer, cookie o ?token=)."""
    app = FastAPI(title="Jarvis")

    @app.exception_handler(Exception)
    async def error_inesperado(request: Request, exc: Exception):
        # Que el fallo se vea claro en la Terminal y en la app, en lugar de "Internal Server Error".
        log.error("Error en %s", request.url.path, exc_info=exc)
        return JSONResponse({"detail": f"Error interno ({type(exc).__name__}): {exc}"}, status_code=500)

    def token_valido(valor: str | None) -> bool:
        return bool(valor) and secrets.compare_digest(valor, token)

    @app.middleware("http")
    async def proteger(request: Request, call_next):
        if not token or request.url.path in PUBLICAS:
            return await call_next(request)
        cabecera = request.headers.get("authorization", "")
        por_url = request.query_params.get("token")
        if not (token_valido(cabecera.removeprefix("Bearer ").strip())
                or token_valido(request.cookies.get("jarvis_token")) or token_valido(por_url)):
            return JSONResponse({"detail": "Acceso no autorizado"}, status_code=401)
        respuesta = await call_next(request)
        if token_valido(por_url):  # recordar el acceso en este navegador
            respuesta.set_cookie("jarvis_token", token, max_age=60 * 60 * 24 * 365,
                                 httponly=True, samesite="lax", secure=request.url.scheme == "https")
        return respuesta

    def responder(texto: str) -> dict:
        texto = texto.strip()
        if not texto:
            raise HTTPException(400, "Mensaje vacío")
        try:
            respuesta = cerebro.pensar(texto)
        except anthropic.AuthenticationError:
            raise HTTPException(502, "Falta la clave de Claude: configure ANTHROPIC_API_KEY, señor.")
        except anthropic.RateLimitError:
            raise HTTPException(502, "Mis sistemas están saturados, señor. Inténtelo en un momento.")
        except anthropic.APIConnectionError:
            raise HTTPException(502, "No puedo conectar con mis sistemas, señor. ¿Hay internet?")
        except anthropic.APIError as e:
            log.exception("Error de la API")
            raise HTTPException(502, f"Mis sistemas han devuelto un error: {e}")
        hablado, detalle = separar_detalle(respuesta)
        return {"tu": texto, "respuesta": hablado, "detalle": detalle}

    def pagina(nombre: str, request: Request) -> str:
        html = (WEB / nombre).read_text(encoding="utf-8")
        # El acceso directo del iPhone guarda su propia sesión: le pasamos el token en la URL.
        sufijo = f"?token={token}" if token else ""
        return html.replace("__TOKEN_QS__", sufijo)

    # --- páginas ---------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request):
        return HTMLResponse(pagina("index.html", request), headers=SIN_CACHE)

    @app.get("/panel", response_class=HTMLResponse)
    def panel(request: Request):
        return HTMLResponse(pagina("panel.html", request), headers=SIN_CACHE)

    @app.get("/manifest.webmanifest")
    def manifest(token: str = ""):
        inicio_url = f"/?token={token}" if token and token_valido(token) else "/"
        return JSONResponse({
            "name": "Jarvis", "short_name": "Jarvis", "start_url": inicio_url, "display": "standalone",
            "background_color": "#05090f", "theme_color": "#05090f", "lang": "es",
            "icons": [{"src": "/icono-180.png", "sizes": "180x180", "type": "image/png"},
                      {"src": "/icono-512.png", "sizes": "512x512", "type": "image/png"}],
        }, media_type="application/manifest+json")

    @app.get("/icono-{tamano}.png")
    def png(tamano: int):
        if tamano not in (180, 512):
            raise HTTPException(404)
        return Response(icono(tamano), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})

    # --- conversación ----------------------------------------------------------

    @app.get("/api/estado")
    def estado():
        return {"voz": voz is not None, "oido": oido is not None, "version": VERSION}

    @app.post("/api/mensaje")
    def mensaje(m: Mensaje):
        return responder(m.texto)

    @app.post("/api/siri", response_class=PlainTextResponse)
    def siri(m: Mensaje):
        """Para el atajo de Siri (iPhone y Apple Watch): devuelve solo el texto a leer."""
        try:
            return responder(m.texto)["respuesta"] or "No le he entendido, señor."
        except HTTPException as e:
            return str(e.detail)

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

    @app.get("/api/avisos")
    def avisos(desde: int = 0):
        """Mensajes que Jarvis ha lanzado por su cuenta (rutinas, recordatorios)."""
        return cerebro.avisos.desde(desde)

    # --- panel -----------------------------------------------------------------

    @app.get("/api/panel")
    def datos_panel():
        agentes = {}
        for nombre in ["cerebro", *cerebro.especialistas]:
            a = cerebro.agente(nombre)
            agentes[nombre] = {
                "rol": a.rol,
                "estadisticas": a.memoria.estadisticas(),
                "aprendizajes": [dict(f) for f in a.memoria.aprendizajes(limite=15)],
                "registros": [dict(f) for f in a.memoria.consultar_registros("", 30)][-20:],
            }
        return {
            "perfil": cerebro.perfil_usuario.datos,
            "rutinas": cerebro.rutinas.lista(),
            "recordatorios": [dict(r) for r in cerebro.recordatorios.activos()],
            "agentes": agentes,
        }

    @app.post("/api/rutina")
    def cambiar_rutina(c: CambioRutina):
        if c.nombre not in cerebro.rutinas.lista():
            raise HTTPException(404, "No existe esa rutina")
        try:
            return cerebro.rutinas.configurar(c.nombre, hora=c.hora, activa=c.activa)
        except ValueError:
            raise HTTPException(400, "Hora no válida (usa HH:MM)")

    @app.delete("/api/recordatorio/{id_}")
    def borrar_recordatorio(id_: int):
        return {"ok": cerebro.recordatorios.borrar(id_)}

    @app.delete("/api/aprendizaje/{agente}/{id_}")
    def borrar_aprendizaje(agente: str, id_: int):
        try:
            return {"ok": cerebro.agente(agente).memoria.olvidar(id_)}
        except KeyError:
            raise HTTPException(404, "No existe ese agente")

    return app
