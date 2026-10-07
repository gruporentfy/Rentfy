"""Programador: lanza las rutinas (resumen de la mañana, repaso, sueño...) y los recordatorios."""

from __future__ import annotations

import threading
import traceback

from .cerebro import Cerebro, separar_detalle
from .notificaciones import Notificador

TITULOS = {
    "resumen_manana": "Buenos días",
    "repaso_noche": "Repaso del día",
    "revision_semanal": "Revisión semanal",
}


class Programador:
    def __init__(self, cerebro: Cerebro, notificador: Notificador, intervalo: float = 20):
        self.cerebro = cerebro
        self.notificador = notificador
        self.intervalo = intervalo
        self._parar = threading.Event()

    def revisar(self) -> None:
        """Una pasada: dispara lo que toque ahora."""
        ahora = self.cerebro.ahora_local()
        for r in self.cerebro.recordatorios.vencidos(ahora):
            self.notificador.notificar("Recordatorio", f"Señor, le recuerdo: {r['texto']}")

        for nombre in self.cerebro.rutinas.pendientes(ahora):
            self.cerebro.rutinas.marcar_hecha(nombre, ahora)  # antes de ejecutar: nunca se repite
            try:
                mensaje = self.cerebro.ejecutar_rutina(nombre)
            except Exception:
                traceback.print_exc()
                continue
            if mensaje:
                hablado, detalle = separar_detalle(mensaje)
                titulo = TITULOS.get(nombre, nombre.replace("_", " ").capitalize())
                self.notificador.notificar(titulo, hablado, detalle)

    def ejecutar(self) -> None:
        while not self._parar.is_set():
            try:
                self.revisar()
            except Exception:
                traceback.print_exc()
            self._parar.wait(self.intervalo)

    def iniciar(self) -> None:
        threading.Thread(target=self.ejecutar, daemon=True, name="programador").start()

    def parar(self) -> None:
        self._parar.set()
