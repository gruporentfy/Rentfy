"""Escucha continua: Jarvis espera a oír su nombre, te escucha, piensa y responde.

Flujo:  "Hey Jarvis" -> (pitido) -> hablas -> Jarvis responde en voz alta
        -> se queda unos segundos escuchando por si sigues hablando (sin repetir su nombre).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

import numpy as np

from ..cerebro import Cerebro, separar_detalle
from ..config import Config
from .habla import Voz
from .oido import Oido

FRECUENCIA = 16000
BLOQUE = 1280  # 80 ms: el tamaño que espera openWakeWord
SONIDO_ESCUCHA = "/System/Library/Sounds/Tink.aiff"


def _pitido() -> None:
    if os.path.exists(SONIDO_ESCUCHA):
        subprocess.Popen(["afplay", SONIDO_ESCUCHA])


def _cargar_detector(config: Config):
    import openwakeword
    from openwakeword.model import Model

    activacion = config.palabra_activacion
    if not activacion.endswith((".onnx", ".tflite")):
        openwakeword.utils.download_models([activacion])
    return Model(wakeword_models=[activacion], inference_framework="onnx")


class Escucha:
    def __init__(self, config: Config, cerebro: Cerebro, oido: Oido, voz: Voz):
        self.config = config
        self.cerebro = cerebro
        self.oido = oido
        self.voz = voz
        self.ruido = 0.005  # nivel de ruido de fondo (se ajusta solo)
        self._aviso_dado = False
        self.activa = threading.Event()
        self.activa.set()

    # --- grabación ------------------------------------------------------------

    def _nivel(self, bloque: np.ndarray) -> float:
        return float(np.sqrt(np.mean(bloque.astype(np.float32) ** 2)))

    def grabar_frase(self, stream, espera_inicio: float = 5.0, silencio_fin: float = 0.9,
                     duracion_max: float = 25.0) -> np.ndarray | None:
        """Graba hasta que dejas de hablar. Devuelve None si no dijiste nada."""
        umbral = max(self.ruido * 3, 0.012)
        bloques, hablando = [], False
        silencio = 0.0
        inicio = time.monotonic()
        while time.monotonic() - inicio < duracion_max:
            datos, _ = stream.read(BLOQUE)
            bloque = datos[:, 0].astype(np.float32) / 32768
            nivel = self._nivel(bloque)
            if nivel > umbral:
                hablando, silencio = True, 0.0
            elif hablando:
                silencio += BLOQUE / FRECUENCIA
            if hablando:
                bloques.append(bloque)
                if silencio >= silencio_fin:
                    break
            elif time.monotonic() - inicio > espera_inicio:
                return None
        return np.concatenate(bloques) if bloques else None

    # --- un intercambio -------------------------------------------------------

    def _al_delegar(self, especialista: str, orden: str) -> None:
        # Si va a tardar (está consultando al equipo), Jarvis lo dice una vez.
        if not self._aviso_dado:
            self._aviso_dado = True
            threading.Thread(target=self.voz.decir, args=("Un momento, señor.",), daemon=True).start()
        print(f"  -> consultando a {especialista}...")

    def atender(self, audio: np.ndarray) -> bool:
        """Transcribe, piensa y responde. Devuelve False si no se entendió nada."""
        texto = self.oido.transcribir(audio)
        if not texto:
            return False
        print(f"tú> {texto}")
        self._aviso_dado = False
        try:
            respuesta = self.cerebro.pensar(texto)
        except Exception as e:  # sin conexión, clave inválida, etc.
            print(f"[error] {e}")
            respuesta = "Lo siento, señor, he perdido la conexión con mis sistemas."
        hablado, detalle = separar_detalle(respuesta)
        print(f"jarvis> {hablado}")
        if detalle:
            print(f"\n{detalle}\n")
        self.voz.decir(hablado)
        return True

    # --- bucle principal ------------------------------------------------------

    def ejecutar(self) -> None:
        import sounddevice as sd

        detector = _cargar_detector(self.config)
        self.cerebro.al_delegar = self._al_delegar
        print('Jarvis escuchando. Di "Hey Jarvis"... (Ctrl+C para salir)')
        with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="int16", blocksize=BLOQUE) as stream:
            while True:
                datos, _ = stream.read(BLOQUE)
                if not self.activa.is_set():
                    continue
                bloque = datos[:, 0]
                puntuacion = max(detector.predict(bloque).values())
                if puntuacion < self.config.umbral_activacion:
                    # Aprende el ruido de fondo de la habitación.
                    self.ruido = 0.98 * self.ruido + 0.02 * self._nivel(bloque.astype(np.float32) / 32768)
                    continue

                _pitido()
                audio = self.grabar_frase(stream)
                while audio is not None:
                    stream.stop()  # no escucharse a sí mismo mientras piensa y habla
                    entendido = self.atender(audio)
                    stream.start()
                    if not entendido:
                        break
                    # Modo conversación: unos segundos para seguir hablando sin decir su nombre.
                    audio = self.grabar_frase(stream, espera_inicio=5.0)
                detector.reset()
