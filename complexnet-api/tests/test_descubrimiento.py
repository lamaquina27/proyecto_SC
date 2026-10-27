"""
Pruebas del descubrimiento de nodos.

    python3 -m pytest tests -v

Corren sobre loopback, no hace falta la malla.
"""

import sys
import time

import pytest

sys.path.insert(0, ".")

from src.communication import ServicioMensajes
from src.discovery import (ACTIVO, HEARTBEAT, HELLO, INACTIVO, NODE_STATUS,
                           RESOURCE_UPDATE, SOSPECHOSO,
                           ServicioDescubrimiento)
from src.discovery.vecino import Vecino

LOCAL = "127.255.255.255"


def armar(nombre, node_id, puerto_tcp, servicios=None, estado=None, **kw):
    m = ServicioMensajes(node_id, interfaz="lo", puerto_udp=5800,
                         puerto_tcp=puerto_tcp, difusion=LOCAL)
    d = ServicioDescubrimiento(m, node_id, nombre,
                               leer_estado=lambda: estado or {"cpu": 0.5},
                               servicios=servicios or [],
                               t_hello=1.0, **kw)
    m.iniciar()
    d.iniciar()
    return m, d


# ------------------------------------------------------------ Vecino

def test_vecino_sabe_que_ofrece():
    v = Vecino("id1", "n1", "10.10.0.1", 5001, ["sensor", "camara"])
    assert v.ofrece(["sensor"])
    assert v.ofrece(["sensor", "camara"])
    assert not v.ofrece(["sensor", "gps"])
    assert v.ofrece([])          # una tarea sin requisitos la puede cualquiera


def test_vecino_arranca_activo():
    v = Vecino("id1", "n1", "10.10.0.1", 5001)
    assert v.disponible()
    assert v.silencio() < 1


# ------------------------------------------------------------ descubrimiento

@pytest.fixture
def dos_nodos():
    m1, d1 = armar("nodo-01", "id1", 5801, ["sensor"])
    m2, d2 = armar("nodo-02", "id2", 5802, ["camara"])
    yield d1, d2
    for d, m in ((d1, m1), (d2, m2)):
        d.detener()
        m.detener()


def test_se_descubren_solos(dos_nodos):
    d1, d2 = dos_nodos
    time.sleep(2.5)
    assert d1.por_nombre("nodo-02") is not None
    assert d2.por_nombre("nodo-01") is not None


def test_aprenden_los_servicios_del_otro(dos_nodos):
    d1, d2 = dos_nodos
    time.sleep(2.5)
    assert d1.por_nombre("nodo-02").servicios == ["camara"]
    assert d2.por_nombre("nodo-01").servicios == ["sensor"]


def test_aprenden_el_estado_del_otro(dos_nodos):
    d1, _ = dos_nodos
    time.sleep(2.5)
    assert d1.por_nombre("nodo-02").estado.get("cpu") == 0.5


def test_filtrar_por_servicio(dos_nodos):
    """El paso 1 del planificador: no todos los nodos sirven para todo."""
    d1, _ = dos_nodos
    time.sleep(2.5)
    assert len(d1.que_ofrezcan(["camara"])) == 1
    assert len(d1.que_ofrezcan(["gps"])) == 0
    assert len(d1.que_ofrezcan([])) == 1


def test_avisa_cuando_entra_un_nodo(dos_nodos):
    d1, _ = dos_nodos
    entraron = []
    d1.cuando_entre(lambda v: entraron.append(v.nombre))

    m3, d3 = armar("nodo-03", "id3", 5803)
    try:
        time.sleep(2.5)
        assert "nodo-03" in entraron
    finally:
        d3.detener()
        m3.detener()


def test_goodbye_saca_al_nodo_de_una(dos_nodos):
    d1, d2 = dos_nodos
    salieron = []
    d1.cuando_salga(lambda nid: salieron.append(nid))
    time.sleep(2.5)
    assert d1.por_nombre("nodo-02") is not None

    d2.detener()          # manda GOODBYE al irse
    time.sleep(1.5)
    assert "id2" in salieron
    assert d1.por_nombre("nodo-02") is None


