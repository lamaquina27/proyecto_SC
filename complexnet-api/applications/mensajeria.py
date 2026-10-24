"""
Aplicacion 1 de ComplexNet API: mensajeria entre nodos de la malla.

Esta escrita solo con la capa 4 (src.api.Nodo): no toca sockets ni
servicios por dentro. Es el ejemplo de lo que promete el documento del
corte 1: "el que use nuestra API no deberia tener que saber que es un
socket".

En una Raspberry Pi con la malla montada (sudo ./setup_adhoc.sh N):

    python3 applications/mensajeria.py

En un solo computador, sin malla, para probar (abra varias terminales):

    python3 applications/mensajeria.py --local

Opciones:

    --nombre NOMBRE      nombre del nodo (por defecto, el del equipo)
    --local              usar loopback en lugar de bat0
    --interfaz IF        interfaz de la malla (por defecto bat0)
    --puerto N           puerto TCP (en --local se busca uno libre solo)
    --grupos a,b         grupos a los que se une al arrancar
    --logs CARPETA       donde guardar el registro (por defecto logs)
    --archivos CARPETA   donde quedan los archivos recibidos
                         (por defecto recibidos)

Comandos dentro del programa:

    lista                  nodos conocidos, su estado y sus grupos
    recursos               el estado (cpu, memoria, ...) de cada nodo
    todos <texto>          mensaje a toda la malla
    msg <nodo> <texto>     mensaje directo a un nodo
    grupo <grupo> <texto>  mensaje solo a los de un grupo
    unir <grupo>           entrar a un grupo
    dejar <grupo>          salir de un grupo
    ping <nodo>            tiempo de ida y vuelta
    archivo <nodo> <ruta>  envia un archivo; el otro nodo lo guarda en su
                           carpeta de recibidos y avisa al llegar
    calc <expresion>       operacion matematica como tarea distribuida
                           (tambien: operacion <expresion>). La ejecuta el
                           nodo con mayor F(i,j); si se cae, se reasigna.
                           Ej: calc (10 + 20) * 2^3, calc sqrt(2) * pi
    estres <seg> [partes] [mb]
                           reparte 'partes' tareas que ocupan un nucleo
                           entero durante 'seg' segundos (y reservan 'mb'
                           de memoria) para ver su costo en el monitor
    yo                     el estado de este nodo
    red                    estado de bat0 y vecinos de batman-adv
    stats                  contadores de trafico
    ayuda
    salir                  (o Ctrl+C) se despide de los demas y sale

Se puede correr desde cualquier carpeta; el registro queda en ./logs y el
identificador del nodo en ~/.complexnet/<nombre>.id.
"""

import argparse
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from src.api import Nodo
from src.communication import APP_MSG, PING, PONG, malla

from operaciones import ExpresionInvalida, calcular, estresar

DIFUSION_LOCAL = "127.255.255.255"
PUERTO_TCP = 5001
SERVICIOS = ["mensajeria"]

AYUDA = """  comandos:
    lista | recursos | yo      quien esta y como esta
    todos <texto>              mensaje a toda la malla
    msg <nodo> <texto>         mensaje directo
    grupo <grupo> <texto>      mensaje a un grupo
    unir <grupo> | dejar <grupo>
    archivo <nodo> <ruta>      enviar un archivo
    calc <expresion>           operacion matematica: la ejecuta el mejor nodo
    estres <seg> [partes] [mb] carga de CPU repartida en la red
    ping <nodo> | red | stats | salir"""


def leer_argumentos():
    p = argparse.ArgumentParser(
        description="Mensajeria de ComplexNet API sobre la malla.")
    p.add_argument("--nombre")
    p.add_argument("--local", action="store_true",
                   help="probar en un solo equipo, sin malla")
    p.add_argument("--interfaz", default="bat0")
    p.add_argument("--puerto", type=int)
    p.add_argument("--grupos", default="")
    p.add_argument("--logs", default="logs")
    p.add_argument("--archivos", default="recibidos")
    return p.parse_args()


def tamano_legible(n):
    if n < 1024:
        return f"{n} B"
    for unidad in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unidad == "GB":
            return f"{n:.1f} {unidad}"


