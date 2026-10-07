"""Lo que comparten todos los agentes: tu perfil, recordatorios, rutinas y avisos."""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path


class ArchivoJSON:
    """Diccionario guardado en disco, seguro entre hilos."""

    def __init__(self, ruta: Path, inicial: dict | None = None):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if self.ruta.exists():
            self.datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            for clave, valor in (inicial or {}).items():
                self.datos.setdefault(clave, copy.deepcopy(valor))
        else:
            self.datos = copy.deepcopy(inicial or {})
            self._guardar()

    def _guardar(self) -> None:
        self.ruta.write_text(json.dumps(self.datos, ensure_ascii=False, indent=2), encoding="utf-8")

    def poner(self, clave: str, valor) -> None:
        with self._lock:
            if valor in (None, ""):
                self.datos.pop(clave, None)
            else:
                self.datos[clave] = valor
            self._guardar()

    def obtener(self, clave: str, defecto=None):
        return self.datos.get(clave, defecto)


class Perfil(ArchivoJSON):
    """Datos básicos del usuario que todos los agentes conocen (nombre, negocios, horarios...)."""

    def texto(self) -> str:
        if not self.datos:
            return "Aún no hay datos en el perfil."
        return "\n".join(f"- {k}: {v}" for k, v in self.datos.items())


DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

RUTINAS_INICIALES = {
    "resumen_manana": {
        "hora": "07:30", "dias": "todos", "activa": True,
        "descripcion": "Resumen de la mañana: tiempo, agenda, entreno, estudio, prioridades del día.",
    },
    "repaso_noche": {
        "hora": "21:30", "dias": "todos", "activa": True,
        "descripcion": "Repaso de la noche: preguntar cómo fue el día (entreno, tareas) y preparar mañana.",
    },
    "revision_semanal": {
        "hora": "19:00", "dias": "domingo", "activa": True,
        "descripcion": "Revisión semanal con cada especialista: qué fue bien, qué ajustar, plan de la semana.",
    },
    "sueno": {
        "hora": "03:30", "dias": "todos", "activa": True,
        "descripcion": "Sueño: cada agente ordena y consolida su memoria (silencioso).",
    },
}


class Rutinas(ArchivoJSON):
    """Tareas automáticas con horario editable (también por voz)."""

    def __init__(self, ruta: Path):
        super().__init__(ruta, {"rutinas": RUTINAS_INICIALES, "ultima_ejecucion": {}})

    def lista(self) -> dict:
        return self.datos["rutinas"]

    def configurar(self, nombre: str, hora: str | None = None, dias: str | None = None,
                   activa: bool | None = None, descripcion: str | None = None) -> dict:
        with self._lock:
            rutina = self.datos["rutinas"].setdefault(
                nombre, {"hora": "09:00", "dias": "todos", "activa": True, "descripcion": ""}
            )
            if hora is not None:
                datetime.strptime(hora, "%H:%M")  # valida el formato
                rutina["hora"] = hora
            if dias is not None:
                rutina["dias"] = dias
            if activa is not None:
                rutina["activa"] = activa
            if descripcion is not None:
                rutina["descripcion"] = descripcion
            self._guardar()
            return rutina

    def pendientes(self, ahora: datetime) -> list[str]:
        """Rutinas cuya hora ya llegó hoy y que aún no se han ejecutado hoy."""
        hoy = ahora.strftime("%Y-%m-%d")
        dia = DIAS_SEMANA[ahora.weekday()]
        listas = []
        for nombre, r in self.datos["rutinas"].items():
            if not r.get("activa", True):
                continue
            dias = r.get("dias", "todos")
            if dias == "laborables":
                if ahora.weekday() >= 5:
                    continue
            elif dias not in ("todos", "") and dia not in dias:
                continue
            h, m = map(int, r["hora"].split(":"))
            hora_rutina = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
            # Solo si la hora llegó hace menos de 30 min (si el Mac estaba apagado, no recupera).
            if hora_rutina <= ahora < hora_rutina + timedelta(minutes=30) \
                    and self.datos["ultima_ejecucion"].get(nombre) != hoy:
                listas.append(nombre)
        return listas

    def marcar_hecha(self, nombre: str, ahora: datetime) -> None:
        with self._lock:
            self.datos["ultima_ejecucion"][nombre] = ahora.strftime("%Y-%m-%d")
            self._guardar()


class Recordatorios:
    def __init__(self, ruta: Path):
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(ruta, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS recordatorios (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "texto TEXT NOT NULL, cuando TEXT NOT NULL, repetir TEXT NOT NULL DEFAULT 'no', "
            "activo INTEGER NOT NULL DEFAULT 1)"
        )
        self._db.commit()

    def crear(self, texto: str, cuando: str, repetir: str = "no") -> int:
        datetime.fromisoformat(cuando)  # valida
        if repetir not in ("no", "diario", "semanal", "laborables"):
            raise ValueError("repetir debe ser: no, diario, semanal o laborables")
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO recordatorios (texto, cuando, repetir) VALUES (?, ?, ?)", (texto, cuando, repetir)
            )
            self._db.commit()
            return cur.lastrowid

    def activos(self) -> list[sqlite3.Row]:
        return self._db.execute("SELECT * FROM recordatorios WHERE activo = 1 ORDER BY cuando").fetchall()

    def borrar(self, id_: int) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE recordatorios SET activo = 0 WHERE id = ?", (id_,))
            self._db.commit()
            return cur.rowcount > 0

    def vencidos(self, ahora: datetime) -> list[sqlite3.Row]:
        """Devuelve los que tocan ya y los reprograma (si se repiten) o los desactiva."""
        with self._lock:
            filas = self._db.execute(
                "SELECT * FROM recordatorios WHERE activo = 1 AND cuando <= ?",
                (ahora.isoformat(timespec="minutes"),),
            ).fetchall()
            for f in filas:
                if f["repetir"] == "no":
                    self._db.execute("UPDATE recordatorios SET activo = 0 WHERE id = ?", (f["id"],))
                    continue
                siguiente = datetime.fromisoformat(f["cuando"])
                paso = timedelta(days=7 if f["repetir"] == "semanal" else 1)
                while siguiente <= ahora or (f["repetir"] == "laborables" and siguiente.weekday() >= 5):
                    siguiente += paso
                self._db.execute(
                    "UPDATE recordatorios SET cuando = ? WHERE id = ?",
                    (siguiente.isoformat(timespec="minutes"), f["id"]),
                )
            self._db.commit()
            return filas


class Avisos:
    """Mensajes que Jarvis lanza por iniciativa propia; la app web los recoge y los lee."""

    def __init__(self, maximo: int = 50):
        self._lista: list[dict] = []
        self._siguiente = 1
        self._maximo = maximo
        self._lock = threading.Lock()

    def publicar(self, titulo: str, texto: str, detalle: str = "") -> dict:
        with self._lock:
            aviso = {
                "id": self._siguiente, "titulo": titulo, "texto": texto, "detalle": detalle,
                "fecha": datetime.now().isoformat(timespec="seconds"),
            }
            self._siguiente += 1
            self._lista = (self._lista + [aviso])[-self._maximo:]
            return aviso

    def desde(self, id_: int) -> list[dict]:
        return [a for a in self._lista if a["id"] > id_]
