"""Pruebas de rutinas, recordatorios, perfil, especialistas por voz, sueño, tiempo, calendario,
seguridad del servidor e integración del programador."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from cerebro import Cerebro, Config
from cerebro.compartido import Recordatorios, Rutinas
from cerebro.externos import eventos_calendario, tiempo
from cerebro.iconos import icono
from cerebro.programador import Programador
from cerebro.servidor import crear_app
from test_cerebro import ClienteFalso, herramienta, resp, texto


@pytest.fixture
def config(tmp_path):
    return Config(directorio_datos=tmp_path)


def _cerebro(config, *respuestas):
    return Cerebro(config, ClienteFalso(respuestas))


# --- rutinas y recordatorios ------------------------------------------------------------

def test_rutinas_por_defecto_y_horario(tmp_path):
    r = Rutinas(tmp_path / "rutinas.json")
    martes_730 = datetime(2026, 10, 6, 7, 31)
    assert r.pendientes(martes_730) == ["resumen_manana"]
    r.marcar_hecha("resumen_manana", martes_730)
    assert r.pendientes(martes_730 + timedelta(minutes=5)) == []           # no se repite hoy
    assert r.pendientes(datetime(2026, 10, 6, 8, 30)) == []                 # fuera de la ventana
    assert r.pendientes(datetime(2026, 10, 7, 7, 30)) == ["resumen_manana"]  # al día siguiente sí
    assert "revision_semanal" in r.pendientes(datetime(2026, 10, 11, 19, 5))  # domingo
    assert "revision_semanal" not in r.pendientes(datetime(2026, 10, 10, 19, 5))


def test_rutinas_editables_y_persistentes(tmp_path):
    r = Rutinas(tmp_path / "rutinas.json")
    r.configurar("resumen_manana", hora="08:00")
    r.configurar("gimnasio", hora="18:00", dias="laborables", descripcion="Recordar ir al gimnasio")
    with pytest.raises(ValueError):
        r.configurar("resumen_manana", hora="25:99")
    r2 = Rutinas(tmp_path / "rutinas.json")
    assert r2.lista()["resumen_manana"]["hora"] == "08:00"
    assert "gimnasio" in r2.pendientes(datetime(2026, 10, 9, 18, 0))       # viernes
    assert "gimnasio" not in r2.pendientes(datetime(2026, 10, 10, 18, 0))  # sábado


def test_recordatorios_unicos_y_repetidos(tmp_path):
    r = Recordatorios(tmp_path / "r.db")
    r.crear("Llamar al gestor", "2026-10-08T10:00")
    r.crear("Tomar creatina", "2026-10-08T09:00", "diario")
    assert r.vencidos(datetime(2026, 10, 8, 8, 59)) == []
    assert [f["texto"] for f in r.vencidos(datetime(2026, 10, 8, 10, 0))] == ["Llamar al gestor", "Tomar creatina"]
    activos = r.activos()
    assert [a["texto"] for a in activos] == ["Tomar creatina"]
    assert activos[0]["cuando"] == "2026-10-09T09:00"
    with pytest.raises(ValueError):
        r.crear("x", "mañana")


# --- Cerebro --------------------------------------------------------------------------

def test_system_congelado_durante_la_sesion(config):
    cliente = ClienteFalso([
        resp("tool_use", herramienta("t1", "guardar_aprendizaje", {"categoria": "dato", "contenido": "Se llama Héctor", "importancia": 5})),
        resp("end_turn", texto("Encantado, Héctor.")),
        resp("end_turn", texto("Claro.")),
    ])
    cerebro = Cerebro(config, cliente)
    cerebro.pensar("Me llamo Héctor")
    cerebro.pensar("¿Qué tal?")
    systems = [json.dumps(l["system"], ensure_ascii=False) for l in cliente.llamadas]
    tools = [json.dumps(l["tools"]) for l in cliente.llamadas]
    assert len(set(systems)) == 1 and len(set(tools)) == 1  # nunca cambian a mitad de conversación
    assert "Se llama Héctor" not in systems[0]
    # La hora va dentro de cada mensaje del usuario
    assert cerebro.historial[0]["content"].startswith("[") and "Bilbao]" in cerebro.historial[0]["content"]
    # Al caducar la sesión, se empieza de cero con la memoria actualizada
    cerebro._ultima_actividad -= 31 * 60
    cliente.respuestas.append(resp("end_turn", texto("Buenos días.")))
    cerebro.pensar("Hola")
    assert "Se llama Héctor" in json.dumps(cliente.llamadas[-1]["system"], ensure_ascii=False)
    assert len(cerebro.historial) == 2


def test_herramientas_de_cerebro(config):
    cerebro = _cerebro(
        config,
        resp("tool_use",
             herramienta("a", "actualizar_perfil", {"clave": "Negocio principal", "valor": "Rentfy"}),
             herramienta("b", "crear_recordatorio", {"texto": "Llamar al banco", "cuando": "2026-10-08T10:00", "repetir": "no"}),
             herramienta("c", "configurar_rutina", {"nombre": "resumen_manana", "hora": "08:15", "dias": "", "activa": "", "descripcion": ""})),
        resp("end_turn", texto("Hecho, señor.")),
    )
    cerebro.pensar("Mi negocio es Rentfy; recuérdame llamar al banco mañana a las 10 y pon el resumen a las 8:15")
    assert cerebro.perfil_usuario.obtener("negocio_principal") == "Rentfy"
    assert cerebro.recordatorios.activos()[0]["texto"] == "Llamar al banco"
    assert cerebro.rutinas.lista()["resumen_manana"]["hora"] == "08:15"
    resultados = cerebro.historial[2]["content"]
    assert not any(r["is_error"] for r in resultados)


def test_perfil_compartido_llega_a_los_especialistas(config):
    cliente = ClienteFalso([resp("end_turn", texto("ok"))])
    cerebro = Cerebro(config, cliente)
    cerebro.perfil_usuario.poner("nombre", "Héctor")
    cerebro.especialistas["entrenamiento"].atender("Plan de hoy")
    assert "nombre: Héctor" in json.dumps(cliente.llamadas[0]["system"], ensure_ascii=False)


def test_crear_especialista_por_voz(config):
    cliente = ClienteFalso([
        resp("tool_use", herramienta("t", "crear_especialista", {"nombre": "viajes", "rol": "organizador de viajes.", "instrucciones": "Planifica viajes.", "web": True})),
        resp("end_turn", texto("He incorporado a viajes al equipo.")),
        resp("end_turn", texto("Delegando...")),
    ])
    cerebro = Cerebro(config, cliente)
    cerebro.pensar("Crea un especialista de viajes")
    assert "viajes" in cerebro.especialistas
    assert cerebro.historial == []  # nueva sesión para que el equipo actualizado esté disponible
    cerebro.pensar("Planifica Roma")
    delegar = next(t for t in cliente.llamadas[-1]["tools"] if t["name"] == "delegar")
    assert "viajes" in delegar["input_schema"]["properties"]["especialista"]["enum"]
    # Persiste tras reiniciar y tiene búsqueda web
    nuevo = Cerebro(config, ClienteFalso([]))
    assert any(t.get("type") == "web_search_20260209" for t in nuevo.especialistas["viajes"].herramientas)
    with pytest.raises(ValueError):
        nuevo._crear_especialista({"nombre": "Mal Nombre", "rol": "", "instrucciones": ""})


def test_registros_de_un_especialista(config):
    cliente = ClienteFalso([
        resp("tool_use", herramienta("t", "registrar_dato", {"tipo": "sentadilla", "valor": 100, "unidad": "kg", "nota": "5x5"})),
        resp("end_turn", texto("Registrado.")),
    ])
    cerebro = Cerebro(config, cliente)
    cerebro.especialistas["entrenamiento"].atender("Hoy sentadilla 5x5 con 100 kg")
    filas = cerebro.especialistas["entrenamiento"].memoria.consultar_registros("sentadilla")
    assert filas[0]["valor"] == 100
    assert "sentadilla" in cerebro.especialistas["entrenamiento"].memoria.contexto()


def test_pause_turn_se_reanuda(config):
    cliente = ClienteFalso([resp("pause_turn", texto("Buscando...")), resp("end_turn", texto("Encontrado."))])
    cerebro = Cerebro(config, cliente)
    assert cerebro.especialistas["marketing"].atender("Tendencias") == "Encontrado."
    assert len(cliente.llamadas) == 2


def test_sueno_consolida_memoria(config):
    salida = {"borrar": [1, 2, 999], "nuevos": [{"categoria": "preferencia", "contenido": "Entrena por la mañana", "importancia": 4}], "resumen": "Fusioné dos recuerdos."}
    cliente = ClienteFalso([resp("end_turn", texto(json.dumps(salida)))])
    cerebro = Cerebro(config, cliente)
    m = cerebro.especialistas["entrenamiento"].memoria
    m.guardar_aprendizaje("habito", "Entrena a las 7")
    m.guardar_aprendizaje("habito", "Prefiere entrenar temprano")
    m.guardar_aprendizaje("dato", "Mide 1,80")
    assert cerebro.especialistas["entrenamiento"].consolidar() == "Fusioné dos recuerdos."
    assert sorted(a["contenido"] for a in m.aprendizajes()) == ["Entrena por la mañana", "Mide 1,80"]
    assert cliente.llamadas[0]["output_config"]["format"]["type"] == "json_schema"


# --- programador ------------------------------------------------------------------------

class NotificadorFalso:
    def __init__(self):
        self.enviados = []

    def notificar(self, titulo, texto, detalle="", hablar=True):
        self.enviados.append((titulo, texto, detalle))


def test_programador_lanza_rutina_y_recordatorio(config, monkeypatch):
    cerebro = _cerebro(config, resp("end_turn", texto("Buenos días, señor. Doce grados.\nDETALLE:\nAgenda completa")))
    ahora = datetime(2026, 10, 8, 7, 30)
    monkeypatch.setattr(cerebro, "ahora_local", lambda: ahora)
    cerebro.recordatorios.crear("Llamar al banco", "2026-10-08T07:30")
    notificador = NotificadorFalso()
    p = Programador(cerebro, notificador)
    p.revisar()
    assert ("Recordatorio", "Señor, le recuerdo: Llamar al banco", "") in notificador.enviados
    assert ("Buenos días", "Buenos días, señor. Doce grados.", "Agenda completa") in notificador.enviados
    assert cerebro.historial[0]["content"].split("\n", 1)[1].startswith("[RUTINA resumen_manana]")
    p.revisar()  # una segunda pasada no repite nada
    assert len(notificador.enviados) == 2


# --- tiempo y calendario --------------------------------------------------------------

def test_tiempo_open_meteo():
    datos = {
        "current": {"temperature_2m": 14.4, "apparent_temperature": 13.2, "weather_code": 61, "wind_speed_10m": 12.3},
        "daily": {"weather_code": [61, 2], "temperature_2m_max": [17.8, 19.1], "temperature_2m_min": [11.2, 10.6],
                  "precipitation_probability_max": [80, 10]},
    }
    urls = []
    t = tiempo(43.26, -2.93, "Europe/Madrid", "Bilbao", obtener=lambda u: (urls.append(u), json.dumps(datos).encode())[1])
    assert "Ahora en Bilbao: 14 grados (sensación 13), lluvia débil" in t
    assert "Mañana: parcialmente nuboso, entre 11 y 19 grados, probabilidad de lluvia 10%." in t
    assert "api.open-meteo.com" in urls[0]


ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
DTSTART:20261008T080000Z
DTEND:20261008T090000Z
SUMMARY:Reuni\xc3\xb3n con el banco
LOCATION:Gran V\xc3\xada
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART:20261001T160000Z
DTEND:20261001T170000Z
RRULE:FREQ=WEEKLY
SUMMARY:Gimnasio
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTART;VALUE=DATE:20261008
SUMMARY:Cumple de Ana
END:VEVENT
END:VCALENDAR
"""


