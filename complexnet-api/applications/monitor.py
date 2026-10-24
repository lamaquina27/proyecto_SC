"""
Monitor de ComplexNet API: los recursos y las tareas de cada nodo, en vivo.

Se une a la red como un nodo mas, pero no ofrece ninguna operacion, asi que
nunca recibe tareas: solo escucha los RESOURCE_UPDATE que todos difunden y
redibuja la pantalla. Se abre en su propia terminal, al lado de la
mensajeria.

En una Raspberry Pi con la malla montada:

    python3 applications/monitor.py

En un solo computador, sin malla, junto a varias mensajerias --local:

    python3 applications/monitor.py --local

Opciones:

    --nombre NOMBRE      nombre del monitor (por defecto monitor-<equipo>)
    --local              usar loopback en lugar de bat0
    --interfaz IF        interfaz de la malla (por defecto bat0)
    --puerto N           puerto TCP (por defecto 5009; se busca uno libre)
    --cada S             segundos entre redibujos (por defecto 1)
    --logs CARPETA       guardar el registro del monitor (por defecto no)
    --sin-color          sin colores ANSI

Ctrl+C para salir.
"""

import argparse
import os
import socket
import sys
import threading
import time
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from src.api import Nodo
from src.communication import RESOURCE_UPDATE, malla

DIFUSION_LOCAL = "127.255.255.255"
PUERTO_TCP = 5009
SERVICIO = "monitor"
CAMBIOS = 10

VERDE, AMARILLO, ROJO, GRIS, NEGRITA, NORMAL = (
    "\033[32m", "\033[33m", "\033[31m", "\033[90m", "\033[1m", "\033[0m")
COLOR_ESTADO = {"ACTIVO": VERDE, "SOSPECHOSO": AMARILLO, "INACTIVO": ROJO}


def leer_argumentos():
    p = argparse.ArgumentParser(
        description="Monitor en vivo de los nodos de ComplexNet API.")
    p.add_argument("--nombre")
    p.add_argument("--local", action="store_true",
                   help="probar en un solo equipo, sin malla")
    p.add_argument("--interfaz", default="bat0")
    p.add_argument("--puerto", type=int)
    p.add_argument("--cada", type=float, default=1.0)
    p.add_argument("--logs")
    p.add_argument("--sin-color", action="store_true")
    return p.parse_args()


def porcentaje(valor):
    if valor is None:
        return "-"
    return f"{float(valor) * 100:.0f}%"


def decimal(valor):
    if valor is None:
        return "-"
    return f"{float(valor):.2f}"


def barra(ocupadas, capacidad):
    capacidad = max(1, int(capacidad or 1))
    llenas = min(capacidad, max(0, ocupadas))
    return "[" + "#" * llenas + "-" * (capacidad - llenas) + "]"


