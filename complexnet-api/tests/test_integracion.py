"""
Pruebas de integracion: tres nodos completos (mensajes + descubrimiento +
registro) y se apaga de golpe el del medio.

    python3 -m pytest tests/test_integracion.py -v

En loopback los tres nodos se oyen directo, asi que "el del medio" es el
nodo B por papel, no por topologia: es el unico que ofrece "camara" y el
unico que esta en el grupo "rescate" junto con C. La prueba de topologia
real (A no oye a C sin pasar por B) se hace en las Raspberry Pi; ver
docs/api/manual.md.
"""

import json
import sys
import time

import pytest

sys.path.insert(0, ".")

from src.communication import APP_MSG, ServicioMensajes
from src.discovery import ACTIVO, INACTIVO, SOSPECHOSO, ServicioDescubrimiento
from src.monitoring import Registro

LOCAL = "127.255.255.255"
UDP = 5900
SOSPECHA = 2.0
MUERTE = 6.0


class Nodo:
    def __init__(self, nombre, node_id, puerto_tcp, servicios, carpeta):
        self.nombre = nombre
        self.carpeta = carpeta
        self.vivo = False
        self.mensajes = ServicioMensajes(node_id, interfaz="lo",
                                         puerto_udp=UDP,
                                         puerto_tcp=puerto_tcp,
                                         difusion=LOCAL)
        self.desc = ServicioDescubrimiento(
            self.mensajes, node_id, nombre,
            leer_estado=lambda: {"cpu": 0.5}, servicios=servicios,
            t_hello=1.0, t_sospecha=SOSPECHA, t_muerte=MUERTE)
        self.registro = Registro(node_id, nombre, carpeta=carpeta)
        self.registro.observar(self.mensajes, self.desc)
        self.recibidos = []
        self.mensajes.al_recibir(
            APP_MSG, lambda m, ip: self.recibidos.append(m.payload["texto"]))

    def prender(self):
        self.mensajes.iniciar()
        self.desc.iniciar()
        self.vivo = True
        return self

    def apagar_de_golpe(self):
        self.vivo = False
        self.desc.detener(despedirse=False)
        self.mensajes.detener()

    def apagar(self):
        if not self.vivo:
            return
        self.vivo = False
        self.desc.detener()
        self.mensajes.detener()
        self.registro.cerrar(self.mensajes)


def leer_log(nodo):
    with open(nodo.registro.ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f]


@pytest.fixture
def red(tmp_path):
    a = Nodo("nodo-A", "idA", 5901, ["sensor"], tmp_path).prender()
    b = Nodo("nodo-B", "idB", 5902, ["camara"], tmp_path).prender()
    c = Nodo("nodo-C", "idC", 5903, ["sensor"], tmp_path).prender()
    b.desc.unirse("rescate")
    c.desc.unirse("rescate")
    time.sleep(2.5)
    yield a, b, c
    for n in (a, b, c):
        n.apagar()


def test_los_tres_se_conocen(red):
    a, _, _ = red
    for n in red:
        otros = {v.nombre for v in n.desc.activos()}
        assert otros == {"nodo-A", "nodo-B", "nodo-C"} - {n.nombre}
    assert [v.nombre for v in a.desc.que_ofrezcan(["camara"])] == ["nodo-B"]


def test_se_cae_el_del_medio(red):
    a, b, c = red
    b_vecino = a.desc.por_nombre("nodo-B")
    assert b_vecino.status == ACTIVO

    b.apagar_de_golpe()

    time.sleep(SOSPECHA + 1.5)
    for n in (a, c):
        assert n.desc.por_nombre("nodo-B").status == SOSPECHOSO
        assert n.desc.por_nombre(
            "nodo-A" if n is c else "nodo-C").status == ACTIVO

    time.sleep(MUERTE - SOSPECHA + 1.5)
    for n in (a, c):
        assert n.desc.por_nombre("nodo-B").status == INACTIVO

    assert a.desc.que_ofrezcan(["camara"]) == []
    assert [v.nombre for v in a.desc.miembros("rescate")] == ["nodo-C"]

    r = a.desc.enviar_a_grupo("rescate", APP_MSG, {"texto": "x" * 3000})
    assert r["via"] == "tcp"
    assert r["entregados"] == ["idC"]
    assert r["fallidos"] == []

    a.mensajes.enviar("127.0.0.1", 5903, APP_MSG, "idC",
                      {"texto": "sigo aqui"})
    time.sleep(0.8)
    assert "sigo aqui" in c.recibidos

    log_a = leer_log(a)
    eventos = [e["evento"] for e in log_a
               if e.get("vecino") == "nodo-B"
               and e["evento"].startswith("vecino_")]
    assert eventos == ["vecino_entra", "vecino_sospechoso", "vecino_sale"]

    reportes = {(e["reporta"], e["status"]) for e in log_a
                if e["evento"] == "reporte_estado"
                and e["vecino"] == "nodo-B"}
    assert ("nodo-C", SOSPECHOSO) in reportes
    assert ("nodo-C", INACTIVO) in reportes


def test_el_del_medio_vuelve(red):
    a, b, c = red
    b.apagar_de_golpe()
    time.sleep(MUERTE + 1.5)
    assert a.desc.por_nombre("nodo-B").status == INACTIVO

    b2 = Nodo("nodo-B", "idB", 5902, ["camara"], a.carpeta).prender()
    b2.desc.unirse("rescate")
    try:
        time.sleep(2.5)
        for n in (a, c):
            assert n.desc.por_nombre("nodo-B").status == ACTIVO
        assert [v.nombre for v in a.desc.que_ofrezcan(["camara"])] == \
            ["nodo-B"]
        assert sorted(v.nombre for v in a.desc.miembros("rescate")) == \
            ["nodo-B", "nodo-C"]
    finally:
        b2.apagar()


def test_mandar_a_un_nodo_caido_avisa(red):
    a, b, _ = red
    b.apagar_de_golpe()
    r = a.mensajes.enviar("127.0.0.1", 5902, APP_MSG, "idB",
                          {"texto": "hola?"}, timeout=1.0, reintentos=1)
    assert r is None
    fallos = [e for e in leer_log(a) if e["evento"] == "fallo_envio"]
    assert len(fallos) == 1
    assert fallos[0]["receiver"] == "idB"
