"""
Pruebas de la capa de comunicacion.

    python3 -m pytest tests -v

Se corren sobre loopback para no necesitar la malla.
"""

import socket
import struct
import sys
import time

import pytest

sys.path.insert(0, ".")

from src.communication import (APP_MSG, MAX_UDP, Mensaje, MensajeMuyGrande,
                               RelojLamport, ServicioMensajes, limite_udp)
from src.discovery import Directorio

LOCAL = "127.255.255.255"


# ------------------------------------------------ formato de los mensajes

def test_mensaje_ida_y_vuelta():
    m = Mensaje(APP_MSG, "n1", "n2", {"texto": "hola"}, seq=3, lamport=9)
    c = Mensaje.from_bytes(m.to_bytes())
    assert c.type == APP_MSG
    assert c.sender == "n1"
    assert c.receiver == "n2"
    assert c.payload["texto"] == "hola"
    assert c.seq == 3 and c.lamport == 9


def test_mensaje_roto_no_rompe_el_nodo():
    assert Mensaje.from_bytes(b"esto no es json") is None
    assert Mensaje.from_bytes(b'{"sender":"n1"}') is None      # falta type
    assert Mensaje.from_bytes(b'[1,2,3]') is None              # no es objeto
    assert Mensaje.from_bytes(b"") is None


def test_mensaje_grande_no_sale_por_udp():
    grande = Mensaje(APP_MSG, "n1", payload={"texto": "x" * (MAX_UDP + 100)})
    assert not grande.cabe_en_udp()


def test_el_grupo_viaja_en_el_mensaje():
    m = Mensaje(APP_MSG, "n1", payload={"texto": "hola"}, grupo="rescate")
    c = Mensaje.from_bytes(m.to_bytes())
    assert c.group == "rescate"
    assert Mensaje.from_bytes(b'{"type":"X","sender":"n1"}').group is None


def test_limite_udp_sale_del_mtu():
    assert limite_udp(None) == MAX_UDP        # no se pudo leer: 1400
    assert limite_udp(65536) == MAX_UDP       # loopback: nunca mas de 1400
    assert limite_udp(1500) == MAX_UDP
    assert limite_udp(1280) == 1280 - 28      # malla con MTU chico: se adapta


def test_reloj_lamport():
    r = RelojLamport()
    assert r.tick() == 1
    assert r.actualizar(7) == 8
    assert r.tick() == 9


# ------------------------------------------------ directorio

def test_directorio_registra_y_actualiza():
    d = Directorio()
    assert d.registrar("id1", "nodo-01", "10.10.0.1", 5001) is True
    assert d.registrar("id1", "nodo-01", "10.10.0.9", 5001) is False
    assert d.buscar("id1").ip == "10.10.0.9"
    assert d.por_nombre("nodo-01").node_id == "id1"
    assert len(d) == 1
    d.olvidar("id1")
    assert len(d) == 0


# ------------------------------------------------ transporte

@pytest.fixture
def par():
    a = ServicioMensajes("A", interfaz="lo", puerto_udp=5700,
                         puerto_tcp=5701, difusion=LOCAL)
    b = ServicioMensajes("B", interfaz="lo", puerto_udp=5700,
                         puerto_tcp=5702, difusion=LOCAL)
    a.iniciar()
    b.iniciar()
    yield a, b
    a.detener()
    b.detener()


def test_puerto_tcp_ocupado_avisa_al_iniciar(par):
    """Antes el nodo seguia a medias, sin TCP, y nadie se enteraba."""
    _, b = par
    otro = ServicioMensajes("Z", interfaz="lo", puerto_udp=5700,
                            puerto_tcp=b.puerto_tcp, difusion=LOCAL)
    with pytest.raises(OSError, match="TCP"):
        otro.iniciar()


def test_difusion_llega_al_otro_nodo(par):
    a, b = par
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m.payload["texto"]))
    a.difundir(APP_MSG, {"texto": "hola malla"})
    time.sleep(1.0)
    assert recibidos == ["hola malla"]


def test_no_me_llegan_mis_propios_mensajes(par):
    a, _ = par
    propios = []
    a.al_recibir(APP_MSG, lambda m, ip: propios.append(m))
    a.difundir(APP_MSG, {"texto": "eco"})
    time.sleep(1.0)
    assert propios == []


def test_mensaje_directo_por_tcp(par):
    a, b = par
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m.payload["texto"]))
    a.enviar("127.0.0.1", b.puerto_tcp, APP_MSG, "B", {"texto": "directo"})
    time.sleep(0.8)
    assert recibidos == ["directo"]


def test_mensaje_que_no_es_para_mi_se_descarta(par):
    a, b = par
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m))
    a.difundir(APP_MSG, {"texto": "x"})
    time.sleep(0.5)
    # el broadcast sin destinatario si llega
    assert len(recibidos) == 1
    a.enviar("127.0.0.1", b.puerto_tcp, APP_MSG, "OTRO", {"texto": "y"})
    time.sleep(0.5)
    assert len(recibidos) == 1


def test_mensaje_grande_por_tcp_llega_entero(par):
    a, b = par
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m.payload["texto"]))
    texto = "y" * 300_000
    a.enviar("127.0.0.1", b.puerto_tcp, APP_MSG, "B", {"texto": texto})
    time.sleep(2.0)
    assert len(recibidos) == 1
    assert len(recibidos[0]) == 300_000


