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


def test_un_trozo_fuera_del_archivo_se_ignora(pareja, tmp_path):
    """Nadie puede escribir mas alla del tamano que anuncio."""
    a, b = pareja
    a.mensajes.enviar("127.0.0.1", b.puerto, FILE_CHUNK, b.node_id, {
        "transfer_id": "lejos001", "nombre": "x.txt", "tamano": 4,
        "sha256": "0" * 64, "indice": 0, "total": 2,
        "posicion": 10 ** 12, "puerto_tcp": a.puerto, "datos": "aG9sYQ=="})
    time.sleep(0.5)
    parcial = os.path.join(b.archivos.carpeta, ".parciales",
                           f"{a.node_id}-lejos001")
    assert os.path.getsize(parcial) == 0
    assert b.archivos.en_curso()[0]["recibidos"] == 0


# ------------------------------------------------------------ compresion

TEXTO = ("Censo albergue norte: 42 personas, 7 heridos leves, falta agua. "
         * 4000).encode()


def esperar(lista):
    for _ in range(40):
        if lista:
            return lista
        time.sleep(0.05)
    return lista


def test_un_texto_viaja_comprimido_y_llega_igual(pareja, tmp_path):
    a, b = pareja
    llegados = []
    b.cuando_llegue_archivo(llegados.append)
    ruta = escribir(tmp_path / "censo.txt", TEXTO)

    r = a.enviar_archivo("nodo-B", ruta)

    assert r["entregado"] is True
    assert r["comprimido"] is True
    assert r["tamano"] == len(TEXTO)
    assert r["tamano_enviado"] < len(TEXTO) / 20
    assert leer(r["ruta"]) == TEXTO
    info = esperar(llegados)[0]
    assert info["comprimido"] is True
    assert info["tamano"] == len(TEXTO)
    assert info["tamano_enviado"] == r["tamano_enviado"]


def test_lo_que_no_se_comprime_va_tal_cual(pareja, tmp_path):
    """Una foto o un zip ya vienen comprimidos: no se gasta CPU en vano."""
    a, _ = pareja
    datos = os.urandom(60_000)
    r = a.enviar_archivo("nodo-B", escribir(tmp_path / "foto.jpg", datos))
    assert r["entregado"] is True
    assert r["comprimido"] is False
    assert r["tamano_enviado"] == len(datos)
    assert leer(r["ruta"]) == datos


def test_un_archivo_pequeno_no_se_comprime(pareja, tmp_path):
    a, _ = pareja
    r = a.enviar_archivo("nodo-B", escribir(tmp_path / "n.txt", b"a" * 500))
    assert r["comprimido"] is False
    assert leer(r["ruta"]) == b"a" * 500


def test_se_puede_obligar_o_prohibir_la_compresion(pareja, tmp_path):
    a, _ = pareja
    texto = escribir(tmp_path / "t.txt", TEXTO)
    azar = escribir(tmp_path / "z.bin", os.urandom(30_000))

    sin = a.enviar_archivo("nodo-B", texto, comprimir=False)
    con = a.enviar_archivo("nodo-B", azar, comprimir=True)

    assert sin["comprimido"] is False and sin["tamano_enviado"] == len(TEXTO)
    assert con["comprimido"] is True
    assert leer(sin["ruta"]) == TEXTO
    assert leer(con["ruta"]) == leer(azar)


def test_comprimido_en_muchos_trozos(pareja, tmp_path):
    a, _ = pareja
    a.archivos.trozo = 1024
    datos = TEXTO + os.urandom(20_000)
    r = a.enviar_archivo("nodo-B", escribir(tmp_path / "mixto.bin", datos))
    assert r["entregado"] is True
    assert r["comprimido"] is True
    assert r["trozos"] > 5
    assert leer(r["ruta"]) == datos


def test_no_deja_temporales_en_quien_envia(pareja, tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    os.makedirs(tmp_path / "tmp")
    a, _ = pareja
    a.enviar_archivo("nodo-B", escribir(tmp_path / "c.txt", TEXTO))
    assert os.listdir(tmp_path / "tmp") == []


def trozo_comprimido(a, b, transfer_id, comprimidos, tamano, compresion="zlib"):
    import base64
    import hashlib
    a.mensajes.enviar("127.0.0.1", b.puerto, FILE_CHUNK, b.node_id, {
        "transfer_id": transfer_id, "nombre": "bomba.txt", "tamano": tamano,
        "sha256": hashlib.sha256(b"x" * tamano).hexdigest(),
        "indice": 0, "total": 1, "posicion": 0, "puerto_tcp": a.puerto,
        "compresion": compresion, "tamano_enviado": len(comprimidos),
        "datos": base64.b64encode(comprimidos).decode()})


def respuestas_de(a):
    respuestas = []
    a.al_recibir(FILE_ACK, lambda m, ip: respuestas.append(m.payload))
    return respuestas


def test_una_bomba_de_compresion_se_rechaza(pareja, tmp_path):
    """Pocos bytes que al descomprimirse pasan de lo anunciado."""
    import zlib
    a, b = pareja
    respuestas = respuestas_de(a)
    trozo_comprimido(a, b, "bomba001", zlib.compress(b"x" * 5_000_000), 100)
    assert esperar(respuestas)[0]["ok"] is False
    assert "mas grande de lo anunciado" in respuestas[0]["error"]
    assert not os.path.exists(os.path.join(b.archivos.carpeta, "bomba.txt"))


def test_datos_comprimidos_danados_se_rechazan(pareja, tmp_path):
    a, b = pareja
    respuestas = respuestas_de(a)
    trozo_comprimido(a, b, "malo0001", b"esto no es zlib", 100)
    assert esperar(respuestas)[0]["ok"] is False
    assert "descomprimir" in respuestas[0]["error"]


def test_una_compresion_desconocida_se_rechaza(pareja, tmp_path):
    import zlib
    a, b = pareja
    respuestas = respuestas_de(a)
    trozo_comprimido(a, b, "lzma0001", zlib.compress(b"x" * 100), 100,
                     compresion="lzma")
    assert esperar(respuestas)[0]["ok"] is False
    assert "no soportada" in respuestas[0]["error"]


def test_un_nodo_viejo_sin_compresion_sigue_funcionando(pareja, tmp_path):
    """Un FILE_CHUNK sin el campo compresion se toma como archivo plano."""
    import base64
    import hashlib
    a, b = pareja
    respuestas = respuestas_de(a)
    a.mensajes.enviar("127.0.0.1", b.puerto, FILE_CHUNK, b.node_id, {
        "transfer_id": "viejo001", "nombre": "viejo.txt", "tamano": 4,
        "sha256": hashlib.sha256(b"hola").hexdigest(), "indice": 0,
        "total": 1, "posicion": 0, "puerto_tcp": a.puerto,
        "datos": base64.b64encode(b"hola").decode()})
    assert esperar(respuestas)[0]["ok"] is True
    assert leer(respuestas[0]["ruta"]) == b"hola"
