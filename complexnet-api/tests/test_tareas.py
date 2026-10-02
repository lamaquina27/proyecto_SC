"""
Pruebas de recursos, planificador, tareas y recuperacion.

    python3 -m pytest tests/test_tareas.py -v

Las de integracion arman nodos completos (src.api.Nodo) sobre loopback.
"""

import json
import sys
import threading
import time

import pytest

sys.path.insert(0, ".")

from src.api import Nodo, TareaFallida
from src.discovery import Vecino
from src.resources import GestorRecursos
from src.scheduler import PlanificadorDistribuido

LOCAL = "127.255.255.255"
UDP = 5960


def vecino(node_id, **estado):
    v = Vecino(node_id, node_id, "10.0.0.1", 5001)
    v.estado = estado
    return v


def nodo(nombre, puerto, carpeta, cpu=0.5, **kw):
    kw.setdefault("t_hello", 1.0)
    kw.setdefault("leer_estado", lambda: {"cpu": cpu, "memoria": 0.5,
                                          "ancho_banda": 1.0, "carga": 0.0,
                                          "capacidad": 1})
    return Nodo(nombre, interfaz="lo", difusion=LOCAL, puerto_udp=UDP,
                puerto_tcp=puerto, carpeta_logs=str(carpeta / "logs"),
                carpeta_id=str(carpeta / "ids"), **kw)


def eventos(n, tipo):
    with open(n.registro.ruta, encoding="utf-8") as f:
        return [e for e in map(json.loads, f) if e["evento"] == tipo]


@pytest.fixture
def red(tmp_path):
    creados = []

    def crear(*args, **kw):
        n = nodo(*args, tmp_path, **kw)
        creados.append(n)
        return n

    yield crear
    for n in creados:
        n.detener()


# ------------------------------------------------------------ planificador

def test_formula_de_aptitud():
    p = PlanificadorDistribuido()
    v = vecino("x", cpu=0.8, memoria=0.6, ancho_banda=0.5,
               confiabilidad=1.0, carga=0.2)
    # sin historia propia R = min(1.0, (0+1)/(0+2)) = 0.5
    assert p.calcular_aptitud(v) == pytest.approx(0.8 + 0.6 + 0.5 + 0.5 - 0.2)


def test_se_escoge_el_de_mayor_aptitud():
    p = PlanificadorDistribuido()
    a = vecino("a", cpu=0.9, memoria=0.9)
    b = vecino("b", cpu=0.1, memoria=0.1)
    assert p.seleccionar_nodo([b, a])[0] is a
    assert p.seleccionar_nodo([b, a], excluir={"a"})[0] is b
    assert p.seleccionar_nodo([]) == (None, None)


def test_sin_disponibilidad_no_es_candidato():
    p = PlanificadorDistribuido()
    sin_bateria = vecino("a", cpu=1.0, disponibilidad=0.1)
    normal = vecino("b", cpu=0.1)
    assert p.seleccionar_nodo([sin_bateria, normal])[0] is normal


def test_lo_que_ya_le_mande_cuenta_como_carga():
    p = PlanificadorDistribuido()
    a = vecino("a", cpu=0.6, capacidad=1)
    b = vecino("b", cpu=0.5, capacidad=1)
    assert p.seleccionar_nodo([a, b])[0] is a
    p.sumar_pendiente("a")
    assert p.seleccionar_nodo([a, b])[0] is b


def test_los_fallos_bajan_la_reputacion():
    p = PlanificadorDistribuido()
    assert p.reputacion("a") == 0.5
    p.registrar_fallo("a")
    p.registrar_fallo("a")
    assert p.reputacion("a") == 0.25
    p.registrar_exito("b")
    assert p.reputacion("b") == pytest.approx(2 / 3)


# ------------------------------------------------------------ recursos