class Monitor:
    def __init__(self, args):
        self.cada = args.cada
        self.color = not args.sin_color
        self.cambios = deque(maxlen=CAMBIOS)
        self.tareas_vistas = {}
        self.nombres = {}
        self._candado = threading.Lock()
        self.nodo = self.arrancar(args)

    def pintar(self, texto, color):
        return f"{color}{texto}{NORMAL}" if self.color else texto

    def arrancar(self, args):
        if args.local:
            interfaz, difusion = "lo", DIFUSION_LOCAL
        else:
            interfaz, difusion = args.interfaz, None
            if not malla.existe(interfaz):
                raise SystemExit(
                    f"la interfaz {interfaz} no existe en este equipo.\n"
                    f"  En una Raspberry Pi: monte la malla con "
                    f"sudo ./setup_adhoc.sh N\n"
                    f"  Para probar sin malla: agregue --local")

        nombre = args.nombre or f"monitor-{socket.gethostname()}"
        primero = args.puerto or PUERTO_TCP
        intentos = 1 if args.puerto else 50
        error = None
        for puerto in range(primero, primero + intentos):
            nodo = Nodo(nombre, interfaz=interfaz, difusion=difusion,
                        puerto_tcp=puerto, servicios=[SERVICIO],
                        carpeta_logs=args.logs)
            nodo.al_recibir(RESOURCE_UPDATE, self.al_llegar_recursos)
            nodo.cuando_entre(self.al_entrar)
            nodo.cuando_sospeche(
                lambda nid: self.anotar(f"{self.nombre_de(nid)} no responde: "
                                        f"SOSPECHOSO", AMARILLO))
            nodo.cuando_salga(self.al_salir)
            self.nodo = nodo
            try:
                return nodo.iniciar()
            except OSError as e:
                error = e
        raise SystemExit(f"{error}\n  Use otro --puerto")

    def nombre_de(self, node_id):
        v = self.nodo.buscar(node_id)
        return v.nombre if v else self.nombres.get(node_id, node_id)

    def anotar(self, texto, color=None):
        hora = time.strftime("%H:%M:%S")
        with self._candado:
            self.cambios.appendleft((hora, texto, color))

    @staticmethod
    def es_monitor(v):
        return SERVICIO in (v.get("servicios") or [])

    def al_entrar(self, v):
        self.nombres[v.node_id] = v.nombre
        if SERVICIO not in v.servicios:
            self.anotar(f"entro {v.nombre} ({v.ip})", VERDE)

    def al_salir(self, node_id):
        nombre = self.nombre_de(node_id)
        with self._candado:
            perdidas = self.tareas_vistas.pop(node_id, {})
        self.anotar(f"{nombre} salio de la red", ROJO)
        for operacion, de in perdidas.values():
            self.anotar(f"{nombre} no termino {operacion} (de {de}); "
                        f"la recuperacion la reasigna", ROJO)

    def al_llegar_recursos(self, m, ip_origen):
        p = m.payload or {}
        nombre = p.get("nombre") or self.nombre_de(m.sender)
        self.nombres[m.sender] = nombre
        actuales = {}
        for t in (p.get("estado") or {}).get("tareas") or []:
            if isinstance(t, list) and len(t) >= 3:
                actuales[t[0]] = (t[1], t[2])
        with self._candado:
            antes = self.tareas_vistas.get(m.sender, {})
            self.tareas_vistas[m.sender] = actuales
        for tarea_id, (operacion, de) in actuales.items():
            if tarea_id not in antes:
                self.anotar(f"{nombre} recibio {operacion} (de {de})")
        for tarea_id, (operacion, de) in antes.items():
            if tarea_id not in actuales:
                self.anotar(f"{nombre} termino {operacion} (de {de})", VERDE)

    def aptitud(self, node_id):
        v = self.nodo.buscar(node_id)
        if v is None or not v.estado:
            return None
        return self.nodo.planificador.calcular_aptitud(v)

    def dibujar(self):
        vecinos = [v for v in self.nodo.consultar_estado_red(
            incluir_caidos=True) if not self.es_monitor(v)]
        cuantos = {"ACTIVO": 0, "SOSPECHOSO": 0, "INACTIVO": 0}
        for v in vecinos:
            cuantos[v["status"]] = cuantos.get(v["status"], 0) + 1
        corriendo = en_cola = 0
        filas_tareas = []
        for v in vecinos:
            for t in v["estado"].get("tareas") or []:
                if not isinstance(t, list) or len(t) < 5:
                    continue
                _, operacion, de, estado, segundos = t[:5]
                if estado == "corriendo":
                    corriendo += 1
                else:
                    en_cola += 1
                filas_tareas.append((v["nombre"], operacion, de, estado,
                                     segundos))

        lineas = []
        lineas.append(self.pintar("ComplexNet - monitor de la red", NEGRITA)
                      + f"   desde {self.nodo.nombre} ({self.nodo.ip})"
                      + f"   {time.strftime('%H:%M:%S')}")
        lineas.append(f"{cuantos['ACTIVO']} activos, "
                      f"{cuantos['SOSPECHOSO']} sospechosos, "
                      f"{cuantos['INACTIVO']} caidos   |   tareas: "
                      f"{corriendo} corriendo, {en_cola} en cola")
        lineas.append("")
        lineas.append(self.pintar(
            f"{'nodo':<16}{'estado':<12}{'cpu':>5}{'mem':>6}{'bw':>6}"
            f"{'R':>6}{'A':>6}  {'carga':<14}{'F':>6}{'hechas':>8}"
            f"{'fallas':>8}{'visto':>7}", NEGRITA))

        if not vecinos:
            lineas.append(self.pintar("  todavia no conozco a nadie "
                                      "(llegan con el primer HELLO)", GRIS))
        for v in sorted(vecinos, key=lambda v: v["nombre"]):
            e = v["estado"]
            capacidad = e.get("capacidad") or 1
            ocupadas = round(float(e.get("carga") or 0) * capacidad)
            carga = f"{barra(ocupadas, capacidad)} {ocupadas}/{capacidad}"
            if e.get("en_cola"):
                carga += f" +{e['en_cola']}"
            f = self.aptitud(v["node_id"])
            estado = self.pintar(f"{v['status']:<12}",
                                 COLOR_ESTADO.get(v["status"], ""))
            lineas.append(
                f"{v['nombre'][:15]:<16}{estado}"
                f"{porcentaje(e.get('cpu')):>5}"
                f"{porcentaje(e.get('memoria')):>6}"
                f"{porcentaje(e.get('ancho_banda')):>6}"
                f"{decimal(e.get('confiabilidad')):>6}"
                f"{decimal(e.get('disponibilidad')):>6}  "
                f"{carga:<14}{decimal(f):>6}"
                f"{e.get('hechas', '-'):>8}{e.get('fallidas', '-'):>8}"
                f"{str(v['silencio']) + 's':>7}")
        lineas.append(self.pintar(
            "  cpu y mem: % libre | bw: calidad del enlace (TQ/255) | "
            "R: confiabilidad | A: disponibilidad | carga: corriendo/"
            "capacidad +en cola | F: aptitud vista desde este monitor",
            GRIS))

        lineas.append("")
        lineas.append(self.pintar("tareas en curso", NEGRITA))
        if not filas_tareas:
            lineas.append(self.pintar("  ninguna", GRIS))
        for nombre, operacion, de, estado, segundos in filas_tareas:
            color = VERDE if estado == "corriendo" else AMARILLO
            lineas.append(f"  {nombre[:15]:<16}{str(operacion)[:18]:<20}"
                          f"de {str(de)[:15]:<16}"
                          f"{self.pintar(f'{estado:<11}', color)}"
                          f"{segundos}s")

        lineas.append("")
        lineas.append(self.pintar("ultimos cambios", NEGRITA))
        with self._candado:
            cambios = list(self.cambios)
        if not cambios:
            lineas.append(self.pintar("  ninguno todavia", GRIS))
        for hora, texto, color in cambios:
            lineas.append(f"  {self.pintar(hora, GRIS)}  "
                          + (self.pintar(texto, color) if color else texto))
        lineas.append("")
        lineas.append(self.pintar("Ctrl+C para salir", GRIS))
        return "\n".join(lineas)

    def correr(self):
        if os.name == "nt":
            os.system("")
        while True:
            pantalla = self.dibujar()
            sys.stdout.write("\033[H\033[J" + pantalla + "\n")
            sys.stdout.flush()
            time.sleep(self.cada)


def main():
    monitor = Monitor(leer_argumentos())
    try:
        monitor.correr()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.nodo.detener()
        print("\nmonitor detenido")


if __name__ == "__main__":
    main()
