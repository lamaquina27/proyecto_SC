import json
import os
import threading
import time

from ..discovery import HEARTBEAT, RESOURCE_UPDATE


class Registro:
    def __init__(self, node_id, nombre=None, carpeta="logs"):
        self.node_id = node_id
        self.nombre = nombre or node_id
        self.reloj = None
        os.makedirs(carpeta, exist_ok=True)
        self.ruta = os.path.join(carpeta, f"{self.nombre}.jsonl")
        self._archivo = open(self.ruta, "a", encoding="utf-8")
        self._candado = threading.Lock()
        self._contadores = {}

    def contar(self, nombre, cuanto=1):
        with self._candado:
            self._contadores[nombre] = self._contadores.get(nombre, 0) + cuanto

    def evento(self, tipo, **datos):
        linea = {"t": round(time.time(), 3), "nodo": self.nombre,
                 "node_id": self.node_id, "evento": tipo}
        if self.reloj is not None:
            linea["lamport"] = self.reloj.valor
        linea.update(datos)
        texto = json.dumps(linea, ensure_ascii=False, separators=(",", ":"))
        with self._candado:
            self._contadores[tipo] = self._contadores.get(tipo, 0) + 1
            if self._archivo.closed:
                return
            self._archivo.write(texto + "\n")
            self._archivo.flush()

    def observar(self, mensajes, descubrimiento=None):
        self.reloj = mensajes.reloj
        mensajes.al_recibir(
            HEARTBEAT, lambda m, ip: self.contar("heartbeat_recibidos"))
        mensajes.al_recibir(
            RESOURCE_UPDATE, lambda m, ip: self.contar("recursos_recibidos"))
        mensajes.cuando_falle(
            lambda m, ip, puerto, error: self.evento(
                "fallo_envio", mensaje=m.type, destino=ip, puerto=puerto,
                receiver=m.receiver, grupo=m.group, error=str(error)))
        if descubrimiento is None:
            return

        nombres = {}

        def nombre_de(node_id):
            v = descubrimiento.buscar(node_id)
            return v.nombre if v else nombres.get(node_id, node_id)

        def entro(v):
            nombres[v.node_id] = v.nombre
            self.evento("vecino_entra", vecino=v.nombre, vecino_id=v.node_id,
                        ip=v.ip, servicios=list(v.servicios))

        descubrimiento.cuando_entre(entro)
        descubrimiento.cuando_sospeche(
            lambda nid: self.evento("vecino_sospechoso",
                                    vecino=nombre_de(nid), vecino_id=nid))
        descubrimiento.cuando_salga(
            lambda nid: self.evento("vecino_sale",
                                    vecino=nombre_de(nid), vecino_id=nid))
        descubrimiento.cuando_reporten(
            lambda nid, status, quien: self.evento(
                "reporte_estado", vecino=nombre_de(nid), vecino_id=nid,
                status=status, reporta=nombre_de(quien)))

    def metricas(self):
        with self._candado:
            return dict(self._contadores)

    def volcar(self, mensajes=None):
        datos = {"contadores": self.metricas()}
        if mensajes is not None:
            datos["trafico"] = mensajes.metricas()
        self.evento("metricas", **datos)

    def cerrar(self, mensajes=None):
        self.volcar(mensajes)
        with self._candado:
            self._archivo.close()
