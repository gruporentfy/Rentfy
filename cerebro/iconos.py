"""Genera el icono de Jarvis (un reactor) en PNG sin dependencias externas."""

from __future__ import annotations

import struct
import zlib
from functools import lru_cache

import numpy as np


def _png(rgb: np.ndarray) -> bytes:
    alto, ancho, _ = rgb.shape
    filas = b"".join(b"\x00" + rgb[y].tobytes() for y in range(alto))

    def bloque(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))

    cabecera = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloque(b"IHDR", cabecera) + bloque(b"IDAT", zlib.compress(filas, 9)) + bloque(b"IEND", b"")


@lru_cache(maxsize=4)
def icono(tamano: int) -> bytes:
    y, x = np.mgrid[0:tamano, 0:tamano].astype(np.float32)
    r = np.hypot(x - tamano / 2, y - tamano / 2) / (tamano / 2)  # 0 en el centro, 1 en el borde
    fondo = np.array([5, 9, 15], np.float32)
    cian = np.array([79, 216, 255], np.float32)
    brillo = np.clip(1 - r / 0.55, 0, 1) ** 1.5                     # núcleo
    anillo = np.exp(-((r - 0.72) / 0.035) ** 2)                      # anillo exterior
    angulo = np.arctan2(y - tamano / 2, x - tamano / 2)
    segmentos = (np.cos(angulo * 10) > 0.2) * np.exp(-((r - 0.58) / 0.05) ** 2)
    intensidad = np.clip(brillo + 0.9 * anillo + 0.6 * segmentos, 0, 1)[..., None]
    blanco = np.clip(1 - r / 0.18, 0, 1)[..., None]
    color = fondo + (cian - fondo) * intensidad + (255 - cian) * blanco
    return _png(np.clip(color, 0, 255).astype(np.uint8))