def test_difundir_algo_muy_grande_avisa(par):
    a, _ = par
    with pytest.raises(MensajeMuyGrande):
        a.difundir(APP_MSG, {"texto": "z" * (MAX_UDP + 500)})


def test_dos_mensajes_tcp_seguidos_no_se_pegan(par):
    """
    La prueba del enmarcado. TCP es un flujo: sin la longitud adelante, dos
    mensajes seguidos en la misma conexion llegan pegados y el JSON no
    parsea. Aqui se mandan a proposito en una sola conexion.
    """
    _, b = par
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m.payload["texto"]))

    m1 = Mensaje(APP_MSG, "X", "B", {"texto": "uno"}).to_bytes()
    with socket.create_connection(("127.0.0.1", b.puerto_tcp), timeout=5) as s:
        s.sendall(struct.pack("!I", len(m1)) + m1)
    time.sleep(0.3)
    m2 = Mensaje(APP_MSG, "X", "B", {"texto": "dos"}).to_bytes()
    with socket.create_connection(("127.0.0.1", b.puerto_tcp), timeout=5) as s:
        # mandar la cabecera y el cuerpo por separado, como llegaria partido
        s.sendall(struct.pack("!I", len(m2)))
        time.sleep(0.1)
        s.sendall(m2)
    time.sleep(0.8)
    assert recibidos == ["uno", "dos"]


def test_los_contadores_se_mueven(par):
    a, b = par
    b.al_recibir(APP_MSG, lambda m, ip: None)
    a.difundir(APP_MSG, {"texto": "hola"})
    time.sleep(0.8)
    assert a.metricas()["enviados"] >= 1
    assert a.metricas()["bytes_enviados"] > 0
    assert b.metricas()["recibidos"] >= 1


def test_mismo_mensaje_dos_veces_se_entrega_una(par):
    """Si un reintento TCP llega dos veces, la aplicacion lo ve una sola."""
    _, b = par
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m.payload["texto"]))
    datos = Mensaje(APP_MSG, "X", "B", {"texto": "una vez"}).to_bytes()
    for _ in range(2):
        with socket.create_connection(("127.0.0.1", b.puerto_tcp),
                                      timeout=5) as s:
            s.sendall(struct.pack("!I", len(datos)) + datos)
        time.sleep(0.3)
    time.sleep(0.5)
    assert recibidos == ["una vez"]
    assert b.metricas()["duplicados"] == 1


# ------------------------------------------------ fallos de envio

def test_envio_tcp_fallido_avisa_y_reintenta(par):
    a, _ = par
    fallos = []
    a.cuando_falle(lambda m, ip, puerto, e: fallos.append((m.type, puerto)))
    puerto_cerrado = 5799
    r = a.enviar("127.0.0.1", puerto_cerrado, APP_MSG, "NADIE",
                 {"texto": "x"}, timeout=1.0, reintentos=1)
    assert r is None
    assert fallos == [(APP_MSG, puerto_cerrado)]
    assert a.metricas()["fallos_envio"] == 1
    assert a.metricas()["reintentos"] == 1


def test_envio_tcp_exitoso_no_avisa(par):
    a, b = par
    fallos = []
    a.cuando_falle(lambda *args: fallos.append(args))
    assert a.enviar("127.0.0.1", b.puerto_tcp, APP_MSG, "B",
                    {"texto": "ok"}) is not None
    assert fallos == []


# ------------------------------------------------ multicast

@pytest.fixture
def trio():
    nodos = [ServicioMensajes(n, interfaz="lo", puerto_udp=5750,
                              puerto_tcp=5750 + i, difusion=LOCAL)
             for i, n in enumerate(("A", "B", "C"), start=1)]
    for n in nodos:
        n.iniciar()
    yield nodos
    for n in nodos:
        n.detener()


def test_multicast_solo_llega_a_los_del_grupo(trio):
    a, b, c = trio
    b.unirse("rescate")
    llegadas = {"B": [], "C": []}
    b.al_recibir(APP_MSG, lambda m, ip: llegadas["B"].append(m.group))
    c.al_recibir(APP_MSG, lambda m, ip: llegadas["C"].append(m.group))

    a.multidifundir("rescate", APP_MSG, {"texto": "zona norte"})
    time.sleep(1.0)
    assert llegadas == {"B": ["rescate"], "C": []}
    assert c.metricas()["descartados"] >= 1


def test_abandonar_el_grupo_deja_de_recibir(trio):
    a, b, _ = trio
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m))
    b.unirse("medicos")
    a.multidifundir("medicos", APP_MSG, {"texto": "1"})
    time.sleep(0.8)
    b.abandonar("medicos")
    a.multidifundir("medicos", APP_MSG, {"texto": "2"})
    time.sleep(0.8)
    assert [m.payload["texto"] for m in recibidos] == ["1"]


def test_enviar_a_varios_por_tcp_reporta_quien_fallo(trio):
    a, b, c = trio
    recibidos = []
    for nodo in (b, c):
        nodo.unirse("g")
        nodo.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m.receiver))
    destinos = [("B", "127.0.0.1", b.puerto_tcp),
                ("C", "127.0.0.1", c.puerto_tcp),
                ("MUERTO", "127.0.0.1", 5799)]
    r = a.enviar_a_varios(destinos, APP_MSG, {"texto": "x" * 5000},
                          grupo="g", timeout=1.0, reintentos=0)
    time.sleep(0.8)
    assert sorted(r["entregados"]) == ["B", "C"]
    assert r["fallidos"] == ["MUERTO"]
    assert sorted(recibidos) == ["B", "C"]
