"""
Pruebas del envio de archivos entre nodos (src.communication.archivos).

    python3 -m pytest tests/test_archivos.py -v
"""

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, ".")

from src.api import Nodo
from src.communication import FILE_ACK, FILE_CHUNK

LOCAL = "127.255.255.255"
UDP = 6000


def nodo(nombre, puerto_tcp, carpeta):
    return Nodo(nombre, interfaz="lo", difusion=LOCAL, puerto_udp=UDP,
                puerto_tcp=puerto_tcp, carpeta_logs=str(carpeta / "logs"),
                carpeta_id=str(carpeta / "ids"),
                carpeta_archivos=str(carpeta / f"recibidos-{nombre}"),
                t_hello=1.0)


def escribir(ruta, datos):
    with open(ruta, "wb") as f:
        f.write(datos)
    return str(ruta)


def leer(ruta):
    with open(ruta, "rb") as f:
        return f.read()


@pytest.fixture
def pareja(tmp_path):
    a = nodo("nodo-A", 6001, tmp_path).iniciar()
    b = nodo("nodo-B", 6002, tmp_path).iniciar()
    time.sleep(2.5)
    yield a, b
    a.detener()
    b.detener()


# ------------------------------------------------------------ envio normal

def test_un_archivo_pequeno_llega_igual(pareja, tmp_path):
    a, b = pareja
    llegados = []
    b.cuando_llegue_archivo(llegados.append)
    ruta = escribir(tmp_path / "reporte.txt", "zona norte sin agua".encode())

    r = a.enviar_archivo("nodo-B", ruta)

    assert r["entregado"] is True
    assert r["error"] is None
    assert r["trozos"] == 1
    assert leer(r["ruta"]) == leer(ruta)
    for _ in range(20):
        if llegados:
            break
        time.sleep(0.05)
    assert len(llegados) == 1
    info = llegados[0]
    assert info["nombre"] == "reporte.txt"
    assert info["de"] == a.node_id
    assert info["sha256"] == r["sha256"]


def test_un_archivo_grande_viaja_en_trozos(pareja, tmp_path):
    a, b = pareja
    a.archivos.trozo = 4096
    datos = os.urandom(50_000)
    ruta = escribir(tmp_path / "foto.jpg", datos)
    avance = []

    r = a.enviar_archivo(b.node_id, ruta,
                         al_avanzar=lambda i, n: avance.append((i, n)))

    assert r["entregado"] is True
    assert r["trozos"] == 13
    assert avance[-1] == (13, 13)
    assert leer(r["ruta"]) == datos


def test_un_archivo_vacio_tambien_llega(pareja, tmp_path):
    a, _ = pareja
    r = a.enviar_archivo("nodo-B", escribir(tmp_path / "vacio.txt", b""))
    assert r["entregado"] is True
    assert leer(r["ruta"]) == b""


def test_no_pisa_un_archivo_con_el_mismo_nombre(pareja, tmp_path):
    a, _ = pareja
    r1 = a.enviar_archivo("nodo-B", escribir(tmp_path / "x.txt", b"uno"))
    r2 = a.enviar_archivo("nodo-B", escribir(tmp_path / "x.txt", b"dos"))
    assert os.path.basename(r1["ruta"]) == "x.txt"
    assert os.path.basename(r2["ruta"]) == "x (1).txt"
    assert leer(r1["ruta"]) == b"uno"
    assert leer(r2["ruta"]) == b"dos"


def test_el_nombre_no_puede_salirse_de_la_carpeta(pareja, tmp_path):
    a, b = pareja
    ruta = escribir(tmp_path / "datos.bin", b"123")
    r = a.enviar_archivo("nodo-B", ruta, nombre="../../etc/passwd")
    assert r["entregado"] is True
    assert os.path.dirname(r["ruta"]) == b.archivos.carpeta
    assert os.path.basename(r["ruta"]) == "passwd"


def test_dos_envios_a_la_vez_no_se_mezclan(pareja, tmp_path):
    a, _ = pareja
    a.archivos.trozo = 2048
    rutas = [escribir(tmp_path / f"f{i}.bin", os.urandom(20_000))
             for i in range(3)]
    resultados = [None] * 3

    def mandar(i):
        resultados[i] = a.enviar_archivo("nodo-B", rutas[i])

    hilos = [threading.Thread(target=mandar, args=(i,)) for i in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    for ruta, r in zip(rutas, resultados):
        assert r["entregado"] is True
        assert leer(r["ruta"]) == leer(ruta)


# ------------------------------------------------------------ fallos

def test_destino_desconocido(pareja, tmp_path):
    a, _ = pareja
    with pytest.raises(LookupError):
        a.enviar_archivo("nodo-Z", escribir(tmp_path / "a.txt", b"a"))


def test_destino_caido_devuelve_el_error(pareja, tmp_path):
    a, b = pareja
    b.detener(despedirse=False)
    r = a.enviar_archivo("nodo-B", escribir(tmp_path / "a.txt", b"a"))
    assert r["entregado"] is False
    assert "trozo 1 de 1" in r["error"]


def test_huella_que_no_coincide_se_rechaza(pareja, tmp_path):
    a, b = pareja
    respuestas = []
    a.al_recibir(FILE_ACK, lambda m, ip: respuestas.append(m.payload))

    a.mensajes.enviar("127.0.0.1", b.puerto, FILE_CHUNK, b.node_id, {
        "transfer_id": "falso001", "nombre": "malo.txt", "tamano": 4,
        "sha256": "0" * 64, "indice": 0, "total": 1, "posicion": 0,
        "puerto_tcp": a.puerto, "datos": "aG9sYQ=="})
    time.sleep(1.0)

    assert respuestas and respuestas[0]["ok"] is False
    assert "sha256" in respuestas[0]["error"]
    assert not os.path.exists(os.path.join(b.archivos.carpeta, "malo.txt"))


def test_una_recepcion_abandonada_se_borra(pareja, tmp_path):
    a, b = pareja
    b.archivos.abandono = 0.5
    trozo = {"transfer_id": "medio001", "nombre": "medio.txt", "tamano": 8,
             "sha256": "0" * 64, "total": 2, "puerto_tcp": a.puerto,
             "datos": "aG9sYQ=="}
    a.mensajes.enviar("127.0.0.1", b.puerto, FILE_CHUNK, b.node_id,
                      dict(trozo, indice=0, posicion=0))
    time.sleep(0.3)
    assert len(b.archivos.en_curso()) == 1

    time.sleep(0.5)
    a.mensajes.enviar("127.0.0.1", b.puerto, FILE_CHUNK, b.node_id,
                      dict(trozo, transfer_id="otro0001", indice=0,
                           posicion=0))
    time.sleep(0.3)
    assert [r["transfer_id"] for r in b.archivos.en_curso()] == ["otro0001"]