def test_carga_y_confiabilidad_propias():
    r = GestorRecursos(max_tareas=2)
    assert r.carga() == 0.0 and r.confiabilidad() == 0.5
    r.tarea_iniciada()
    assert r.carga() == 0.5
    r.tarea_terminada(True)
    assert r.carga() == 0.0
    assert r.confiabilidad() == pytest.approx(2 / 3, abs=0.001)


def test_recursos_registrados_se_publican():
    r = GestorRecursos()
    assert "recursos" not in r.medir()
    r.registrar_recurso("camara", "sensor")
    r.actualizar_recurso("camara", disponible=False)
    assert r.medir()["recursos"] == [{"nombre": "camara", "tipo": "sensor",
                                      "capacidad": 1.0, "disponible": False}]


# ------------------------------------------------------------ tareas

def test_prueba_de_concepto_del_corte_1(red):
    """Nodo 1 pide suma 10 + 20, nodo 2 la ejecuta y devuelve 30."""
    n1 = red("nodo-1", 5961).iniciar()
    n2 = red("nodo-2", 5962).iniciar()
    n2.registrar_operacion("suma", lambda d: d[0] + d[1])
    time.sleep(2.0)

    futuro = n1.enviar_tarea_async("suma", [10, 20])
    assert futuro.result(timeout=10) == 30
    assert futuro.tarea.ejecutor == n2.node_id
    assert futuro.tarea.intentos == 1
    assert [e["ejecutor"] for e in eventos(n1, "tarea_completada")] == \
        ["nodo-2"]
    assert len(eventos(n2, "tarea_recibida")) == 1


def test_va_al_nodo_con_mayor_aptitud(red):
    a = red("nodo-A", 5963).iniciar()
    fuerte = red("fuerte", 5964, cpu=0.9).iniciar()
    debil = red("debil", 5965, cpu=0.1).iniciar()
    for n in (fuerte, debil):
        n.registrar_operacion("suma", sum)
    time.sleep(2.0)
    futuro = a.enviar_tarea_async("suma", [1, 2, 3])
    assert futuro.result(timeout=10) == 6
    assert futuro.tarea.ejecutor == fuerte.node_id


def test_un_error_en_la_funcion_no_se_reasigna(red):
    a = red("nodo-A", 5966).iniciar()
    b = red("nodo-B", 5967).iniciar()
    b.registrar_operacion("division", lambda d: d[0] / d[1])
    time.sleep(2.0)
    futuro = a.enviar_tarea_async("division", [1, 0])
    with pytest.raises(TareaFallida, match="ZeroDivisionError"):
        futuro.result(timeout=10)
    assert futuro.tarea.intentos == 1


def test_si_nadie_la_ofrece_falla_claro(red):
    a = red("nodo-A", 5968).iniciar()
    time.sleep(1.0)
    with pytest.raises(TareaFallida, match="ningun nodo activo ofrece"):
        a.enviar_tarea("regresion", [1, 2])


def test_solo_se_ejecuta_en_el_propio_nodo_si_no_hay_nadie(red):
    a = red("nodo-A", 5969).iniciar()
    a.registrar_operacion("suma", sum)
    time.sleep(1.0)
    futuro = a.enviar_tarea_async("suma", [10, 20])
    assert futuro.result(timeout=10) == 30
    assert futuro.tarea.ejecutor == a.node_id


def test_task_request_pregunta_a_la_red(red):
    """A todavia no sabe que B ofrece 'eco'; pregunta con TASK_REQUEST y B
    se anuncia de una, sin esperar a su siguiente latido."""
    a = red("nodo-A", 5970).iniciar()
    b = red("nodo-B", 5971, t_hello=30.0).iniciar()
    time.sleep(2.0)
    b.registrar_operacion("eco", lambda d: d)
    assert a.que_ofrezcan(["eco"]) == []

    futuro = a.enviar_tarea_async("eco", "hola")
    assert futuro.result(timeout=10) == "hola"
    assert futuro.tarea.ejecutor == b.node_id
    assert len(eventos(a, "tarea_solicitada")) == 1