def test_calendario_ical_con_eventos_repetidos():
    desde = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    t = eventos_calendario("https://x", "Europe/Madrid", dias=1, desde=desde, obtener=lambda u: ICS)
    assert t.splitlines() == ["- 08/10 todo el día: Cumple de Ana", "- 08/10 10:00: Reunión con el banco en Gran Vía", "- 08/10 18:00: Gimnasio"]
    assert "No hay eventos" in eventos_calendario("https://x", "Europe/Madrid", dias=1,
                                                   desde=datetime(2026, 10, 9, tzinfo=timezone.utc), obtener=lambda u: ICS)


# --- servidor ---------------------------------------------------------------------------

def test_servidor_protegido_con_token(config):
    cerebro = _cerebro(config, resp("end_turn", texto("Hola, señor.\nDETALLE:\nx")), resp("end_turn", texto("Sí.")))
    app = crear_app(cerebro, token="secreto")
    c = TestClient(app)
    assert c.get("/api/panel").status_code == 401
    assert c.post("/api/siri", json={"texto": "hola"}).status_code == 401
    # Atajo de Siri: cabecera Bearer, respuesta en texto plano y solo la parte hablada
    r = c.post("/api/siri", json={"texto": "hola"}, headers={"Authorization": "Bearer secreto"})
    assert r.text == "Hola, señor." and r.headers["content-type"].startswith("text/plain")
    # Navegador: ?token= deja una cookie para lo siguiente
    r = c.get("/?token=secreto")
    assert r.status_code == 200 and 'manifest.webmanifest?token=secreto' in r.text
    assert c.get("/api/panel").status_code == 200
    # El icono y el manifest son públicos; el manifest solo lleva el token si es correcto
    publico = TestClient(app)
    assert publico.get("/icono-180.png").content.startswith(b"\x89PNG")
    assert publico.get("/manifest.webmanifest?token=malo").json()["start_url"] == "/"
    assert publico.get("/manifest.webmanifest?token=secreto").json()["start_url"] == "/?token=secreto"


