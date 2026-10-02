"""
Pruebas de la capa 4 (src.api): la clase Nodo y la identidad persistente.

    python3 -m pytest tests/test_api.py -v
"""

import sys
import time

import pytest

sys.path.insert(0, ".")

from src.api import Nodo, identidad, ruta_identidad
from src.communication import APP_MSG

LOCAL = "127.255.255.255"
UDP = 5950


def nodo(nombre, puerto_tcp, carpeta, **kw):
    return Nodo(nombre, interfaz="lo", difusion=LOCAL, puerto_udp=UDP,
                puerto_tcp=puerto_tcp, carpeta_logs=str(carpeta / "logs"),
                carpeta_id=str(carpeta / "ids"), t_hello=1.0, **kw)


# ------------------------------------------------------------ RF01

def test_la_identidad_sobrevive_al_reinicio(tmp_path):
    primero = identidad("nodo-01", str(tmp_path))
    assert len(primero) == 8
    assert identidad("nodo-01", str(tmp_path)) == primero
    assert identidad("nodo-02", str(tmp_path)) != primero


def test_identidad_danada_se_regenera(tmp_path):
    with open(ruta_identidad("nodo-01", str(tmp_path)), "w") as f:
        f.write("esto no es un id")
    nuevo = identidad("nodo-01", str(tmp_path))
    assert len(nuevo) == 8
    assert identidad("nodo-01", str(tmp_path)) == nuevo


def test_el_nodo_que_reinicia_conserva_su_lugar(tmp_path):
    with nodo("nodo-A", 5951, tmp_path) as a:
        b = nodo("nodo-B", 5952, tmp_path).iniciar()
        time.sleep(2.0)
        id_b = b.node_id
        b.detener(despedirse=False)

        b2 = nodo("nodo-B", 5952, tmp_path).iniciar()
        try:
            time.sleep(2.0)
            assert b2.node_id == id_b
            assert len(a.consultar_estado_red(incluir_caidos=True)) == 1
        finally:
            b2.detener()


# ------------------------------------------------------------ la fachada

@pytest.fixture
def pareja(tmp_path):
    a = nodo("nodo-A", 5953, tmp_path, servicios=["sensor"],
             leer_estado=lambda: {"cpu": 0.9}).iniciar()
    b = nodo("nodo-B", 5954, tmp_path, servicios=["camara"],
             leer_estado=lambda: {"cpu": 0.2}).iniciar()
    time.sleep(2.5)
    yield a, b
    a.detener()
    b.detener()


def test_ver_quien_esta_conectado(pareja):
    a, b = pareja
    red = a.consultar_estado_red()
    assert [v["nombre"] for v in red] == ["nodo-B"]
    assert red[0]["node_id"] == b.node_id


def test_consultar_recursos(pareja):
    a, b = pareja
    assert a.consultar_recursos("nodo-B") == {"cpu": 0.2}
    assert a.consultar_recursos() == {b.node_id: {"cpu": 0.2}}
    assert a.consultar_recursos("nadie") is None


def test_obtener_estado_propio(pareja):
    a, _ = pareja
    e = a.obtener_estado()
    assert e["nombre"] == "nodo-A"
    assert e["activo"] is True
    assert e["recursos"] == {"cpu": 0.9}
    assert e["servicios"] == ["sensor"]


def test_enviar_mensaje_por_nombre_o_id(pareja):
    a, b = pareja
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(m.payload["t"]))
    assert a.enviar_mensaje("nodo-B", {"t": "por nombre"})
    assert a.enviar_mensaje(b.node_id, {"t": "por id"})
    time.sleep(0.5)
    assert recibidos == ["por nombre", "por id"]
    with pytest.raises(LookupError):
        a.enviar_mensaje("nadie", {"t": "x"})


def test_difundir_corto_y_largo(pareja):
    a, b = pareja
    recibidos = []
    b.al_recibir(APP_MSG, lambda m, ip: recibidos.append(len(m.payload["t"])))
    assert a.difundir({"t": "hola"})["via"] == "udp"
    largo = a.difundir({"t": "x" * 5000})
    assert largo["via"] == "tcp"
    assert largo["entregados"] == [b.node_id]
    time.sleep(0.8)
    assert recibidos == [4, 5000]


def test_publicar_servicio(pareja):
    a, b = pareja
    b.publicar_servicio("gps")
    time.sleep(1.5)
    assert [v.nombre for v in a.que_ofrezcan(["gps"])] == ["nodo-B"]


def test_el_vector_de_estado_por_defecto_esta_completo(tmp_path):
    n = nodo("nodo-Z", 5959, tmp_path)
    estado = n.obtener_estado()["recursos"]
    for clave in ("cpu", "memoria", "ancho_banda", "confiabilidad",
                  "disponibilidad", "carga", "almacenamiento"):
        assert 0.0 <= estado[clave] <= 1.0
    assert estado["capacidad"] == 2
