"""
Demostracion del descubrimiento de nodos.

Levanta un nodo que se anuncia en la malla y muestra la tabla de vecinos
actualizandose sola. No hay que configurarle nada a nadie: se prende y ya.

    python3 examples/demo_descubrimiento.py nodo-01
    python3 examples/demo_descubrimiento.py nodo-01 bat0
    python3 examples/demo_descubrimiento.py nodo-01 lo 127.255.255.255 5001
    python3 examples/demo_descubrimiento.py nodo-01 bat0 - 5001 rescate,medicos

El tercer y cuarto argumento son para probar en un solo equipo, sin malla:
la difusion de loopback y un puerto TCP distinto por nodo ("-" deja la
difusion de bat0). El quinto es la lista de grupos a los que se une.

Los eventos quedan en logs/<nombre>.jsonl. Para resumirlos:

    python3 examples/analizar_logs.py logs

QUE MIRAR
---------
1. Prenda dos o tres nodos. Se encuentran en menos de un segundo, porque al
   HELLO del nodo nuevo los demas responden de una.
2. Apague uno con Ctrl+C: manda GOODBYE y desaparece de la tabla al momento.
3. Apaguelo de golpe (cierre la terminal): a los 15 segundos queda
   SOSPECHOSO y a los 30 INACTIVO. Esto es lo que hay que grabar para el
   video, porque es la evidencia de tolerancia a fallos.
4. Vuelvalo a prender: se reintegra solo.
"""

import sys
import time
import uuid

sys.path.insert(0, ".")

from src.communication import ServicioMensajes, malla
from src.discovery import ServicioDescubrimiento
from src.monitoring import Registro

try:
    import psutil
except ImportError:
    psutil = None

nombre = sys.argv[1] if len(sys.argv) > 1 else "nodo-01"
interfaz = sys.argv[2] if len(sys.argv) > 2 else "bat0"
difusion = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
puerto_tcp = int(sys.argv[4]) if len(sys.argv) > 4 else 5001
grupos = sys.argv[5].split(",") if len(sys.argv) > 5 else []

node_id = uuid.uuid4().hex[:8]


def leer_estado():
    """
    Vector de recursos del nodo, todo entre 0 y 1.

    Esto es lo que despues alimenta la formula de aptitud del planificador.
    El ancho de banda sale del TQ que reporta batman-adv.
    """
    if psutil:
        cpu = 1.0 - psutil.cpu_percent(interval=0.1) / 100.0
        mem = psutil.virtual_memory().available / psutil.virtual_memory().total
    else:
        cpu = mem = 0.5
    return {
        "cpu": round(max(0.0, cpu), 3),
        "memoria": round(mem, 3),
        "ancho_banda": malla.calidad_promedio(),
        "carga": 0.0,
    }


mensajes = ServicioMensajes(node_id, interfaz=interfaz, difusion=difusion,
                            puerto_tcp=puerto_tcp)
descubrimiento = ServicioDescubrimiento(
    mensajes, node_id, nombre,
    leer_estado=leer_estado,
    servicios=["sensor_movimiento"],
)
for g in grupos:
    descubrimiento.unirse(g)

registro = Registro(node_id, nombre)
registro.observar(mensajes, descubrimiento)

descubrimiento.cuando_entre(
    lambda v: print(f"\n  >> entró {v.nombre} en {v.ip}"))
descubrimiento.cuando_sospeche(
    lambda nid: print(f"\n  >> no sé nada de {nid} hace rato: SOSPECHOSO"))
descubrimiento.cuando_salga(
    lambda nid: print(f"\n  >> se fue el nodo {nid}"))


def tabla():
    vecinos = descubrimiento.resumen()
    print(f"\n[{nombre}] conozco {len(vecinos)} nodo(s)")
    if not vecinos:
        print("   (esperando a que aparezca alguien)")
        return
    print(f"   {'nombre':<12}{'estado':<12}{'ip':<16}"
          f"{'cpu':<7}{'mem':<7}{'visto':<8}{'servicios':<20}grupos")
    for v in vecinos:
        e = v["estado"]
        print(f"   {v['nombre']:<12}{v['status']:<12}{v['ip']:<16}"
              f"{e.get('cpu', '-'):<7}{e.get('memoria', '-'):<7}"
              f"{str(v['silencio']) + 's':<8}"
              f"{','.join(v['servicios']):<20}{','.join(v['grupos'])}")


if __name__ == "__main__":
    mensajes.iniciar()
    descubrimiento.iniciar()

    print(f"{nombre} ({node_id}) en {interfaz}")
    print(f"  ip: {mensajes.ip}   difusión: {mensajes.difusion}")
    print(f"  grupos: {', '.join(mensajes.mis_grupos()) or '-'}")
    print(f"  registro: {registro.ruta}")
    if not malla.existe(interfaz):
        print(f"  ojo: la interfaz {interfaz} no existe en este equipo")
    print("\nCtrl+C para salir\n")

    registro.evento("inicio", ip=mensajes.ip, interfaz=interfaz)
    try:
        while True:
            time.sleep(5)
            tabla()
    except KeyboardInterrupt:
        print("\nsaliendo, avisando a los demás...")
        descubrimiento.detener()
        mensajes.detener()
        registro.cerrar(mensajes)
