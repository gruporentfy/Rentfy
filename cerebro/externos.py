"""Conexiones gratuitas con el exterior: el tiempo (Open-Meteo) y tu calendario (enlace iCal)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Códigos WMO que usa Open-Meteo.
TIEMPO = {
    0: "despejado", 1: "casi despejado", 2: "parcialmente nuboso", 3: "nublado",
    45: "niebla", 48: "niebla con escarcha", 51: "llovizna débil", 53: "llovizna", 55: "llovizna intensa",
    61: "lluvia débil", 63: "lluvia", 65: "lluvia fuerte", 66: "lluvia helada", 67: "lluvia helada fuerte",
    71: "nieve débil", 73: "nieve", 75: "nieve fuerte", 77: "granizo fino",
    80: "chubascos débiles", 81: "chubascos", 82: "chubascos fuertes", 85: "chubascos de nieve",
    86: "chubascos de nieve fuertes", 95: "tormenta", 96: "tormenta con granizo", 99: "tormenta fuerte con granizo",
}


def _get(url: str, timeout: float = 10) -> bytes:
    peticion = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
    with urllib.request.urlopen(peticion, timeout=timeout) as r:
        return r.read()


def tiempo(latitud: float, longitud: float, zona: str, ciudad: str, obtener=_get) -> str:
    """Tiempo actual y previsión de hoy y mañana, en texto natural."""
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": latitud, "longitude": longitud, "timezone": zona, "forecast_days": 2,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })
    d = json.loads(obtener(url))
    actual, diario = d["current"], d["daily"]
    lineas = [
        f"Ahora en {ciudad}: {round(actual['temperature_2m'])} grados "
        f"(sensación {round(actual['apparent_temperature'])}), "
        f"{TIEMPO.get(actual['weather_code'], 'tiempo variable')}, viento {round(actual['wind_speed_10m'])} km/h."
    ]
    for i, nombre in enumerate(["Hoy", "Mañana"]):
        lineas.append(
            f"{nombre}: {TIEMPO.get(diario['weather_code'][i], 'variable')}, "
            f"entre {round(diario['temperature_2m_min'][i])} y {round(diario['temperature_2m_max'][i])} grados, "
            f"probabilidad de lluvia {diario['precipitation_probability_max'][i]}%."
        )
    return "\n".join(lineas)


def eventos_calendario(url_ical: str, zona: str, dias: int = 1, desde: datetime | None = None,
                       obtener=_get) -> str:
    """Eventos de tu calendario en los próximos ``dias`` (a partir de hoy a las 00:00)."""
    import icalendar
    import recurring_ical_events

    tz = ZoneInfo(zona)
    inicio = (desde or datetime.now(tz)).replace(hour=0, minute=0, second=0, microsecond=0)
    fin = inicio + timedelta(days=dias)
    if url_ical.startswith("webcal://"):  # enlaces de iCloud
        url_ical = "https://" + url_ical.removeprefix("webcal://")
    calendario = icalendar.Calendar.from_ical(obtener(url_ical))
    eventos = []
    for ev in recurring_ical_events.of(calendario).between(inicio, fin):
        comienzo = ev.get("DTSTART").dt
        todo_el_dia = not isinstance(comienzo, datetime)
        if not todo_el_dia:
            comienzo = comienzo.astimezone(tz)
        lugar = f" en {ev.get('LOCATION')}" if ev.get("LOCATION") else ""
        orden = datetime(comienzo.year, comienzo.month, comienzo.day, tzinfo=tz) if todo_el_dia else comienzo
        cuando = f"{comienzo:%d/%m} todo el día" if todo_el_dia else f"{comienzo:%d/%m %H:%M}"
        eventos.append((orden, f"- {cuando}: {ev.get('SUMMARY', '(sin título)')}{lugar}"))
    if not eventos:
        return "No hay eventos en el calendario para ese periodo."
    return "\n".join(texto for _, texto in sorted(eventos))
