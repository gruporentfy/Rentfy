"""Configuración global (se puede sobrescribir con variables de entorno)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(nombre: str, defecto: str) -> str:
    return os.getenv(nombre, defecto)


@dataclass
class Config:
    # --- Inteligencia ---
    modelo: str = field(default_factory=lambda: _env("CEREBRO_MODELO", "claude-opus-5-5"))
    # low | medium | high | xhigh | max. Cerebro va en "low" para responder rápido por voz;
    # los especialistas piensan más porque hacen el trabajo de fondo.
    esfuerzo_cerebro: str = field(default_factory=lambda: _env("CEREBRO_ESFUERZO_CEREBRO", "low"))
    esfuerzo: str = field(default_factory=lambda: _env("CEREBRO_ESFUERZO", "medium"))
    max_tokens: int = 16000
    directorio_datos: Path = field(default_factory=lambda: Path(_env("CEREBRO_DATOS", "datos")))

    # --- Tú ---
    ciudad: str = field(default_factory=lambda: _env("JARVIS_CIUDAD", "Bilbao"))
    zona_horaria: str = field(default_factory=lambda: _env("JARVIS_ZONA_HORARIA", "Europe/Madrid"))

    # --- Voz (habla) ---
    voz: str = field(default_factory=lambda: _env("JARVIS_VOZ", "Jorge"))  # voz de macOS (`say -v '?'`)
    velocidad_voz: int = field(default_factory=lambda: int(_env("JARVIS_VELOCIDAD", "180")))
    efecto_jarvis: float = field(default_factory=lambda: float(_env("JARVIS_EFECTO", "0.6")))  # 0 = sin filtro

    # --- Oído ---
    modelo_whisper: str = field(default_factory=lambda: _env("JARVIS_WHISPER", "small"))
    # "hey_jarvis" (preentrenado) o la ruta a un modelo propio .onnx (p. ej. "Oye, Jarvis")
    palabra_activacion: str = field(default_factory=lambda: _env("JARVIS_ACTIVACION", "hey_jarvis"))
    umbral_activacion: float = field(default_factory=lambda: float(_env("JARVIS_UMBRAL", "0.5")))

    # --- Servidor ---
    host: str = field(default_factory=lambda: _env("JARVIS_HOST", "127.0.0.1"))
    puerto: int = field(default_factory=lambda: int(_env("JARVIS_PUERTO", "8765")))
