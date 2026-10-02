"""
Resume los registros de los nodos.

    python3 examples/analizar_logs.py logs

Lee todos los logs/*.jsonl (uno por nodo) y muestra:

  1. Cuantos eventos de cada tipo escribio cada nodo.
  2. La linea de tiempo de entradas, sospechas, caidas y fallos de envio,
     juntando los archivos de todos los nodos.
  3. Cuanto tardo cada nodo en pasar de SOSPECHOSO a INACTIVO para cada
     vecino caido. Es la evidencia de los dos umbrales.
     (La linea de tiempo tambien muestra cada tarea: a quien se asigno, con
     que F(i,j), si se reasigno y por que.)
  4. Las ultimas metricas de trafico de cada nodo.

Los HEARTBEAT y RESOURCE_UPDATE no aparecen en la linea de tiempo porque no
se escriben, solo se cuentan: salen en las metricas. Los NODE_STATUS si
aparecen, como reporte_estado.
"""

import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

LINEA_DE_TIEMPO = {"inicio", "vecino_entra", "vecino_sospechoso",
                   "vecino_sale", "reporte_estado", "fallo_envio",
                   "tarea_solicitada", "tarea_asignada", "tarea_recibida",
                   "tarea_reasignada", "tarea_completada", "tarea_fallida"}


def leer(carpeta):
    eventos = []
    for ruta in sorted(glob.glob(os.path.join(carpeta, "*.jsonl"))):
        with open(ruta, encoding="utf-8") as f:
            for n, linea in enumerate(f, start=1):
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    eventos.append(json.loads(linea))
                except ValueError:
                    print(f"  ojo: linea {n} de {ruta} no es JSON")
    return eventos


def hora(t):
    return datetime.fromtimestamp(t).strftime("%H:%M:%S.%f")[:-3]


def describir(e):
    tipo = e["evento"]
    if tipo == "fallo_envio":
        return (f"no pudo enviar {e.get('mensaje')} a {e.get('destino')} "
                f"({e.get('error')})")
    if tipo == "inicio":
        return f"arranca en {e.get('ip')} ({e.get('interfaz')})"
    if tipo == "reporte_estado":
        return (f"oye por NODE_STATUS que {e.get('reporta')} ve a "
                f"{e.get('vecino')} {e.get('status')}")
    if tipo == "tarea_solicitada":
        return (f"tarea {e.get('tarea')}: nadie conocido ofrece "
                f"{e.get('requisitos')}, pregunta con TASK_REQUEST")
    if tipo == "tarea_asignada":
        aptitud = e.get("aptitud")
        f = f"F={aptitud}" if aptitud is not None else "local"
        return (f"tarea {e.get('tarea')} ({e.get('operacion')}) -> "
                f"{e.get('ejecutor')}  [{f}, intento {e.get('intento')}]")
    if tipo == "tarea_recibida":
        return (f"ejecuta tarea {e.get('tarea')} ({e.get('operacion')}) "
                f"de {e.get('solicitante')}")
    if tipo == "tarea_reasignada":
        return (f"REASIGNA tarea {e.get('tarea')}: {e.get('motivo')} "
                f"(estaba en {e.get('desde')})")
    if tipo == "tarea_completada":
        return (f"tarea {e.get('tarea')} lista, la hizo {e.get('ejecutor')} "
                f"en {e.get('intentos')} intento(s)")
    if tipo == "tarea_fallida":
        return f"tarea {e.get('tarea')} FALLIDA: {e.get('error')}"
    verbo = {"vecino_entra": "ve entrar a",
             "vecino_sospechoso": "sospecha de",
             "vecino_sale": "da por caido a"}[tipo]
    return f"{verbo} {e.get('vecino')}"


def main():
    carpeta = sys.argv[1] if len(sys.argv) > 1 else "logs"
    eventos = leer(carpeta)
    if not eventos:
        print(f"no hay registros en {carpeta}/")
        return

    print("== eventos por nodo ==")
    por_nodo = defaultdict(Counter)
    for e in eventos:
        por_nodo[e["nodo"]][e["evento"]] += 1
    for nodo, cuenta in sorted(por_nodo.items()):
        detalle = ", ".join(f"{k}={v}" for k, v in sorted(cuenta.items()))
        print(f"  {nodo:<12} {detalle}")

    print("\n== linea de tiempo ==")
    for e in sorted(eventos, key=lambda e: e["t"]):
        if e["evento"] in LINEA_DE_TIEMPO:
            print(f"  {hora(e['t'])}  {e['nodo']:<12} {describir(e)}")

    print("\n== deteccion de caidas (sospecha -> inactivo) ==")
    sospecha = {}
    hubo = False
    for e in sorted(eventos, key=lambda e: e["t"]):
        clave = (e["nodo"], e.get("vecino_id"))
        if e["evento"] == "vecino_sospechoso":
            sospecha[clave] = e["t"]
        elif e["evento"] == "vecino_sale" and clave in sospecha:
            hubo = True
            print(f"  {e['nodo']:<12} sobre {e.get('vecino'):<12} "
                  f"{e['t'] - sospecha.pop(clave):.1f} s")
    if not hubo:
        print("  ninguna caida completa registrada")

    print("\n== ultimas metricas ==")
    ultimas = {}
    for e in eventos:
        if e["evento"] == "metricas":
            ultimas[e["nodo"]] = e
    if not ultimas:
        print("  ningun nodo cerro su registro (se escriben al salir)")
    for nodo, e in sorted(ultimas.items()):
        print(f"  {nodo}")
        for k, v in sorted((e.get("trafico") or {}).items()):
            print(f"      {k:<18} {v}")
        contadores = e.get("contadores", {})
        print(f"      {'heartbeat_recib.':<18} "
              f"{contadores.get('heartbeat_recibidos', 0)}")
        print(f"      {'resource_upd_recib.':<18} "
              f"{contadores.get('recursos_recibidos', 0)}")


if __name__ == "__main__":
    main()
