"""Pruebas sin llamadas reales a la API: se usa un cliente falso con respuestas guionadas."""

from types import SimpleNamespace as NS

import pytest

from cerebro import Cerebro, Config, Memoria


def texto(t):
    return NS(type="text", text=t)


def herramienta(id_, nombre, entrada):
    return NS(type="tool_use", id=id_, name=nombre, input=entrada)


def resp(stop, *bloques):
    return NS(stop_reason=stop, content=list(bloques))


class ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuestas.pop(0)


@pytest.fixture
def config(tmp_path):
    return Config(directorio_datos=tmp_path)


def test_memoria_independiente_por_agente(tmp_path):
    a = Memoria("marketing", tmp_path)
    b = Memoria("entrenamiento", tmp_path)
    a.guardar_aprendizaje("marca", "Tono cercano y directo", 5)
    assert a.buscar("tono")
    assert not b.buscar("tono")
    assert (tmp_path / "marketing" / "memoria.db").exists()
    assert (tmp_path / "entrenamiento" / "memoria.db").exists()


def test_memoria_feedback_y_contexto(tmp_path):
    m = Memoria("estudios", tmp_path)
    m.registrar_feedback(2, "demasiado largo")
    m.registrar("plan de repaso", "Lunes: tema 1")
    ctx = m.contexto()
    assert "2/5 demasiado largo" in ctx and "plan de repaso" in ctx
    assert m.estadisticas()["valoracion_media"] == 2


def test_cerebro_delega_y_el_especialista_aprende(config):
    cliente = ClienteFalso([
        # Cerebro decide delegar a marketing
        resp("tool_use", herramienta("t1", "delegar", {"especialista": "marketing", "orden": "Ideas para Instagram de Rentfy"})),
        # Marketing guarda un aprendizaje y luego responde
        resp("tool_use", herramienta("t2", "guardar_aprendizaje", {"categoria": "marca", "contenido": "Rentfy alquila vehículos", "importancia": 4})),
        resp("end_turn", texto("3 ideas de posts")),
        # Cerebro integra la respuesta
        resp("end_turn", texto("Marketing propone 3 ideas.")),
    ])
    cerebro = Cerebro(config, cliente)
    assert cerebro.pensar("Dame ideas para Instagram") == "Marketing propone 3 ideas."

    mk = cerebro.especialistas["marketing"].memoria
    assert mk.buscar("Rentfy")[0]["contenido"] == "Rentfy alquila vehículos"
    assert mk.estadisticas()["tareas"] == 1
    assert cerebro.memoria.estadisticas()["tareas"] == 1
    # La memoria del especialista no se mezcla con la de otros
    assert not cerebro.especialistas["finanzas"].memoria.buscar("Rentfy")
    # Los resultados de herramientas vuelven al modelo con su id
    resultado = cerebro.historial[2]["content"][0]
    assert resultado["tool_use_id"] == "t1" and resultado["content"] == "3 ideas de posts"


def test_especialista_inexistente_devuelve_error_al_modelo(config):
    cliente = ClienteFalso([
        resp("tool_use", herramienta("t1", "delegar", {"especialista": "astrologia", "orden": "x"})),
        resp("end_turn", texto("ok")),
    ])
    cerebro = Cerebro(config, cliente)
    cerebro.pensar("hola")
    resultado = cerebro.historial[2]["content"][0]
    assert resultado["is_error"] is True


def test_rechazo_no_rompe_el_historial(config):
    cliente = ClienteFalso([resp("refusal")])
    cerebro = Cerebro(config, cliente)
    assert "No puedo" in cerebro.pensar("algo")
    assert cerebro.historial == []


def test_memoria_se_inyecta_en_el_prompt(config):
    cliente = ClienteFalso([resp("end_turn", texto("hola"))])
    cerebro = Cerebro(config, cliente)
    cerebro.memoria.guardar_aprendizaje("preferencia", "Prefiere respuestas cortas", 5)
    cerebro.pensar("hola")
    system = cliente.llamadas[0]["system"]
    assert "Prefiere respuestas cortas" in system[1]["text"]
    assert "cache_control" in system[0]
