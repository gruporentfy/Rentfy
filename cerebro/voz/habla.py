"""Habla: convierte texto en la voz de Jarvis.

Usa las voces gratuitas de macOS (comando ``say``), que funcionan sin internet, y les aplica
el filtro JARVIS. Para mejor calidad descarga una voz "mejorada" en
Ajustes del Sistema > Accesibilidad > Contenido leído > Voz del sistema > Gestionar voces.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
from queue import Queue

from ..config import Config
from .filtro import aplicar_a_wav

_MARKDOWN = re.compile(r"[*_#`>|~]+")
_FRASES = re.compile(r"(?<=[.!?…])\s+")


def limpiar_para_voz(texto: str) -> str:
    """Quita símbolos que no deben leerse en voz alta."""
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)  # enlaces markdown -> texto
    texto = re.sub(r"https?://\S+", "el enlace en pantalla", texto)
    texto = _MARKDOWN.sub("", texto)
    texto = re.sub(r"^\s*[-•]\s*", "", texto, flags=re.M)
    return re.sub(r"\s+", " ", texto).strip()


def dividir_frases(texto: str) -> list[str]:
    return [f for f in _FRASES.split(texto) if f.strip()]


class Voz:
    def __init__(self, config: Config):
        self.config = config
        if not shutil.which("say"):
            raise RuntimeError("La voz local necesita macOS (comando `say`).")
        self.nombre_voz = elegir_voz(config.voz, listar_voces_espanol())
        self._hablando = threading.Lock()  # nunca dos frases a la vez (respuesta + aviso)

    def sintetizar(self, texto: str) -> bytes:
        """Devuelve un WAV con la frase dicha por Jarvis."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "voz.wav")
            subprocess.run(
                [
                    "say", "-v", self.nombre_voz, "-r", str(self.config.velocidad_voz),
                    "-o", ruta, "--file-format=WAVE", "--data-format=LEI16@22050",
                    limpiar_para_voz(texto),
                ],
                check=True,
            )
            with open(ruta, "rb") as f:
                datos = f.read()
        return aplicar_a_wav(datos, self.config.efecto_jarvis)

    def reproducir_wav(self, datos: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(datos)
        try:
            subprocess.run(["afplay", f.name], check=False)
        finally:
            os.unlink(f.name)

    def decir(self, texto: str) -> None:
        """Habla por los altavoces del ordenador.

        Prepara la siguiente frase mientras suena la actual, para que empiece a hablar enseguida.
        """
        frases = dividir_frases(limpiar_para_voz(texto))
        if not frases:
            return
        cola: Queue = Queue(maxsize=2)

        def preparar():
            try:
                for frase in frases:
                    cola.put(self.sintetizar(frase))
            except Exception as e:  # nunca dejar la cola esperando
                print(f"[aviso] Error de voz: {e}")
            finally:
                cola.put(None)

        with self._hablando:
            threading.Thread(target=preparar, daemon=True).start()
            while (audio := cola.get()) is not None:
                self.reproducir_wav(audio)


def listar_voces_espanol() -> list[tuple[str, str]]:
    """Voces de macOS instaladas en español: [(nombre, idioma), ...]."""
    salida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    voces = []
    for linea in salida.splitlines():
        m = re.match(r"^(.+?)\s+(es_[A-Z]{2})\s", linea)
        if m:
            voces.append((m.group(1).strip(), m.group(2)))
    return voces


_CALIDAD = ("premium", "mejorada", "enhanced")
# Voces masculinas de macOS en español: Jarvis suena a mayordomo, no a locutora.
_MASCULINAS = ("jorge", "diego", "juan", "carlos", "eddy", "reed", "rocko", "grandpa")


def elegir_voz(preferida: str, voces: list[tuple[str, str]]) -> str:
    """La voz pedida (en su mejor calidad si está); si falta, la mejor voz masculina en español."""
    def puntuar(voz: tuple[str, str]) -> tuple:
        nombre, idioma = voz
        bajo = nombre.lower()
        return (
            preferida.lower() in bajo,
            any(m in bajo for m in _MASCULINAS),
            any(c in bajo for c in _CALIDAD),
            idioma == "es_ES",
        )

    if not voces:
        print("[aviso] No hay voces en español instaladas; se usará la del sistema.")
        return preferida
    mejor = max(voces, key=puntuar)
    if preferida.lower() not in mejor[0].lower():
        print(f"[aviso] La voz '{preferida}' no está instalada; uso '{mejor[0]}'. Para la voz de Jarvis, "
              "descarga 'Jorge (Mejorada)' en Ajustes > Accesibilidad > Contenido leído > Gestionar voces.")
    return mejor[0]
