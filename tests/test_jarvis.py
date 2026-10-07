"""Pruebas de la parte de voz y del servidor (sin micrófono, sin macOS y sin API real)."""

import numpy as np
from fastapi.testclient import TestClient

from cerebro import Cerebro, Config
from cerebro.cerebro import separar_detalle
from cerebro.servidor import crear_app
from cerebro.voz.activacion import BLOQUE, Escucha
from cerebro.voz.filtro import aplicar_a_wav, efecto_jarvis, escribir_wav, leer_wav
from cerebro.voz.habla import dividir_frases, elegir_voz, limpiar_para_voz
from test_cerebro import ClienteFalso, resp, texto


def _cerebro(tmp_path, *respuestas):
    return Cerebro(Config(directorio_datos=tmp_path), ClienteFalso(respuestas))


class OidoFalso:
    def transcribir(self, audio):
        return "qué tengo hoy" if len(audio) else ""


class VozFalsa:
    def __init__(self):
        self.dicho = []

    def sintetizar(self, t):
        return escribir_wav(np.zeros(100, dtype=np.float32), 22050)

    def decir(self, t):
        self.dicho.append(t)


def test_separar_detalle():
    assert separar_detalle("Listo, señor.\nDETALLE:\n1. a\n2. b") == ("Listo, señor.", "1. a\n2. b")
    assert separar_detalle("Hola") == ("Hola", "")


def test_texto_limpio_para_voz():
    assert limpiar_para_voz("**Hola** _señor_\n- uno\n- dos [web](http://x.com)") == "Hola señor uno dos web"
    assert dividir_frases("Hola. ¿Qué tal? Bien!") == ["Hola.", "¿Qué tal?", "Bien!"]


def test_elegir_voz():
    voces = [("Mónica", "es_ES"), ("Jorge", "es_ES"), ("Jorge (Mejorada)", "es_ES"), ("Juan", "es_MX")]
    assert elegir_voz("Jorge", voces) == "Jorge (Mejorada)"
    assert elegir_voz("Inexistente", [("Juan", "es_MX"), ("Mónica", "es_ES")]) == "Mónica"


def test_filtro_jarvis_conserva_formato():
    senal = np.sin(np.linspace(0, 500, 22050)).astype(np.float32) * 0.3
    salida, frecuencia = leer_wav(aplicar_a_wav(escribir_wav(senal, 22050), 0.6))
    assert frecuencia == 22050 and len(salida) == len(senal)
    assert np.max(np.abs(salida)) <= 0.91
    assert np.array_equal(efecto_jarvis(senal, 22050, 0), senal)


def test_servidor_texto_y_audio(tmp_path):
    cerebro = _cerebro(
        tmp_path,
        resp("end_turn", texto("Tiene dos reuniones, señor.\nDETALLE:\n10:00 Banco\n12:00 Cliente")),
        resp("end_turn", texto("Nada más hoy, señor.")),
    )
    cliente = TestClient(crear_app(cerebro, OidoFalso(), VozFalsa()))

    r = cliente.post("/api/mensaje", json={"texto": "¿Qué tengo hoy?"}).json()
    assert r == {"tu": "¿Qué tengo hoy?", "respuesta": "Tiene dos reuniones, señor.", "detalle": "10:00 Banco\n12:00 Cliente"}

    r = cliente.post("/api/audio", files={"archivo": ("voz.webm", b"audio", "audio/webm")}).json()
    assert r["tu"] == "qué tengo hoy" and r["respuesta"] == "Nada más hoy, señor."

    r = cliente.post("/api/voz", json={"texto": "Hola"})
    assert r.headers["content-type"] == "audio/wav"

    assert cliente.get("/").text.startswith("<!doctype html>")
    assert set(cliente.get("/api/estado").json()["agentes"]) >= {"cerebro", "marketing"}
    assert cliente.post("/api/mensaje", json={"texto": "  "}).status_code == 400


def test_servidor_sin_voz_ni_oido(tmp_path):
    cliente = TestClient(crear_app(_cerebro(tmp_path)))
    assert cliente.post("/api/audio", files={"archivo": ("v", b"x")}).status_code == 503
    assert cliente.get("/api/estado").json()["voz"] is False


class StreamFalso:
    """Simula el micrófono: silencio, luego voz, luego silencio."""

    def __init__(self, niveles):
        self.niveles = list(niveles)

    def read(self, n):
        nivel = self.niveles.pop(0) if self.niveles else 0.0
        return (np.full((n, 1), int(nivel * 32767), dtype=np.int16), False)


def test_grabar_frase_corta_al_callarse(tmp_path):
    escucha = Escucha(Config(directorio_datos=tmp_path), _cerebro(tmp_path), OidoFalso(), VozFalsa())
    stream = StreamFalso([0, 0, 0.2, 0.2, 0.2] + [0] * 20 + [0.2] * 10)
    audio = escucha.grabar_frase(stream, silencio_fin=0.5)
    # 3 bloques de voz + ~0.5 s de silencio final; no incluye la voz posterior
    assert 3 * BLOQUE <= len(audio) <= 11 * BLOQUE


def test_grabar_frase_sin_voz_devuelve_none(tmp_path):
    escucha = Escucha(Config(directorio_datos=tmp_path), _cerebro(tmp_path), OidoFalso(), VozFalsa())
    assert escucha.grabar_frase(StreamFalso([0] * 200), espera_inicio=0.0) is None


def test_atender_habla_solo_la_parte_hablada(tmp_path):
    voz = VozFalsa()
    cerebro = _cerebro(tmp_path, resp("end_turn", texto("Hecho, señor.\nDETALLE:\nplan largo")))
    escucha = Escucha(Config(directorio_datos=tmp_path), cerebro, OidoFalso(), voz)
    assert escucha.atender(np.ones(10, dtype=np.float32)) is True
    assert voz.dicho == ["Hecho, señor."]
