"""Filtro "IA de película": da a la voz un toque metálico y envolvente al estilo JARVIS.

No imita a ninguna persona: solo procesa la señal (eco corto metálico, brillo y una
pequeña sala), como el efecto de radio de un casco.
"""

from __future__ import annotations

import io
import wave

import numpy as np


def leer_wav(datos: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(datos)) as w:
        frecuencia = w.getframerate()
        canales = w.getnchannels()
        if w.getsampwidth() != 2:
            raise ValueError("Solo se admite WAV de 16 bits")
        senal = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if canales > 1:
        senal = senal.reshape(-1, canales).mean(axis=1)
    return senal, frecuencia


def escribir_wav(senal: np.ndarray, frecuencia: int) -> bytes:
    pcm = (np.clip(senal, -1, 1) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frecuencia)
        w.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _retardo(senal: np.ndarray, muestras: int) -> np.ndarray:
    salida = np.zeros_like(senal)
    if muestras < len(senal):
        salida[muestras:] = senal[: len(senal) - muestras]
    return salida


def efecto_jarvis(senal: np.ndarray, frecuencia: int, intensidad: float = 0.6) -> np.ndarray:
    """Aplica el efecto. ``intensidad`` entre 0 (voz original) y 1 (muy robótica)."""
    if intensidad <= 0 or len(senal) == 0:
        return senal
    ms = lambda x: int(frecuencia * x / 1000)  # noqa: E731

    # 1. Eco muy corto (filtro peine): el timbre "metálico" de la IA.
    metal = senal + 0.45 * intensidad * _retardo(senal, ms(7)) + 0.25 * intensidad * _retardo(senal, ms(13))

    # 2. Quitar graves sordos (paso alto de un polo ~150 Hz) para sonar "por altavoz".
    a = np.exp(-2 * np.pi * 150 / frecuencia)
    paso_alto = np.empty_like(metal)
    previo_x = previo_y = 0.0
    for i, x in enumerate(metal):  # bucle simple; la señal es corta (una frase)
        previo_y = a * (previo_y + x - previo_x)
        previo_x = x
        paso_alto[i] = previo_y
    voz = (1 - 0.5 * intensidad) * metal + 0.5 * intensidad * paso_alto

    # 3. Pequeña sala: unos ecos tenues que dan sensación de "estar en el taller".
    sala = sum(g * _retardo(voz, ms(d)) for d, g in ((41, 0.18), (67, 0.12), (97, 0.08)))
    salida = voz + intensidad * sala

    pico = np.max(np.abs(salida))
    return salida / pico * 0.9 if pico > 0 else salida


def aplicar_a_wav(datos: bytes, intensidad: float) -> bytes:
    senal, frecuencia = leer_wav(datos)
    return escribir_wav(efecto_jarvis(senal, frecuencia, intensidad), frecuencia)
