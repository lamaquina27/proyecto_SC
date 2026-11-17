"""
Mediciones experimentales de ComplexNet API: latencia, escalabilidad y
tolerancia a fallos.

En un solo computador (levanta varios nodos sobre loopback):

    python experimentos/medir.py todo            # todo, unos 12 minutos
    python experimentos/medir.py latencia        # o una sola parte
    python experimentos/medir.py todo --rapido   # menos repeticiones, ~4 min

Partes: latencia, tareas, archivos, escalabilidad, fallos.

En la malla real (desde un equipo de la malla, con la mensajeria abierta en
los demas):

    sudo python3 experimentos/medir.py malla

Cada parte guarda sus datos crudos y su resumen en
experimentos/resultados/<parte>.json. Las graficas salen con:

    python experimentos/graficas.py

Se corre desde la carpeta complexnet-api/.
"""

import argparse
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
import threading
import time
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, ".."))

from src.api import Nodo
from src.communication import PING, PONG, malla

LOCAL = "127.255.255.255"
RESULTADOS = os.path.join(AQUI, "resultados")


# ---------------------------------------------------------------- ayudantes

def resumen(valores):
    """Media, mediana y percentiles de una lista de numeros."""
    if not valores:
        return {"n": 0}
    orden = sorted(valores)

    def percentil(p):
        k = (len(orden) - 1) * p / 100
        i = int(k)
        j = min(i + 1, len(orden) - 1)
        return orden[i] + (orden[j] - orden[i]) * (k - i)

    return {
        "n": len(orden),
        "media": round(statistics.fmean(orden), 3),
        "mediana": round(percentil(50), 3),
        "p95": round(percentil(95), 3),
        "p99": round(percentil(99), 3),
        "min": round(orden[0], 3),
        "max": round(orden[-1], 3),
        "desv": round(statistics.pstdev(orden), 3),
    }


def ms(segundos):
    return segundos * 1000.0