def test_panel_y_ediciones(config):
    cerebro = _cerebro(config)
    cerebro.recordatorios.crear("Pagar IVA", "2026-10-20T09:00")
    id_ = cerebro.especialistas["marketing"].memoria.guardar_aprendizaje("marca", "Tono cercano")
    c = TestClient(crear_app(cerebro))
    d = c.get("/api/panel").json()
    assert d["agentes"]["marketing"]["aprendizajes"][0]["contenido"] == "Tono cercano"
    assert "resumen_manana" in d["rutinas"] and d["recordatorios"][0]["texto"] == "Pagar IVA"
    assert c.post("/api/rutina", json={"nombre": "repaso_noche", "hora": "22:00", "activa": False}).json()["hora"] == "22:00"
    assert c.post("/api/rutina", json={"nombre": "repaso_noche", "hora": "99:99"}).status_code == 400
    assert c.delete(f"/api/aprendizaje/marketing/{id_}").json()["ok"] is True
    assert c.delete(f"/api/recordatorio/{d['recordatorios'][0]['id']}").json()["ok"] is True
    assert c.get("/panel").text.startswith("<!doctype html>")
    assert c.get("/api/avisos").json() == []
    cerebro.avisos.publicar("Buenos días", "Doce grados")
    assert c.get("/api/avisos?desde=0").json()[0]["texto"] == "Doce grados"


def test_icono_png():
    assert icono(512)[:8] == b"\x89PNG\r\n\x1a\n"