def test_paralelo_se_reparte(red):
    a = red("nodo-A", 5972).iniciar()
    b = red("nodo-B", 5973).iniciar()
    c = red("nodo-C", 5974).iniciar()

    def lenta(d):
        time.sleep(0.5)
        return d

    for n in (b, c):
        n.registrar_operacion("lenta", lenta)
    time.sleep(2.0)
    futuros = [a.enviar_tarea_async("lenta", i) for i in range(4)]
    assert sorted(f.result(timeout=15) for f in futuros) == [0, 1, 2, 3]
    assert {f.tarea.ejecutor for f in futuros} == {b.node_id, c.node_id}


# ------------------------------------------------------------ recuperacion

def test_se_cae_el_ejecutor_y_se_reasigna(red):
    a = red("nodo-A", 5975, t_sospecha=1.5, t_muerte=3.0).iniciar()
    b = red("nodo-B", 5976, cpu=0.9).iniciar()
    c = red("nodo-C", 5977, cpu=0.1).iniciar()
    soltar = threading.Event()

    def bloqueada(d):
        soltar.wait(20)
        return "de B"

    b.registrar_operacion("trabajo", bloqueada)
    c.registrar_operacion("trabajo", lambda d: "de C")
    time.sleep(2.0)
    try:
        futuro = a.enviar_tarea_async("trabajo", None)
        time.sleep(1.0)
        assert futuro.tarea.ejecutor == b.node_id

        b.detener(despedirse=False)
        assert futuro.result(timeout=15) == "de C"
        assert futuro.tarea.historial == [b.node_id, c.node_id]
        motivos = [e["motivo"] for e in eventos(a, "tarea_reasignada")]
        assert motivos == ["nodo_caido"]
        assert a.planificador.reputacion(b.node_id) < 0.5
    finally:
        soltar.set()


def test_si_no_se_puede_entregar_va_al_siguiente(red):
    a = red("nodo-A", 5978).iniciar()
    b = red("nodo-B", 5979, cpu=0.9).iniciar()
    c = red("nodo-C", 5980, cpu=0.1).iniciar()
    for n in (b, c):
        n.registrar_operacion("suma", sum)
    time.sleep(2.0)

    b.mensajes.detener()
    futuro = a.enviar_tarea_async("suma", [10, 20])
    assert futuro.result(timeout=15) == 30
    assert futuro.tarea.historial == [b.node_id, c.node_id]
    motivos = [e["motivo"] for e in eventos(a, "tarea_reasignada")]
    assert motivos == ["no_entregada"]


def test_si_se_demasiado_se_reasigna_y_gana_el_primero(red):
    a = red("nodo-A", 5981).iniciar()
    b = red("nodo-B", 5982, cpu=0.9).iniciar()
    c = red("nodo-C", 5983, cpu=0.1).iniciar()

    def lenta(d):
        time.sleep(3.0)
        return "de B"

    b.registrar_operacion("trabajo", lenta)
    c.registrar_operacion("trabajo", lambda d: "de C")
    time.sleep(2.0)

    futuro = a.enviar_tarea_async("trabajo", None, timeout=1.0)
    assert futuro.result(timeout=15) == "de C"
    assert futuro.tarea.intentos == 2
    motivos = [e["motivo"] for e in eventos(a, "tarea_reasignada")]
    assert motivos == ["tiempo_agotado"]
    time.sleep(2.5)
    assert len(eventos(a, "tarea_completada")) == 1


def test_se_agotan_los_intentos(red):
    a = red("nodo-A", 5984).iniciar()
    b = red("nodo-B", 5985).iniciar()
    b.registrar_operacion("lenta", lambda d: time.sleep(3.0))
    time.sleep(2.0)
    with pytest.raises(TareaFallida):
        a.enviar_tarea("lenta", None, timeout=0.5, intentos=1)
