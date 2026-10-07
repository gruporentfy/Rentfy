"""Almacenamiento propio de cada agente.

Cada agente tiene su propia base SQLite en ``datos/<agente>/memoria.db`` con:

- aprendizajes: lo que el agente sabe de ti (preferencias, hechos, objetivos...).
- historial: tareas recibidas y respuestas dadas.
- feedback: tus valoraciones, para que ajuste su forma de trabajar.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS aprendizajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT NOT NULL,
    contenido TEXT NOT NULL,
    importancia INTEGER NOT NULL DEFAULT 3,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarea TEXT NOT NULL,
    respuesta TEXT NOT NULL,
    fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    valor REAL,
    unidad TEXT NOT NULL DEFAULT '',
    nota TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valoracion INTEGER NOT NULL,
    comentario TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL
);
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Memoria:
    def __init__(self, agente: str, directorio_datos: Path):
        self.agente = agente
        carpeta = Path(directorio_datos) / agente
        carpeta.mkdir(parents=True, exist_ok=True)
        self.ruta = carpeta / "memoria.db"
        # El servidor atiende peticiones desde varios hilos; cada agente se usa de uno en uno.
        self._db = sqlite3.connect(self.ruta, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(ESQUEMA)
        self._db.commit()

    # --- aprendizajes -------------------------------------------------------

    def guardar_aprendizaje(self, categoria: str, contenido: str, importancia: int = 3) -> int:
        importancia = max(1, min(5, int(importancia)))
        cur = self._db.execute(
            "INSERT INTO aprendizajes (categoria, contenido, importancia, creado) VALUES (?, ?, ?, ?)",
            (categoria.strip().lower(), contenido.strip(), importancia, _ahora()),
        )
        self._db.commit()
        return cur.lastrowid

    def olvidar(self, id_aprendizaje: int) -> bool:
        cur = self._db.execute("DELETE FROM aprendizajes WHERE id = ?", (id_aprendizaje,))
        self._db.commit()
        return cur.rowcount > 0

    def buscar(self, consulta: str, limite: int = 10) -> list[sqlite3.Row]:
        palabras = [p for p in consulta.lower().split() if len(p) > 2] or [consulta.lower()]
        condicion = " OR ".join("(lower(contenido) LIKE ? OR categoria LIKE ?)" for _ in palabras)
        params: list = []
        for p in palabras:
            params += [f"%{p}%", f"%{p}%"]
        return self._db.execute(
            f"SELECT * FROM aprendizajes WHERE {condicion} "
            "ORDER BY importancia DESC, id DESC LIMIT ?",
            (*params, limite),
        ).fetchall()

    def aprendizajes(self, limite: int = 40) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM aprendizajes ORDER BY importancia DESC, id DESC LIMIT ?", (limite,)
        ).fetchall()

    # --- historial ----------------------------------------------------------

    def registrar(self, tarea: str, respuesta: str) -> None:
        self._db.execute(
            "INSERT INTO historial (tarea, respuesta, fecha) VALUES (?, ?, ?)",
            (tarea, respuesta, _ahora()),
        )
        self._db.commit()

    def historial_reciente(self, limite: int = 5) -> list[sqlite3.Row]:
        filas = self._db.execute(
            "SELECT * FROM historial ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
        return list(reversed(filas))

    # --- registros (datos con números: entrenos, gastos, ventas, estudio...) --

    def registrar_dato(self, tipo: str, valor: float | None, unidad: str = "", nota: str = "",
                       fecha: str | None = None) -> int:
        cur = self._db.execute(
            "INSERT INTO registros (tipo, valor, unidad, nota, fecha) VALUES (?, ?, ?, ?, ?)",
            (tipo.strip().lower(), valor, unidad.strip(), nota.strip(), fecha or _ahora()),
        )
        self._db.commit()
        return cur.lastrowid

    def consultar_registros(self, tipo: str = "", dias: int = 30) -> list[sqlite3.Row]:
        desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
        return self._db.execute(
            "SELECT * FROM registros WHERE fecha >= ? AND tipo LIKE ? ORDER BY fecha",
            (desde, f"%{tipo.strip().lower()}%"),
        ).fetchall()

    def tipos_registro(self) -> list[str]:
        return [f[0] for f in self._db.execute("SELECT DISTINCT tipo FROM registros ORDER BY tipo")]

    # --- feedback -----------------------------------------------------------

    def registrar_feedback(self, valoracion: int, comentario: str = "") -> None:
        valoracion = max(1, min(5, int(valoracion)))
        self._db.execute(
            "INSERT INTO feedback (valoracion, comentario, fecha) VALUES (?, ?, ?)",
            (valoracion, comentario.strip(), _ahora()),
        )
        self._db.commit()

    def feedback_reciente(self, limite: int = 10) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()

    # --- contexto para el modelo -------------------------------------------

    def contexto(self) -> str:
        """Resumen de la memoria que se inyecta en el prompt del agente."""
        partes = []
        apr = self.aprendizajes()
        if apr:
            partes.append("## Lo que sé del usuario")
            partes += [f"- [{a['id']}] ({a['categoria']}, imp. {a['importancia']}) {a['contenido']}" for a in apr]
        fb = self.feedback_reciente()
        if fb:
            partes.append("\n## Valoraciones recientes del usuario (1-5)")
            partes += [f"- {f['valoracion']}/5 {f['comentario']}".rstrip() for f in fb]
        tipos = self.tipos_registro()
        if tipos:
            partes.append("\n## Registros que llevo (consúltalos con `consultar_registros`)")
            partes.append(", ".join(tipos))
        hist = self.historial_reciente()
        if hist:
            partes.append("\n## Últimas tareas atendidas")
            partes += [f"- ({h['fecha'][:10]}) {h['tarea'][:200]} -> {h['respuesta'][:300]}" for h in hist]
        return "\n".join(partes) if partes else "Aún no tengo recuerdos sobre el usuario."

    def estadisticas(self) -> dict:
        def contar(tabla: str) -> int:
            return self._db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]

        prom = self._db.execute("SELECT AVG(valoracion) FROM feedback").fetchone()[0]
        return {
            "aprendizajes": contar("aprendizajes"),
            "tareas": contar("historial"),
            "valoraciones": contar("feedback"),
            "registros": contar("registros"),
            "valoracion_media": round(prom, 2) if prom else None,
        }

    def cerrar(self) -> None:
        self._db.close()
