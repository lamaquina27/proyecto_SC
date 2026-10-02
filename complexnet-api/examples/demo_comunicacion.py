"""
Demostracion de la capa de comunicacion.

Levanta un nodo que se anuncia en la malla, aprende las direcciones de los
demas y permite mandarles mensajes directos o a todos.

    python3 examples/demo_comunicacion.py nodo-01
    python3 examples/demo_comunicacion.py nodo-01 bat0            # malla real
    python3 examples/demo_comunicacion.py nodo-01 lo 127.255.255.255 5001

Los ultimos dos argumentos son para probar en un solo equipo: la interfaz
de loopback, su direccion de difusion y un puerto TCP distinto por nodo.

Comandos dentro del programa:

    lista                  ver los nodos conocidos y sus direcciones
    todos <texto>          mandar un mensaje a toda la malla (UDP)
    msg <nodo> <texto>     mandar un mensaje directo (TCP)
    unir <grupo>           entrar a un grupo
    dejar <grupo>          salir de un grupo
    grupo <grupo> <texto>  mandar un mensaje solo a los del grupo (UDP)
    ping <nodo>            medir el tiempo de ida y vuelta
    red                    ver el estado de bat0 y los vecinos directos
    stats                  ver los contadores de trafico
    salir
"""

import sys
import threading
import time
import uuid

sys.path.insert(0, ".")

from src.communication import (ANUNCIO, APP_MSG, PING, PONG, ServicioMensajes,
                               malla)
from src.discovery import Directorio

nombre = sys.argv[1] if len(sys.argv) > 1 else "nodo-01"
interfaz = sys.argv[2] if len(sys.argv) > 2 else "bat0"
difusion = sys.argv[3] if len(sys.argv) > 3 else None
puerto_tcp = int(sys.argv[4]) if len(sys.argv) > 4 else 5001

node_id = uuid.uuid4().hex[:8]
directorio = Directorio()
mensajes = ServicioMensajes(node_id, interfaz=interfaz, difusion=difusion,
                            puerto_tcp=puerto_tcp)

# Guarda los PING que salieron, para calcular el tiempo de vuelta
pendientes = {}


# ------------------------------------------------- que hacer con cada tipo

def al_llegar_anuncio(m, ip_origen):
    p = m.payload
    # La IP la tomamos de donde llego el paquete, no de lo que diga el
    # mensaje: asi funciona aunque el otro nodo se equivoque al reportarla.
    nuevo = directorio.registrar(m.sender, p.get("nombre", m.sender),
                                 ip_origen, p.get("puerto_tcp", 5001))
    if nuevo:
        print(f"\n  >> apareció {p.get('nombre')} en {ip_origen}")


def al_llegar_mensaje(m, ip_origen):
    c = directorio.buscar(m.sender)
    quien = c.nombre if c else m.sender
    if m.group:
        via = f"grupo {m.group}"
    else:
        via = "directo" if m.receiver else "a todos"
    print(f"\n  >> {quien} ({via}): {m.payload.get('texto')}")


def al_llegar_ping(m, ip_origen):
    c = directorio.buscar(m.sender)
    if c:
        mensajes.enviar(c.ip, c.puerto_tcp, PONG, m.sender,
                        {"t0": m.payload.get("t0")})


def al_llegar_pong(m, ip_origen):
    t0 = m.payload.get("t0")
    if t0:
        ida_y_vuelta = (time.time() - t0) * 1000
        c = directorio.buscar(m.sender)
        quien = c.nombre if c else m.sender
        print(f"\n  >> respuesta de {quien}: {ida_y_vuelta:.1f} ms")


mensajes.al_recibir(ANUNCIO, al_llegar_anuncio)
mensajes.al_recibir(APP_MSG, al_llegar_mensaje)
mensajes.al_recibir(PING, al_llegar_ping)
mensajes.al_recibir(PONG, al_llegar_pong)


# ------------------------------------------------- anunciarse cada 5 s

def anunciarse():
    while True:
        mensajes.difundir(ANUNCIO, {"nombre": nombre,
                                    "puerto_tcp": mensajes.puerto_tcp})
        time.sleep(5)


# ------------------------------------------------- consola

def resolver(texto):
    """Acepta el nombre del nodo o su identificador."""
    return directorio.por_nombre(texto) or directorio.buscar(texto)


def consola():
    while True:
        try:
            linea = input().strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not linea:
            continue
        partes = linea.split(" ", 2)
        orden = partes[0].lower()

        if orden == "salir":
            break

        elif orden == "lista":
            contactos = directorio.todos()
            if not contactos:
                print("  todavía no conozco a nadie")
            for c in contactos:
                print(f"  {c['nombre']:<12} {c['ip']:<16} "
                      f"visto hace {c['hace']} s")

        elif orden == "todos" and len(partes) > 1:
            mensajes.difundir(APP_MSG, {"texto": linea.split(" ", 1)[1]})
            print("  enviado a toda la malla")

        elif orden == "msg" and len(partes) > 2:
            c = resolver(partes[1])
            if c is None:
                print(f"  no conozco a {partes[1]}")
            else:
                mensajes.enviar(c.ip, c.puerto_tcp, APP_MSG, c.node_id,
                                {"texto": partes[2]})
                print(f"  enviado a {c.nombre}")

        elif orden == "unir" and len(partes) > 1:
            mensajes.unirse(partes[1])
            print(f"  ahora estoy en: {', '.join(mensajes.mis_grupos())}")

        elif orden == "dejar" and len(partes) > 1:
            mensajes.abandonar(partes[1])
            print(f"  ahora estoy en: {', '.join(mensajes.mis_grupos()) or '-'}")

        elif orden == "grupo" and len(partes) > 2:
            mensajes.multidifundir(partes[1], APP_MSG, {"texto": partes[2]})
            print(f"  enviado al grupo {partes[1]}")

        elif orden == "ping" and len(partes) > 1:
            c = resolver(partes[1])
            if c is None:
                print(f"  no conozco a {partes[1]}")
            else:
                mensajes.enviar(c.ip, c.puerto_tcp, PING, c.node_id,
                                {"t0": time.time()})

        elif orden == "red":
            for clave, valor in malla.resumen(interfaz).items():
                print(f"  {clave}: {valor}")

        elif orden == "stats":
            for clave, valor in mensajes.metricas().items():
                print(f"  {clave}: {valor}")

        else:
            print("  comandos: lista | todos <texto> | msg <nodo> <texto> | "
                  "unir <grupo> | dejar <grupo> | grupo <grupo> <texto> | "
                  "ping <nodo> | red | stats | salir")


if __name__ == "__main__":
    mensajes.iniciar()
    threading.Thread(target=anunciarse, daemon=True).start()

    print(f"{nombre} ({node_id}) escuchando en {interfaz}")
    print(f"  ip: {mensajes.ip}   difusión: {mensajes.difusion}")
    print(f"  puertos: UDP {mensajes.puerto_udp} · TCP {mensajes.puerto_tcp}")
    print(f"  maximo por UDP: {mensajes.max_udp} bytes (MTU {mensajes.mtu})")
    if not malla.existe(interfaz):
        print(f"  ojo: la interfaz {interfaz} no existe en este equipo")
    print("\nescriba un comando (o 'salir')\n")

    try:
        consola()
    finally:
        mensajes.detener()
        print("nodo detenido")