def test_los_dos_umbrales_de_fallo():
    """
    Se usan tiempos cortos para no esperar 30 segundos en la prueba, pero la
    logica es la misma: primero SOSPECHOSO, despues INACTIVO.
    """
    m1, d1 = armar("nodo-A", "idA", 5811, t_sospecha=2.0, t_muerte=10.0)
    m2, d2 = armar("nodo-B", "idB", 5812, t_sospecha=2.0, t_muerte=10.0)
    caidos = []
    d1.cuando_salga(lambda nid: caidos.append(nid))
    try:
        time.sleep(2.0)
        assert d1.por_nombre("nodo-B").status == ACTIVO

        # Se corta de golpe, sin GOODBYE: como si se le acabara la bateria
        d2._corriendo = False
        m2.detener()

        # margen de 1,5 s sobre cada umbral: la vigilancia revisa cada segundo
        time.sleep(3.5)
        assert d1.por_nombre("nodo-B").status == SOSPECHOSO
        assert caidos == []           # todavia no lo damos por muerto

        time.sleep(8.0)
        assert d1.por_nombre("nodo-B").status == INACTIVO
        assert "idB" in caidos
    finally:
        d1.detener()
        m1.detener()


def test_el_nodo_que_vuelve_se_reintegra():
    m1, d1 = armar("nodo-C", "idC", 5821, t_sospecha=1.0, t_muerte=2.0)
    m2, d2 = armar("nodo-D", "idD", 5822, t_sospecha=1.0, t_muerte=2.0)
    try:
        time.sleep(2.0)
        assert d1.por_nombre("nodo-D").status == ACTIVO

        d2._corriendo = False
        m2.detener()
        time.sleep(3.5)
        assert d1.por_nombre("nodo-D").status == INACTIVO

        # Vuelve a prenderse, sin que nadie lo configure
        m2b, d2b = armar("nodo-D", "idD", 5822, t_sospecha=1.0, t_muerte=2.0)
        try:
            time.sleep(2.0)
            assert d1.por_nombre("nodo-D").status == ACTIVO
        finally:
            d2b.detener()
            m2b.detener()
    finally:
        d1.detener()
        m1.detener()


def test_heartbeat_gigante_no_mata_al_nodo():
    """
    Antes, si el estado no cabia en 1400 bytes, el hilo del latido moria y
    los vecinos daban al nodo por caido aunque estuviera bien.
    """
    enorme = {"cpu": 0.5, "relleno": "x" * 3000}
    m1, d1 = armar("nodo-E", "idE", 5831, t_sospecha=2.0, t_muerte=4.0)
    m2, d2 = armar("nodo-F", "idF", 5832, ["camara"], estado=enorme,
                   t_sospecha=2.0, t_muerte=4.0)
    try:
        time.sleep(5.0)
        v = d1.por_nombre("nodo-F")
        assert v is not None
        assert v.status == ACTIVO
        assert v.servicios == ["camara"]
    finally:
        for d, m in ((d1, m1), (d2, m2)):
            d.detener()
            m.detener()


def test_sospechoso_que_vuelve_no_se_anuncia_como_nuevo():
    m1, d1 = armar("nodo-G", "idG", 5841, t_sospecha=1.5, t_muerte=30.0)
    m2, d2 = armar("nodo-H", "idH", 5842, t_sospecha=1.5, t_muerte=30.0)
    entradas, sospechas = [], []
    try:
        time.sleep(2.0)
        d1.cuando_entre(lambda v: entradas.append(v.nombre))
        d1.cuando_sospeche(lambda nid: sospechas.append(nid))

        d2._corriendo = False
        time.sleep(3.0)
        assert d1.por_nombre("nodo-H").status == SOSPECHOSO
        assert sospechas == ["idH"]

        d2.detener(despedirse=False)
        d2.iniciar()
        time.sleep(2.0)
        assert d1.por_nombre("nodo-H").status == ACTIVO
        assert entradas == []
    finally:
        for d, m in ((d1, m1), (d2, m2)):
            d.detener()
            m.detener()


def test_los_grupos_se_anuncian_en_el_heartbeat(dos_nodos):
    d1, d2 = dos_nodos
    d2.unirse("rescate")
    time.sleep(2.5)
    assert d1.por_nombre("nodo-02").grupos == ["rescate"]
    assert [v.nombre for v in d1.miembros("rescate")] == ["nodo-02"]
    assert d1.miembros("otro") == []


def test_enviar_a_grupo_corto_va_por_udp_y_largo_por_tcp(dos_nodos):
    d1, d2 = dos_nodos
    d2.unirse("rescate")
    recibidos = []
    d2.mensajes.al_recibir("ALERTA",
                           lambda m, ip: recibidos.append(len(m.payload["t"])))
    time.sleep(2.5)

    corto = d1.enviar_a_grupo("rescate", "ALERTA", {"t": "sismo"})
    assert corto["via"] == "udp"

    largo = d1.enviar_a_grupo("rescate", "ALERTA", {"t": "x" * 5000})
    assert largo["via"] == "tcp"
    assert largo["entregados"] == ["id2"]
    time.sleep(1.0)
    assert recibidos == [5, 5000]


# ------------------------------------------------- protocolo del corte 1

