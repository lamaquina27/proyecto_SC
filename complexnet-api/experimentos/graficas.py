"""
Graficas de los experimentos, a partir de experimentos/resultados/*.json.

    python experimentos/graficas.py

Necesita matplotlib (pip install matplotlib). Solo hace falta en el
computador donde se arma el informe, no en los nodos.
Las imagenes quedan en experimentos/graficas/.
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

AQUI = os.path.dirname(os.path.abspath(__file__))
RESULTADOS = os.path.join(AQUI, "resultados")
SALIDA = os.path.join(AQUI, "graficas")

AZUL = "#1f5f74"
NARANJA = "#d2581a"
GRIS = "#8a9aa3"

plt.rcParams.update({
    "figure.figsize": (7, 4.2), "figure.dpi": 130, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.3,
})


def cargar(nombre):
    ruta = os.path.join(RESULTADOS, f"{nombre}.json")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def guardar(fig, nombre):
    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, f"{nombre}.png")
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)
    print(f"  {os.path.relpath(ruta)}")


def grafica_latencia(d):
    tcp = d["tcp_por_tamano"]
    tamanos = sorted(int(t) for t in tcp)
    medianas = [tcp[str(t)]["resumen_ms"]["mediana"] for t in tamanos]
    p95 = [tcp[str(t)]["resumen_ms"]["p95"] for t in tamanos]
    fig, ax = plt.subplots()
    ax.plot(tamanos, medianas, "o-", color=AZUL, label="mediana")
    ax.plot(tamanos, p95, "s--", color=NARANJA, label="percentil 95")
    udp = d["udp_difusion"]["resumen_ms"]["mediana"]
    ax.axhline(udp, color=GRIS, linestyle=":",
               label=f"difusión UDP (mediana {udp:.2f} ms)")
    ax.set_xscale("log")
    ax.set_xlabel("tamaño del mensaje (bytes)")
    ax.set_ylabel("latencia de un sentido (ms)")
    ax.set_title("Latencia de un mensaje según su tamaño")
    ax.legend()
    guardar(fig, "latencia_por_tamano")

    fig, ax = plt.subplots()
    for nombre, valores, color in (
            ("difusión UDP", d["udp_difusion"]["crudo_ms"], GRIS),
            ("TCP 100 B", tcp["100"]["crudo_ms"], AZUL),
            ("ping TCP (ida y vuelta)", d["ping_ida_y_vuelta"]["crudo_ms"],
             NARANJA)):
        orden = sorted(valores)
        n = len(orden)
        ax.step(orden, [(i + 1) / n for i in range(n)], where="post",
                color=color, label=nombre)
    ax.set_xlabel("latencia (ms)")
    ax.set_ylabel("fracción de mensajes")
    ax.set_title("Distribución de la latencia (CDF)")
    ax.legend()
    guardar(fig, "latencia_cdf")


def grafica_tareas(d):
    corridas = d["reparto"]["corridas"]
    k = [c["ejecutores"] for c in corridas]
    fig, ax = plt.subplots()
    ax.plot(k, [c["aceleracion"] for c in corridas], "o-", color=AZUL,
            label="medida")
    ax.plot(k, k, "--", color=GRIS, label="ideal (lineal)")
    for c in corridas:
        ax.annotate(f"{c['segundos']:.1f} s", (c["ejecutores"],
                                              c["aceleracion"]),
                    textcoords="offset points", xytext=(6, -12), fontsize=8)
    ax.set_xlabel("nodos que ejecutan")
    ax.set_ylabel("aceleración (veces más rápido que con 1)")
    ax.set_title(f"{d['reparto']['tareas']} tareas de "
                 f"{d['reparto']['segundos_por_tarea']} s repartidas")
    ax.set_xticks(k)
    ax.legend()
    guardar(fig, "tareas_aceleracion")


def grafica_archivos(filas):
    grupos = [(f["clase"], f["tamano"]) for f in filas
              if f["compresion"] == "auto"]
    etiquetas = [f"{c}\n{t / 1e6:g} MB" for c, t in grupos]
    auto = [next(f["mb_por_s"] for f in filas if (f["clase"], f["tamano"])
                 == g and f["compresion"] == "auto") for g in grupos]
    sin = [next(f["mb_por_s"] for f in filas if (f["clase"], f["tamano"])
                == g and f["compresion"] == "no") for g in grupos]
    x = range(len(grupos))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar([i - 0.2 for i in x], sin, 0.4, color=GRIS, label="sin compresión")
    ax.bar([i + 0.2 for i in x], auto, 0.4, color=AZUL,
           label="compresión automática")
    ax.set_xticks(list(x))
    ax.set_xticklabels(etiquetas)
    ax.set_ylabel("velocidad efectiva (MB/s)")
    ax.set_title("Envío de archivos: velocidad con y sin compresión")
    ax.legend()
    guardar(fig, "archivos_velocidad")


def grafica_escalabilidad(d):
    filas = d["filas"]
    n = [f["nodos"] for f in filas]
    fig, ax = plt.subplots()
    ax.plot(n, [f["recibidos_por_nodo_s"] for f in filas], "o-", color=AZUL,
            label="medido")
    ax.plot(n, [f["teoria_recibidos_por_nodo_s"] for f in filas], "--",
            color=GRIS, label="teoría: 2(N−1)/t_hello")
    ax.set_xlabel("nodos en la red (N)")
    ax.set_ylabel("mensajes recibidos por nodo por segundo")
    ax.set_title("Tráfico de mantenimiento por nodo")
    ax.legend()
    guardar(fig, "escalabilidad_trafico")

    if "arranque_recibidos_por_nodo" in filas[0]:
        fig, ax = plt.subplots()
        ax.plot(n, [f["arranque_recibidos_por_nodo"] for f in filas], "o-",
                color=NARANJA, label="medido")
        ax.plot(n, [f["teoria_arranque_por_nodo"] for f in filas], "--",
                color=GRIS, label="teoría: 3(N−1) + 6(N−1)²")
        ax.set_xlabel("nodos que arrancan a la vez (N)")
        ax.set_ylabel("mensajes recibidos por nodo")
        ax.set_title("Ráfaga de arranque (HELLO y respuestas)")
        ax.legend()
        guardar(fig, "escalabilidad_arranque")

    fig, ax = plt.subplots()
    ax.plot(n, [f["convergencia_s"] for f in filas], "o-", color=NARANJA)
    ax.set_xlabel("nodos en la red (N)")
    ax.set_ylabel("segundos hasta que todos ven a todos")
    ax.set_title("Tiempo de descubrimiento")
    ax.set_ylim(bottom=0)
    guardar(fig, "escalabilidad_convergencia")


def grafica_fallos(d):
    det = d["deteccion"]["crudo"]
    fig, ax = plt.subplots()
    cajas = ax.boxplot([det["sospechoso_s"], det["inactivo_s"]],
                       patch_artist=True, widths=0.5)
    for caja, color in zip(cajas["boxes"], (NARANJA, AZUL)):
        caja.set_facecolor(color)
        caja.set_alpha(0.5)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["pasa a SOSPECHOSO", "pasa a INACTIVO"])
    ax.axhline(d["t_sospecha"], color=NARANJA, linestyle=":",
               label=f"umbral {d['t_sospecha']:g} s")
    ax.axhline(d["t_muerte"], color=AZUL, linestyle=":",
               label=f"umbral {d['t_muerte']:g} s")
    ax.set_ylabel("segundos desde que el nodo se apagó")
    ax.set_title("Detección de un nodo que se apaga de golpe")
    ax.legend()
    guardar(fig, "fallos_deteccion")

    caos = d["carga_con_caidas"]
    fig, ax = plt.subplots()
    nombres = ["sin caídas", "2 de 6 nodos\nse caen"]
    valores = [caos["sin_caidas"]["segundos"], caos["con_caidas"]["segundos"]]
    barras = ax.bar(nombres, valores, color=[AZUL, NARANJA], width=0.5)
    for b, datos in zip(barras, (caos["sin_caidas"], caos["con_caidas"])):
        ax.annotate(f"{datos['completadas']}/{datos['tareas']} completas",
                    (b.get_x() + b.get_width() / 2, b.get_height()),
                    textcoords="offset points", xytext=(0, 4), ha="center",
                    fontsize=9)
    ax.set_ylabel("segundos para terminar todas las tareas")
    ax.set_title("Tareas con caídas de nodos")
    guardar(fig, "fallos_carga")


def main():
    print("graficas:")
    for nombre, funcion in (("latencia", grafica_latencia),
                            ("tareas", grafica_tareas),
                            ("escalabilidad", grafica_escalabilidad),
                            ("fallos", grafica_fallos)):
        d = cargar(nombre)
        if d:
            funcion(d)
    d = cargar("archivos")
    if d:
        grafica_archivos(d["filas"])


if __name__ == "__main__":
    main()
