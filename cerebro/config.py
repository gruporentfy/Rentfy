"""Configuración global (se puede sobrescribir con variables de entorno)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    modelo: str = field(default_factory=lambda: os.getenv("CEREBRO_MODELO", "claude-opus-5-5"))
    # low | medium | high | xhigh | max
    esfuerzo: str = field(default_factory=lambda: os.getenv("CEREBRO_ESFUERZO", "medium"))
    max_tokens: int = 16000
    directorio_datos: Path = field(
        default_factory=lambda: Path(os.getenv("CEREBRO_DATOS", "datos"))
    )