def espia(puerto_udp):
    """Un nodo mudo que solo mira lo que pasa por la difusion."""
    m = ServicioMensajes("espia", interfaz="lo", puerto_udp=puerto_udp,
                         puerto_tcp=puerto_udp + 99, difusion=LOCAL)
    vistos = []
    for tipo in (HELLO, HEARTBEAT, RESOURCE_UPDATE, NODE_STATUS):
        m.al_recibir(tipo, lambda msg, ip: vistos.append(msg))
    return m.iniciar(), vistos


def test_heartbeat_y_resource_update_van_separados():
    """Como en el corte 1: HEARTBEAT dice 'sigo vivo', RESOURCE_UPDATE
    lleva los recursos."""
    ojo, vistos = espia(5850)
    m1 = ServicioMensajes("idR", interfaz="lo", puerto_udp=5850,
                          puerto_tcp=5851, difusion=LOCAL).iniciar()
    d1 = ServicioDescubrimiento(m1, "idR", "nodo-R",
                                leer_estado=lambda: {"cpu": 0.7},
                                servicios=["sensor"], t_hello=1.0).iniciar()
    try:
        time.sleep(2.5)
        latidos = [v for v in vistos if v.type == HEARTBEAT]
        recursos = [v for v in vistos if v.type == RESOURCE_UPDATE]
        assert latidos and recursos
        assert all("estado" not in v.payload for v in latidos)
        assert latidos[0].payload["servicios"] == ["sensor"]
        assert recursos[0].payload["estado"] == {"cpu": 0.7}
    finally:
        d1.detener()
        m1.detener()
        ojo.detener()


def test_node_status_avisa_los_cambios_de_estado():
    m1, d1 = armar("nodo-S", "idS", 5861, t_sospecha=1.5, t_muerte=3.0)
    m2, d2 = armar("nodo-T", "idT", 5862, t_sospecha=1.5, t_muerte=3.0)
    m3, d3 = armar("nodo-U", "idU", 5863, t_sospecha=1.5, t_muerte=3.0)
    reportes = []
    d3.cuando_reporten(lambda nid, st, quien: reportes.append((quien, nid, st)))
    try:
        time.sleep(2.0)
        d2.detener(despedirse=False)
        m2.detener()
        time.sleep(5.0)
        assert ("idS", "idT", SOSPECHOSO) in reportes
        assert ("idS", "idT", INACTIVO) in reportes
        assert d3.por_nombre("nodo-T").status == INACTIVO
    finally:
        for d, m in ((d1, m1), (d3, m3)):
            d.detener()
            m.detener()


def test_node_status_de_otro_no_cambia_mi_tabla():
    """Un reporte es informacion, no una orden: si un nodo con mala senal
    dice que otro se cayo, los demas no lo sacan mientras lo sigan oyendo."""
    m1, d1 = armar("nodo-V", "idV", 5871)
    m2, d2 = armar("nodo-W", "idW", 5872)
    falso = ServicioMensajes("idX", interfaz="lo", puerto_udp=5800,
                             puerto_tcp=5879, difusion=LOCAL).iniciar()
    try:
        time.sleep(2.0)
        falso.difundir(NODE_STATUS, {"node_id": "idW", "nombre": "nodo-W",
                                     "status": INACTIVO,
                                     "anterior": ACTIVO})
        time.sleep(0.5)
        assert d1.por_nombre("nodo-W").status == ACTIVO
    finally:
        falso.detener()
        for d, m in ((d1, m1), (d2, m2)):
            d.detener()
            m.detener()


def test_si_dicen_que_estoy_caido_respondo_con_un_latido():
    ojo, vistos = espia(5880)
    m1 = ServicioMensajes("idY", interfaz="lo", puerto_udp=5880,
                          puerto_tcp=5881, difusion=LOCAL).iniciar()
    d1 = ServicioDescubrimiento(m1, "idY", "nodo-Y", t_hello=30.0).iniciar()
    falso = ServicioMensajes("idZ", interfaz="lo", puerto_udp=5880,
                             puerto_tcp=5882, difusion=LOCAL).iniciar()
    try:
        time.sleep(2.0)
        antes = sum(1 for v in vistos
                    if v.type == HEARTBEAT and v.sender == "idY")
        falso.difundir(NODE_STATUS, {"node_id": "idY", "nombre": "nodo-Y",
                                     "status": SOSPECHOSO,
                                     "anterior": ACTIVO})
        time.sleep(0.5)
        despues = sum(1 for v in vistos
                      if v.type == HEARTBEAT and v.sender == "idY")
        assert despues == antes + 1
    finally:
        falso.detener()
        d1.detener()
        m1.detener()
        ojo.detener()