def guardar(parte, datos):
    os.makedirs(RESULTADOS, exist_ok=True)
    datos["entorno"] = entorno()
    ruta = os.path.join(RESULTADOS, f"{parte}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=1, ensure_ascii=False)
    print(f"  -> guardado en {os.path.relpath(ruta)}")


def entorno():
    return {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "sistema": platform.platform(),
        "python": platform.python_version(),
        "nucleos": os.cpu_count(),
        "equipo": platform.node(),
    }


def titulo(texto):
    print()
    print("=" * 70)
    print(texto)
    print("=" * 70)


def apagar_de_golpe(nodo):
    """Simula una caida real (sin bateria): el nodo deja de mandar todo,
    incluidos los resultados de las tareas que estaba haciendo."""
    nodo.mensajes.enviar = lambda *args, **kwargs: None
    nodo.mensajes._difundir_mensaje = lambda *args, **kwargs: None
    nodo.detener(despedirse=False)


def esperar(condicion, limite, cada=0.05):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(cada)
    return condicion()


class Laboratorio:
    """Varios nodos en este mismo computador, sobre loopback."""

    def __init__(self, puerto_udp, puerto_tcp):
        self.puerto_udp = puerto_udp
        self.siguiente_tcp = puerto_tcp
        self.carpeta = tempfile.mkdtemp(prefix="complexnet-lab-")
        self.nodos = []

    def nodo(self, nombre, iniciar=True, **opciones):
        opciones.setdefault("t_hello", 1.0)
        n = Nodo(nombre, interfaz="lo", difusion=LOCAL,
                 puerto_udp=self.puerto_udp, puerto_tcp=self.siguiente_tcp,
                 carpeta_logs=None,
                 carpeta_id=os.path.join(self.carpeta, "ids"),
                 carpeta_archivos=os.path.join(self.carpeta, nombre),
                 **opciones)
        self.siguiente_tcp += 1
        n.cuando_falle(lambda *args: None)
        self.nodos.append(n)
        return n.iniciar() if iniciar else n

    def se_ven(self, nodos, limite=30.0):
        def todos():
            return all(len(n.descubrimiento.activos()) >= len(nodos) - 1
                       for n in nodos)
        return esperar(todos, limite)

    def cerrar(self):
        for n in self.nodos:
            try:
                n.detener(despedirse=False)
            except Exception:
                pass
        self.nodos = []
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cerrar()


# ---------------------------------------------------------------- latencia

def medir_latencia(rapido):
    titulo("1. LATENCIA DE MENSAJES (loopback)")
    n_udp = 100 if rapido else 300
    n_tcp = 15 if rapido else 40
    n_ping = 40 if rapido else 100
    tamanos = [100, 1_000, 10_000, 100_000, 1_000_000]
    datos = {"modo": "loopback"}

    with Laboratorio(6100, 6101) as lab:
        a = lab.nodo("lat-A")
        b = lab.nodo("lat-B")
        lab.se_ven([a, b])

        llegadas = {}
        b.al_recibir("LAT_UDP", lambda m, ip: llegadas.setdefault(
            m.payload["i"], time.perf_counter() - m.payload["t0"]))
        for i in range(n_udp):
            a.mensajes.difundir("LAT_UDP", {"i": i, "t0": time.perf_counter()})
            time.sleep(0.01)
        time.sleep(1.0)
        udp = [ms(v) for v in llegadas.values()]
        datos["udp_difusion"] = {"enviados": n_udp, "recibidos": len(udp),
                                 "perdidos": n_udp - len(udp),
                                 "resumen_ms": resumen(udp), "crudo_ms": udp}
        print(f"  UDP difusion   : mediana {resumen(udp)['mediana']:.2f} ms, "
              f"p95 {resumen(udp)['p95']:.2f} ms, "
              f"perdidos {n_udp - len(udp)}/{n_udp}")

        tcp = {}
        actual = []
        listo = threading.Event()

        def al_llegar_tcp(m, ip):
            actual.append(time.perf_counter() - m.payload["t0"])
            listo.set()

        b.al_recibir("LAT_TCP", al_llegar_tcp)
        for _ in range(30):
            listo.clear()
            a.enviar_mensaje("lat-B", {"t0": time.perf_counter()},
                             tipo="LAT_TCP")
            listo.wait(10)
        for tamano in tamanos:
            actual.clear()
            relleno = "x" * tamano
            for _ in range(n_tcp):
                listo.clear()
                a.enviar_mensaje("lat-B", {"t0": time.perf_counter(),
                                           "relleno": relleno},
                                 tipo="LAT_TCP")
                listo.wait(10)
            valores = [ms(v) for v in actual]
            tcp[str(tamano)] = {"resumen_ms": resumen(valores),
                                "crudo_ms": valores}
            print(f"  TCP {tamano:>9,} B: mediana "
                  f"{resumen(valores)['mediana']:.2f} ms, "
                  f"p95 {resumen(valores)['p95']:.2f} ms")
        datos["tcp_por_tamano"] = tcp

        rtt = []
        respuesta = threading.Event()
        a.al_recibir("LAT_PONG", lambda m, ip: (
            rtt.append(time.perf_counter() - m.payload["t0"]),
            respuesta.set()))
        b.al_recibir("LAT_PING", lambda m, ip: b.enviar_mensaje(
            m.sender, {"t0": m.payload["t0"]}, tipo="LAT_PONG"))
        for _ in range(n_ping):
            respuesta.clear()
            a.enviar_mensaje("lat-B", {"t0": time.perf_counter()},
                             tipo="LAT_PING")
            respuesta.wait(10)
        rtt_ms = [ms(v) for v in rtt]
        datos["ping_ida_y_vuelta"] = {"resumen_ms": resumen(rtt_ms),
                                      "crudo_ms": rtt_ms}
        print(f"  Ping (TCP ida y vuelta): mediana "
              f"{resumen(rtt_ms)['mediana']:.2f} ms")

    guardar("latencia", datos)
    return datos


# ---------------------------------------------------------------- tareas

def medir_tareas(rapido):
    titulo("2. TAREAS: latencia y reparto en paralelo (loopback)")
    datos = {"modo": "loopback"}
    n = 40 if rapido else 100

    with Laboratorio(6200, 6201) as lab:
        a = lab.nodo("tar-A")
        b = lab.nodo("tar-B")
        b.registrar_operacion("eco", lambda d: d)
        lab.se_ven([a, b])
        esperar(lambda: a.que_ofrezcan(["eco"]), 5)
        tiempos = []
        for i in range(n):
            t0 = time.perf_counter()
            a.enviar_tarea("eco", i)
            tiempos.append(ms(time.perf_counter() - t0))
        datos["ida_y_vuelta"] = {"resumen_ms": resumen(tiempos),
                                 "crudo_ms": tiempos}
        print(f"  Tarea ida y vuelta (TASK_ASSIGN + TASK_RESULT): mediana "
              f"{resumen(tiempos)['mediana']:.2f} ms, "
              f"p95 {resumen(tiempos)['p95']:.2f} ms")

    trabajo = 0.25
    cuantas = 16 if rapido else 32
    ejecutores = [1, 2, 4] if rapido else [1, 2, 4, 8]
    reparto = []
    for k in ejecutores:
        with Laboratorio(6300 + k * 20, 6301 + k * 20) as lab:
            a = lab.nodo("rep-A")
            nodos = [lab.nodo(f"rep-E{i}") for i in range(k)]
            for e in nodos:
                e.registrar_operacion("trabajo",
                                      lambda d: time.sleep(trabajo) or d)
            lab.se_ven([a] + nodos)
            esperar(lambda: len(a.que_ofrezcan(["trabajo"])) == k, 10)
            t0 = time.perf_counter()
            futuros = [a.enviar_tarea_async("trabajo", i, timeout=120)
                       for i in range(cuantas)]
            for f in futuros:
                f.result()
            total = time.perf_counter() - t0
            por_nodo = {}
            for f in futuros:
                quien = f.tarea.ejecutor
                por_nodo[quien] = por_nodo.get(quien, 0) + 1
            reparto.append({"ejecutores": k, "segundos": round(total, 3),
                            "tareas_por_nodo": sorted(por_nodo.values())})
            print(f"  {cuantas} tareas de {trabajo} s con {k} ejecutor(es): "
                  f"{total:.2f} s  reparto {sorted(por_nodo.values())}")
    base = reparto[0]["segundos"]
    for r in reparto:
        r["aceleracion"] = round(base / r["segundos"], 2)
        r["ideal"] = r["ejecutores"]
    datos["reparto"] = {"tareas": cuantas, "segundos_por_tarea": trabajo,
                        "max_tareas_por_nodo": 2, "corridas": reparto}
    guardar("tareas", datos)
    return datos


# ---------------------------------------------------------------- archivos

def medir_archivos(rapido):
    titulo("3. ENVIO DE ARCHIVOS: velocidad y compresion (loopback)")
    tamanos = [100_000, 1_000_000] if rapido else [100_000, 1_000_000,
                                                    10_000_000]
    repeticiones = 2 if rapido else 3
    filas = []
    linea = ("Albergue norte, 2026-11-17 08:15, 42 personas, 7 heridos, "
             "temperatura 23.4 C, humedad 68 %, presion 1012 hPa\n").encode()

    with Laboratorio(6400, 6401) as lab:
        a = lab.nodo("arc-A")
        b = lab.nodo("arc-B")
        lab.se_ven([a, b])
        for tamano in tamanos:
            for clase in ("texto", "aleatorio"):
                ruta = os.path.join(lab.carpeta, f"{clase}-{tamano}.bin")
                with open(ruta, "wb") as f:
                    if clase == "texto":
                        f.write((linea * (tamano // len(linea) + 1))[:tamano])
                    else:
                        f.write(os.urandom(tamano))
                for comprimir in (None, False):
                    tiempos = []
                    r = None
                    for _ in range(repeticiones):
                        t0 = time.perf_counter()
                        r = a.enviar_archivo("arc-B", ruta,
                                             comprimir=comprimir,
                                             timeout=120)
                        tiempos.append(time.perf_counter() - t0)
                    segundos = statistics.median(tiempos)
                    fila = {"tamano": tamano, "clase": clase,
                            "compresion": "auto" if comprimir is None
                            else "no",
                            "comprimido": r["comprimido"],
                            "entregado": r["entregado"],
                            "bytes_enviados": r["tamano_enviado"],
                            "segundos": round(segundos, 4),
                            "mb_por_s": round(tamano / 1e6 / segundos, 2)}
                    filas.append(fila)
                    print(f"  {clase:<9} {tamano / 1e6:>5.1f} MB "
                          f"compresion={fila['compresion']:<4}: "
                          f"{segundos:6.3f} s, "
                          f"{fila['mb_por_s']:7.2f} MB/s, "
                          f"viajaron {r['tamano_enviado'] / 1e6:.3f} MB")
    guardar("archivos", {"modo": "loopback", "filas": filas})
    return filas


# ---------------------------------------------------------------- escalabilidad

def medir_escalabilidad(rapido):
    titulo("4. ESCALABILIDAD DEL DESCUBRIMIENTO (loopback, t_hello = 5 s)")
    tamanos = [3, 5, 10] if rapido else [3, 5, 10, 20, 30]
    ventana = 10.0 if rapido else 20.0
    t_hello = 5.0
    filas = []
    for i, n in enumerate(tamanos):
        with Laboratorio(6500 + i * 50, 6501 + i * 50) as lab:
            nodos = [lab.nodo(f"esc-{j}", iniciar=False, t_hello=t_hello)
                     for j in range(n)]
            t0 = time.perf_counter()
            for nodo in nodos:
                nodo.iniciar()
            ultimo = time.perf_counter()
            convergio = lab.se_ven(nodos, limite=60)
            convergencia = time.perf_counter() - ultimo

            # arranque: lo que recibe cada nodo desde que arranca hasta 3 s
            # despues de que arranco el ultimo (la rafaga de HELLO)
            time.sleep(max(0.0, ultimo + 3.0 - time.perf_counter()))
            arranque = [nodo.mensajes.metricas()["recibidos"]
                        for nodo in nodos]

            # regimen estable: se deja pasar la rafaga y se mide una ventana
            time.sleep(max(0.0, ultimo + 2 * t_hello + 3.0
                           - time.perf_counter()))
            antes = [nodo.mensajes.metricas() for nodo in nodos]
            time.sleep(ventana)
            despues = [nodo.mensajes.metricas() for nodo in nodos]
            msgs = [(d["recibidos"] - x["recibidos"]) / ventana
                    for x, d in zip(antes, despues)]
            enviados = [(d["enviados"] - x["enviados"]) / ventana
                        for x, d in zip(antes, despues)]
            kb = [(d["bytes_recibidos"] - x["bytes_recibidos"]) / ventana / 1024
                  for x, d in zip(antes, despues)]
            fila = {
                "nodos": n, "convergio": convergio,
                "inicio_de_todos_s": round(ultimo - t0, 3),
                "convergencia_s": round(convergencia, 3),
                "arranque_recibidos_por_nodo": round(
                    statistics.fmean(arranque), 1),
                "teoria_arranque_por_nodo": 3 * (n - 1) + 6 * (n - 1) ** 2,
                "recibidos_por_nodo_s": round(statistics.fmean(msgs), 2),
                "enviados_por_nodo_s": round(statistics.fmean(enviados), 2),
                "kb_recibidos_por_nodo_s": round(statistics.fmean(kb), 2),
                "teoria_recibidos_por_nodo_s": round(2 * (n - 1) / t_hello, 2),
                "mensajes_red_s": round(sum(msgs), 1),
            }
            filas.append(fila)
            print(f"  {n:>2} nodos: se ven todos en {convergencia:5.2f} s; "
                  f"arranque {fila['arranque_recibidos_por_nodo']:7.0f} msg "
                  f"por nodo; estable {fila['recibidos_por_nodo_s']:5.1f} "
                  f"msg/s ({fila['kb_recibidos_por_nodo_s']:5.1f} KB/s), "
                  f"teoria {fila['teoria_recibidos_por_nodo_s']:.1f}")
    guardar("escalabilidad", {"modo": "loopback", "t_hello": t_hello,
                              "ventana_s": ventana, "filas": filas})
    return filas


# ---------------------------------------------------------------- fallos

def medir_fallos(rapido):
    titulo("5. TOLERANCIA A FALLOS (loopback, umbrales reales 15 s y 30 s)")
    datos = {"modo": "loopback", "t_hello": 5.0, "t_sospecha": 15.0,
             "t_muerte": 30.0}
    repeticiones = 1 if rapido else 3

    # 5a. deteccion de un nodo que se apaga de golpe
    sospecha, inactivo, reingreso = [], [], []
    for r in range(repeticiones):
        with Laboratorio(7000 + r * 20, 7001 + r * 20) as lab:
            nodos = [lab.nodo(f"fal-{j}", t_hello=5.0) for j in range(5)]
            lab.se_ven(nodos)
            time.sleep(1.0 + r * 1.7)
            victima = nodos[-1]
            vivos = nodos[:-1]
            marcas = {"s": [], "i": [], "e": []}
            for v in vivos:
                v.cuando_sospeche(lambda nid, m=marcas: nid == victima.node_id
                                  and m["s"].append(time.perf_counter()))
                v.cuando_salga(lambda nid, m=marcas: nid == victima.node_id
                               and m["i"].append(time.perf_counter()))
                v.cuando_entre(lambda vec, m=marcas: vec.node_id ==
                               victima.node_id and m["e"].append(
                                   time.perf_counter()))
            t0 = time.perf_counter()
            apagar_de_golpe(victima)
            esperar(lambda: len(marcas["i"]) >= len(vivos), 45, 0.2)
            sospecha += [x - t0 for x in marcas["s"]]
            inactivo += [x - t0 for x in marcas["i"]]

            t1 = time.perf_counter()
            vuelta = None
            for puerto in (victima.puerto, lab.siguiente_tcp):
                try:
                    vuelta = Nodo(victima.nombre, interfaz="lo",
                                  difusion=LOCAL, puerto_udp=lab.puerto_udp,
                                  puerto_tcp=puerto, carpeta_logs=None,
                                  carpeta_id=os.path.join(lab.carpeta, "ids"),
                                  carpeta_archivos=os.path.join(lab.carpeta,
                                                                "v"),
                                  t_hello=5.0).iniciar()
                    break
                except OSError:
                    continue
            lab.siguiente_tcp += 1
            lab.nodos.append(vuelta)
            esperar(lambda: len(marcas["e"]) >= len(vivos), 20)
            reingreso += [x - t1 for x in marcas["e"]]
        print(f"  repeticion {r + 1}: sospechoso a "
              f"{statistics.fmean(sospecha[-4:]):.1f} s, inactivo a "
              f"{statistics.fmean(inactivo[-4:]):.1f} s, "
              f"reingreso en {ms(statistics.fmean(reingreso[-4:])):.0f} ms")
    datos["deteccion"] = {"sospechoso_s": resumen(sospecha),
                          "inactivo_s": resumen(inactivo),
                          "reingreso_ms": resumen([ms(x) for x in reingreso]),
                          "crudo": {"sospechoso_s": sospecha,
                                    "inactivo_s": inactivo,
                                    "reingreso_s": reingreso}}

    # 5b. salida ordenada (GOODBYE)
    with Laboratorio(7100, 7101) as lab:
        nodos = [lab.nodo(f"bye-{j}") for j in range(4)]
        lab.se_ven(nodos)
        salidas = []
        victima = nodos[-1]
        for v in nodos[:-1]:
            v.cuando_salga(lambda nid: nid == victima.node_id
                           and salidas.append(time.perf_counter()))
        t0 = time.perf_counter()
        victima.detener(despedirse=True)
        esperar(lambda: len(salidas) >= 3, 5)
        goodbye = [ms(x - t0) for x in salidas]
    datos["goodbye_ms"] = resumen(goodbye)
    print(f"  Salida con GOODBYE: los demas la ven en "
          f"{resumen(goodbye)['mediana']:.1f} ms")

    # 5c. reasignacion de tareas en los tres casos
    datos["reasignacion"] = {
        "nodo_caido": reasignar_por_caida(),
        "tiempo_agotado": reasignar_por_tiempo(),
        "no_entregada": reasignar_no_entregada(),
    }

    # 5d. carga con caidas: 6 ejecutores, se caen 2 a mitad de trabajo
    datos["carga_con_caidas"] = carga_con_caidas(rapido)
    guardar("fallos", datos)
    return datos


def _tres_nodos(lab, lenta, rapida):
    a = lab.nodo("rea-A", t_hello=5.0)
    b = lab.nodo("rea-B", t_hello=5.0,
                 leer_estado=lambda: {"cpu": 0.9, "capacidad": 2})
    c = lab.nodo("rea-C", t_hello=5.0,
                 leer_estado=lambda: {"cpu": 0.1, "capacidad": 2})
    b.registrar_operacion("trabajo", lenta)
    c.registrar_operacion("trabajo", rapida)
    lab.se_ven([a, b, c])
    esperar(lambda: len(a.que_ofrezcan(["trabajo"])) == 2, 10)
    return a, b, c


def reasignar_por_caida():
    soltar = threading.Event()
    with Laboratorio(7150, 7151) as lab:
        a, b, c = _tres_nodos(lab, lambda d: soltar.wait(90) and "B",
                              lambda d: "C")
        t0 = time.perf_counter()
        futuro = a.enviar_tarea_async("trabajo", None, timeout=120)
        time.sleep(1.0)
        apagar_de_golpe(b)
        resultado = futuro.result(timeout=90)
        total = time.perf_counter() - t0
        soltar.set()
    print(f"  Reasignacion por nodo caido: la tarea termino en {total:.1f} s "
          f"(en {resultado}, intentos {futuro.tarea.intentos})")
    return {"segundos": round(total, 2), "termino_en": resultado,
            "intentos": futuro.tarea.intentos}


def reasignar_por_tiempo():
    with Laboratorio(7170, 7171) as lab:
        a, b, c = _tres_nodos(lab, lambda d: time.sleep(10) or "B",
                              lambda d: "C")
        t0 = time.perf_counter()
        resultado = a.enviar_tarea("trabajo", None, timeout=3.0)
        total = time.perf_counter() - t0
    print(f"  Reasignacion por tiempo agotado (limite 3 s): "
          f"{total:.2f} s (en {resultado})")
    return {"limite_s": 3.0, "segundos": round(total, 2),
            "termino_en": resultado}


def reasignar_no_entregada():
    with Laboratorio(7190, 7191) as lab:
        a, b, c = _tres_nodos(lab, lambda d: "B", lambda d: "C")
        b.mensajes.detener()
        t0 = time.perf_counter()
        resultado = a.enviar_tarea("trabajo", None)
        total = time.perf_counter() - t0
    print(f"  Reasignacion por entrega fallida: {ms(total):.0f} ms "
          f"(en {resultado})")
    return {"ms": round(ms(total), 1), "termino_en": resultado}


def carga_con_caidas(rapido):
    cuantas = 24 if rapido else 40
    trabajo = 0.5

    def correr(con_caidas, puerto):
        with Laboratorio(puerto, puerto + 1) as lab:
            a = lab.nodo("caos-A", t_hello=5.0)
            ejecutores = [lab.nodo(f"caos-E{i}", t_hello=5.0)
                          for i in range(6)]
            for e in ejecutores:
                e.registrar_operacion("trabajo",
                                      lambda d: time.sleep(trabajo) or d)
            lab.se_ven([a] + ejecutores)
            esperar(lambda: len(a.que_ofrezcan(["trabajo"])) == 6, 10)
            t0 = time.perf_counter()
            futuros = [a.enviar_tarea_async("trabajo", i, timeout=120)
                       for i in range(cuantas)]
            caidos = []
            if con_caidas:
                time.sleep(1.0)
                carga = {}
                for t in a.tareas.pendientes():
                    carga[t.ejecutor] = carga.get(t.ejecutor, 0) + 1
                ocupados = sorted(ejecutores,
                                  key=lambda e: -carga.get(e.node_id, 0))
                for e in ocupados[:2]:
                    caidos.append(carga.get(e.node_id, 0))
                    apagar_de_golpe(e)
            bien, mal = 0, 0
            for f in futuros:
                try:
                    f.result(timeout=150)
                    bien += 1
                except Exception:
                    mal += 1
            total = time.perf_counter() - t0
            reintentadas = sum(1 for f in futuros if f.tarea.intentos > 1)
            return {"tareas": cuantas, "completadas": bien, "fallidas": mal,
                    "reasignadas": reintentadas,
                    "pendientes_en_los_caidos": caidos,
                    "segundos": round(total, 2)}

    sin = correr(False, 7200)
    con = correr(True, 7250)
    print(f"  {cuantas} tareas con 6 ejecutores, sin caidas: "
          f"{sin['completadas']}/{cuantas} en {sin['segundos']} s")
    print(f"  {cuantas} tareas, se caen al segundo 1 los 2 ejecutores mas "
          f"ocupados (tenian {con['pendientes_en_los_caidos']} tareas): "
          f"{con['completadas']}/{cuantas} en {con['segundos']} s "
          f"({con['reasignadas']} reasignadas)")
    return {"sin_caidas": sin, "con_caidas": con,
            "segundos_por_tarea": trabajo}


# ---------------------------------------------------------------- malla real

def medir_malla(args):
    titulo("MEDICIONES EN LA MALLA REAL")
    if not malla.existe(args.interfaz):
        raise SystemExit(f"no existe {args.interfaz}: monte la malla primero "
                         f"(sudo bash arrancar_nodo.sh N)")
    datos = {"modo": "malla", "red": malla.resumen(args.interfaz),
             "batman": _batman()}
    with Nodo(f"medidor-{platform.node()}", interfaz=args.interfaz,
              puerto_tcp=args.puerto, carpeta_logs=None,
              carpeta_archivos=tempfile.mkdtemp()) as yo:
        print("  esperando a los demas nodos (10 s)...")
        time.sleep(10)
        vecinos = [v for v in yo.descubrimiento.activos()
                   if not v.nombre.startswith("medidor")]
        if not vecinos:
            raise SystemExit("no veo ningun nodo: abra la mensajeria en los "
                             "demas equipos")
        datos["vecinos"] = [v.resumen() for v in vecinos]

        rtt_por_nodo = {}
        respuesta = threading.Event()
        actual = []
        yo.al_recibir(PONG, lambda m, ip: (
            actual.append(time.perf_counter() - m.payload["t0"]),
            respuesta.set()))
        for v in vecinos:
            actual.clear()
            for _ in range(args.repeticiones):
                respuesta.clear()
                yo.enviar_mensaje(v.node_id, {"t0": time.perf_counter()},
                                  tipo=PING)
                respuesta.wait(5)
            valores = [ms(x) for x in actual]
            rtt_por_nodo[v.nombre] = {"ip": v.ip,
                                      "resumen_ms": resumen(valores),
                                      "crudo_ms": valores}
            print(f"  ping a {v.nombre:<20} {v.ip:<14} mediana "
                  f"{resumen(valores).get('mediana', float('nan')):.1f} ms, "
                  f"p95 {resumen(valores).get('p95', float('nan')):.1f} ms, "
                  f"respondio {len(valores)}/{args.repeticiones}")
        datos["ping"] = rtt_por_nodo

        tareas = []
        for i in range(args.repeticiones):
            t0 = time.perf_counter()
            try:
                yo.enviar_tarea("calcular", f"{i} + 1", timeout=10)
                tareas.append(ms(time.perf_counter() - t0))
            except Exception as e:
                print(f"  tarea fallida: {e}")
        datos["tarea_calcular"] = {"resumen_ms": resumen(tareas),
                                   "crudo_ms": tareas}
        print(f"  tarea 'calcular' ida y vuelta: mediana "
              f"{resumen(tareas).get('mediana', float('nan')):.1f} ms")

        destino = vecinos[0]
        filas = []
        for tamano in (100_000, 1_000_000):
            for clase in ("texto", "aleatorio"):
                ruta = os.path.join(tempfile.gettempdir(),
                                    f"medida-{clase}-{tamano}.bin")
                with open(ruta, "wb") as f:
                    f.write(b"temperatura 23.4 humedad 68 presion 1012\n"
                            * (tamano // 41) if clase == "texto"
                            else os.urandom(tamano))
                t0 = time.perf_counter()
                r = yo.enviar_archivo(destino.node_id, ruta, timeout=120)
                s = time.perf_counter() - t0
                filas.append({"tamano": tamano, "clase": clase,
                              "entregado": r["entregado"],
                              "comprimido": r["comprimido"],
                              "bytes_enviados": r["tamano_enviado"],
                              "segundos": round(s, 3),
                              "mb_por_s": round(tamano / 1e6 / s, 3)})
                print(f"  archivo {clase:<9} {tamano / 1e6:.1f} MB a "
                      f"{destino.nombre}: {s:.2f} s "
                      f"({tamano / 1e6 / s:.2f} MB/s"
                      f"{', comprimido' if r['comprimido'] else ''})")
                os.remove(ruta)
        datos["archivos"] = filas
    guardar("malla", datos)


def _batman():
    import subprocess
    try:
        salida = subprocess.run(["batctl", "o"], capture_output=True,
                                text=True, timeout=5).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return salida


# ---------------------------------------------------------------- principal

PARTES = {
    "latencia": medir_latencia,
    "tareas": medir_tareas,
    "archivos": medir_archivos,
    "escalabilidad": medir_escalabilidad,
    "fallos": medir_fallos,
}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("parte", choices=list(PARTES) + ["todo", "malla"])
    p.add_argument("--rapido", action="store_true",
                   help="menos repeticiones y menos nodos")
    p.add_argument("--interfaz", default="bat0", help="solo para 'malla'")
    p.add_argument("--puerto", type=int, default=5010,
                   help="puerto TCP del medidor en 'malla'")
    p.add_argument("--repeticiones", type=int, default=30,
                   help="repeticiones por medida en 'malla'")
    args = p.parse_args()

    inicio = time.monotonic()
    if args.parte == "malla":
        medir_malla(args)
    elif args.parte == "todo":
        for funcion in PARTES.values():
            funcion(args.rapido)
    else:
        PARTES[args.parte](args.rapido)
    print(f"\nlisto en {time.monotonic() - inicio:.0f} s")


if __name__ == "__main__":
    main()
