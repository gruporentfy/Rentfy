"""Cómo te avisa Jarvis: voz en el Mac, notificación del Mac, la app web y el iPhone (ntfy)."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import urllib.request

from .compartido import Avisos
from .config import Config


class Notificador:
    def __init__(self, config: Config, avisos: Avisos, voz=None):
        self.config = config
        self.avisos = avisos
        self.voz = voz

    def notificar(self, titulo: str, texto: str, detalle: str = "", hablar: bool = True) -> None:
        self.avisos.publicar(titulo, texto, detalle)  # la app web (Mac/iPhone) lo muestra y lo lee
        print(f"\n[{titulo}] {texto}\n")
        self._mac(titulo, texto)
        self._ntfy(titulo, texto)
        if hablar and self.voz and self.config.hablar_avisos:
            threading.Thread(target=self.voz.decir, args=(texto,), daemon=True).start()

    def _mac(self, titulo: str, texto: str) -> None:
        if not shutil.which("osascript"):
            return
        guion = f"display notification {json.dumps(texto[:240])} with title {json.dumps(titulo)}"
        subprocess.Popen(["osascript", "-e", guion], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _ntfy(self, titulo: str, texto: str) -> None:
        if not self.config.ntfy_tema:
            return
        cuerpo = json.dumps({"topic": self.config.ntfy_tema, "title": titulo, "message": texto,
                             "tags": ["robot"]}).encode()
        peticion = urllib.request.Request(self.config.ntfy_servidor, data=cuerpo,
                                          headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(peticion, timeout=10).close()
        except Exception as e:
            print(f"[aviso] No se pudo enviar la notificación al móvil: {e}")
