"""Oído: convierte tu voz en texto con Whisper, en local y gratis."""

from __future__ import annotations

import io
import threading

import numpy as np

from ..config import Config


class Oido:
    def __init__(self, config: Config):
        self.config = config
        self._modelo = None
        self._carga = threading.Lock()

    def _cargar(self):
        with self._carga:
            if self._modelo is None:
                from faster_whisper import WhisperModel  # import tardío: tarda en cargar

                self._modelo = WhisperModel(self.config.modelo_whisper, device="cpu", compute_type="int8")
        return self._modelo

    def transcribir(self, audio: np.ndarray | bytes) -> str:
        """``audio``: señal float32 a 16 kHz, o un archivo de audio en bytes (webm, m4a, wav...)."""
        fuente = io.BytesIO(audio) if isinstance(audio, (bytes, bytearray)) else audio
        segmentos, _ = self._cargar().transcribe(
            fuente,
            language="es",
            beam_size=1,
            vad_filter=True,
            initial_prompt="Jarvis, asistente personal.",
        )
        return " ".join(s.text.strip() for s in segmentos).strip()