class Mensajeria:
    def __init__(self, args):
        self.nombres = {}
        self.nodo = self.arrancar(args)

    def configurar(self, nodo):
        nodo.registrar_operacion("calcular", calcular)
        nodo.registrar_operacion("estresar", estresar)
        nodo.al_recibir(APP_MSG, self.al_llegar_mensaje)
        nodo.al_recibir(PING, self.al_llegar_ping)
        nodo.al_recibir(PONG, self.al_llegar_pong)
        nodo.cuando_llegue_archivo(self.al_llegar_archivo)
        nodo.cuando_entre(self.al_entrar)
        nodo.cuando_sospeche(
            lambda nid: self.avisar(f"{self.nombre_de(nid)} no responde "
                                    f"hace rato: SOSPECHOSO"))
        nodo.cuando_salga(
            lambda nid: self.avisar(f"{self.nombre_de(nid)} salio de la red"))

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

        base = socket.gethostname()
        primero = args.puerto or PUERTO_TCP
        intentos = 50 if args.local and not args.puerto else 1
        error = None
        for puerto in range(primero, primero + intentos):
            nombre = args.nombre or (f"{base}-{puerto}" if args.local
                                     else base)
            nodo = Nodo(nombre, interfaz=interfaz, difusion=difusion,
                        puerto_tcp=puerto, servicios=SERVICIOS,
                        carpeta_logs=args.logs,
                        carpeta_archivos=args.archivos)
            for g in filter(None, args.grupos.split(",")):
                nodo.unirse_a_grupo(g.strip())
            self.nodo = nodo
            self.configurar(nodo)
            try:
                return nodo.iniciar()
            except OSError as e:
                error = e
        raise SystemExit(f"{error}\n  Si hay otro nodo en este equipo, use "
                         f"otro --puerto (o --local para buscar uno libre)")

    @staticmethod
    def avisar(texto):
        print(f"\n  >> {texto}", flush=True)

    def al_entrar(self, v):
        self.nombres[v.node_id] = v.nombre
        self.avisar(f"entro {v.nombre} ({v.ip})")

    def nombre_de(self, node_id):
        v = self.nodo.buscar(node_id)
        return v.nombre if v else self.nombres.get(node_id, node_id)

    def al_llegar_mensaje(self, m, ip_origen):
        if m.group:
            via = f"grupo {m.group}"
        elif m.receiver:
            via = "directo"
        else:
            via = "a todos"
        self.avisar(f"{self.nombre_de(m.sender)} ({via}): "
                    f"{m.payload.get('texto')}")

    def al_llegar_ping(self, m, ip_origen):
        if self.nodo.buscar(m.sender):
            self.nodo.enviar_mensaje(m.sender, {"t0": m.payload.get("t0")},
                                     tipo=PONG)

    def al_llegar_pong(self, m, ip_origen):
        t0 = m.payload.get("t0")
        if t0:
            ms = (time.time() - t0) * 1000
            self.avisar(f"respuesta de {self.nombre_de(m.sender)}: "
                        f"{ms:.1f} ms")

    def al_llegar_archivo(self, info):
        self.avisar(f"{self.nombre_de(info['de'])} te envio el archivo "
                    f"{info['nombre']} ({tamano_legible(info['tamano'])}), "
                    f"guardado en {info['ruta']}")

    @staticmethod
    def en_segundo_plano(funcion, *args):
        threading.Thread(target=funcion, args=args, daemon=True).start()

    def mandar_directo(self, destino, datos, tipo, aviso_ok):
        if not self.nodo.enviar_mensaje(destino, datos, tipo=tipo,
                                        timeout=3.0):
            self.avisar(f"no se pudo entregar a {self.nombre_de(destino)}")
        elif aviso_ok:
            print(f"  {aviso_ok}", flush=True)

    def informar_envio(self, r, a_quien):
        if r["via"] == "udp":
            print(f"  enviado {a_quien}", flush=True)
            return
        if not r["entregados"] and not r["fallidos"]:
            self.avisar(f"no conozco a nadie activo para enviar {a_quien}")
            return
        nombres = [self.nombre_de(n) for n in r["entregados"]]
        print(f"  enviado por TCP a: {', '.join(nombres) or '-'}", flush=True)
        if r["fallidos"]:
            self.avisar("no se pudo entregar a: " + ", ".join(
                self.nombre_de(n) for n in r["fallidos"]))

    def mandar_a_todos(self, texto):
        self.informar_envio(self.nodo.difundir({"texto": texto}),
                            "a toda la malla")

    def mandar_a_grupo(self, grupo, texto):
        self.informar_envio(self.nodo.enviar_a_grupo(grupo, {"texto": texto}),
                            f"al grupo {grupo}")

    def pedir_calculo(self, expresion):
        futuro = self.nodo.enviar_tarea_async("calcular", expresion,
                                              timeout=10.0)
        try:
            resultado = futuro.result()
        except Exception as e:
            self.avisar(f"{expresion}: fallo ({e})")
            return
        t = futuro.tarea
        donde = [self.nombre_de(n) for n in t.historial]
        if isinstance(resultado, float):
            resultado = f"{resultado:.10g}"
        self.avisar(f"{expresion} = {resultado}  "
                    f"(la ejecuto {self.nombre_de(t.ejecutor)}; "
                    f"intentos: {' -> '.join(donde)})")

    def pedir_estres(self, segundos, partes, mb):
        inicio = time.monotonic()
        futuros = [self.nodo.enviar_tarea_async(
            "estresar", {"segundos": segundos, "mb": mb,
                         "desde": 10_000_000 * (i + 1)},
            timeout=segundos * (partes + 1) + 15)
            for i in range(partes)]
        por_nodo = {}
        fallidas = 0
        for i, futuro in enumerate(futuros, 1):
            try:
                r = futuro.result()
            except Exception as e:
                fallidas += 1
                self.avisar(f"estres: la parte {i}/{partes} fallo ({e})")
                continue
            quien = self.nombre_de(futuro.tarea.ejecutor)
            print(f"  estres: parte {i}/{partes} lista en {quien} "
                  f"({r['revisados']:,} numeros, {r['primos']:,} primos, "
                  f"{r['segundos']:.1f} s)", flush=True)
            cuenta = por_nodo.setdefault(quien, [0, 0])
            cuenta[0] += 1
            cuenta[1] += r["revisados"]
        total = time.monotonic() - inicio
        reparto = ", ".join(f"{n}: {p} parte{'s' if p > 1 else ''}"
                            for n, (p, _) in sorted(por_nodo.items()))
        revisados = sum(r for _, r in por_nodo.values())
        self.avisar(f"estres terminado en {total:.1f} s: {revisados:,} "
                    f"numeros revisados. Reparto: {reparto or '-'}"
                    + (f". Fallaron {fallidas}" if fallidas else ""))

    def mandar_archivo(self, v, ruta):
        avisados = set()

        def avance(i, total):
            cuarto = i * 4 // total
            if 0 < cuarto < 4 and cuarto not in avisados:
                avisados.add(cuarto)
                print(f"  {os.path.basename(ruta)}: {cuarto * 25}%",
                      flush=True)

        r = self.nodo.enviar_archivo(v.node_id, ruta, al_avanzar=avance)
        if r["entregado"]:
            self.avisar(f"{r['nombre']} llego completo a {v.nombre} "
                        f"({tamano_legible(r['tamano'])} en "
                        f"{r['segundos']:.1f} s)")
        else:
            self.avisar(f"{r['nombre']} no llego a {v.nombre}: {r['error']}")

    def lista(self):
        vecinos = self.nodo.consultar_estado_red(incluir_caidos=True)
        if not vecinos:
            print("  todavia no conozco a nadie")
            return
        print(f"  {'nombre':<20}{'estado':<12}{'ip':<16}"
              f"{'visto':<8}grupos")
        for v in vecinos:
            print(f"  {v['nombre']:<20}{v['status']:<12}{v['ip']:<16}"
                  f"{str(v['silencio']) + 's':<8}"
                  f"{','.join(v['grupos']) or '-'}")

    def recursos(self):
        recursos = self.nodo.consultar_recursos()
        if not recursos:
            print("  todavia no conozco el estado de nadie")
            return
        for node_id, estado in recursos.items():
            detalle = "  ".join(f"{k}={v}" for k, v in estado.items()) or "-"
            print(f"  {self.nombre_de(node_id):<20}{detalle}")

    def yo(self):
        for clave, valor in self.nodo.obtener_estado().items():
            if clave != "trafico":
                print(f"  {clave}: {valor}")

    def destino(self, texto):
        v = self.nodo.buscar(texto)
        if v is None:
            print(f"  no conozco a {texto} (use 'lista')")
            return None
        if v.status != "ACTIVO":
            print(f"  ojo: {v.nombre} esta {v.status}, se intenta igual")
        return v

    def ejecutar(self, linea):
        partes = linea.split(" ", 2)
        orden = partes[0].lower()

        if orden == "lista":
            self.lista()
        elif orden == "recursos":
            self.recursos()
        elif orden == "yo":
            self.yo()
        elif orden == "todos" and len(partes) > 1:
            self.en_segundo_plano(self.mandar_a_todos,
                                  linea.split(" ", 1)[1])
        elif orden == "msg" and len(partes) > 2:
            v = self.destino(partes[1])
            if v:
                self.en_segundo_plano(self.mandar_directo, v.node_id,
                                      {"texto": partes[2]}, APP_MSG,
                                      f"entregado a {v.nombre}")
        elif orden == "grupo" and len(partes) > 2:
            self.en_segundo_plano(self.mandar_a_grupo, partes[1], partes[2])
        elif orden == "unir" and len(partes) > 1:
            self.nodo.unirse_a_grupo(partes[1])
            print(f"  mis grupos: {', '.join(self.nodo.mensajes.mis_grupos())}")
        elif orden == "dejar" and len(partes) > 1:
            self.nodo.salir_de_grupo(partes[1])
            print(f"  mis grupos: "
                  f"{', '.join(self.nodo.mensajes.mis_grupos()) or '-'}")
        elif orden == "ping" and len(partes) > 1:
            v = self.destino(partes[1])
            if v:
                self.en_segundo_plano(self.mandar_directo, v.node_id,
                                      {"t0": time.time()}, PING, None)
        elif orden == "archivo" and len(partes) > 2:
            ruta = os.path.expanduser(partes[2].strip().strip("\"'"))
            if not os.path.isfile(ruta):
                print(f"  no encuentro el archivo {ruta}")
                return
            v = self.destino(partes[1])
            if v:
                print(f"  enviando {os.path.basename(ruta)} "
                      f"({tamano_legible(os.path.getsize(ruta))}) "
                      f"a {v.nombre}...", flush=True)
                self.en_segundo_plano(self.mandar_archivo, v, ruta)
        elif orden in ("calc", "operacion") and len(partes) > 1:
            expresion = linea.split(" ", 1)[1].strip()
            try:
                calcular(expresion)
            except ExpresionInvalida as e:
                print(f"  {e}")
                print("  ej: calc (10 + 20) * 2^3   calc sqrt(2) * pi")
                return
            except (ArithmeticError, ValueError, TypeError):
                pass
            print("  operacion enviada a la red...")
            self.en_segundo_plano(self.pedir_calculo, expresion)
        elif orden == "estres":
            self.ejecutar_estres(linea.split()[1:])
        elif orden == "red":
            for clave, valor in malla.resumen(self.nodo.interfaz).items():
                print(f"  {clave}: {valor}")
        elif orden == "stats":
            for clave, valor in self.nodo.mensajes.metricas().items():
                print(f"  {clave}: {valor}")
        else:
            print(AYUDA)

    def ejecutar_estres(self, valores):
        try:
            segundos = float(valores[0]) if valores else 10.0
            ofrecen = len(self.nodo.que_ofrezcan(["estresar"]))
            partes = int(valores[1]) if len(valores) > 1 else max(1, ofrecen)
            mb = int(valores[2]) if len(valores) > 2 else 0
        except ValueError:
            print("  uso: estres <segundos> [partes] [mb]   "
                  "ej: estres 15 4 200")
            return
        if not (1 <= segundos <= 120 and 1 <= partes <= 32
                and 0 <= mb <= 1024):
            print("  limites: 1-120 segundos, 1-32 partes, 0-1024 mb")
            return
        print(f"  estres: {partes} parte(s) de {segundos:g} s"
              + (f" y {mb} MB" if mb else "")
              + f" para {ofrecen} nodo(s) que la ofrecen. Mire el monitor.",
              flush=True)
        self.en_segundo_plano(self.pedir_estres, segundos, partes, mb)

    def presentar(self):
        e = self.nodo.obtener_estado()
        m = self.nodo.mensajes
        print(f"{e['nombre']} ({e['node_id']}) en {self.nodo.interfaz}")
        print(f"  ip: {e['ip']}   difusion: {m.difusion}")
        print(f"  puertos: UDP {m.puerto_udp} | TCP {e['puerto']}")
        print(f"  grupos: {', '.join(e['grupos']) or '-'}")
        if self.nodo.registro:
            print(f"  registro: {self.nodo.registro.ruta}")
        print("\nescriba 'ayuda' para ver los comandos\n", flush=True)

    def consola(self):
        while True:
            try:
                linea = input().strip()
            except (EOFError, KeyboardInterrupt):
                return
            if linea.lower() == "salir":
                return
            if linea:
                self.ejecutar(linea)


def main():
    app = Mensajeria(leer_argumentos())
    app.presentar()
    try:
        app.consola()
    finally:
        print("\nsaliendo, avisando a los demas...")
        app.nodo.detener()


if __name__ == "__main__":
    main()
