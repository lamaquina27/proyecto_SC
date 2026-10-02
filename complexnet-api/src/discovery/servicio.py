import threading
import time

from ..communication import (GOODBYE, HEARTBEAT, HELLO, HELLO_ACK,
                             NODE_STATUS, RESOURCE_UPDATE, MensajeMuyGrande)
from .vecino import ACTIVO, INACTIVO, SOSPECHOSO, Vecino

TIPOS = (HELLO, HELLO_ACK, HEARTBEAT, RESOURCE_UPDATE, NODE_STATUS, GOODBYE)


class ServicioDescubrimiento:
    def __init__(self, mensajes, node_id, nombre,
                 leer_estado=None, servicios=None,
                 t_hello=5.0, t_sospecha=15.0, t_muerte=30.0,
                 t_recursos=None):
        self.mensajes = mensajes
        self.node_id = node_id
        self.nombre = nombre
        self.leer_estado = leer_estado or (lambda: {})
        self.servicios = list(servicios or [])

        self.t_hello = t_hello
        self.t_sospecha = t_sospecha
        self.t_muerte = t_muerte
        self.t_recursos = t_recursos or t_hello

        self.vecinos = {}
        self.candado = threading.Lock()

        self._corriendo = False
        self._hilos = []
        self._al_entrar = []
        self._al_sospechar = []
        self._al_salir = []
        self._al_reportar = []
        self._avisos_dados = set()

        for tipo in TIPOS:
            self.mensajes.al_recibir(tipo, self._recibir)

    def cuando_entre(self, funcion):
        self._al_entrar.append(funcion)

    def cuando_sospeche(self, funcion):
        self._al_sospechar.append(funcion)

    def cuando_salga(self, funcion):
        self._al_salir.append(funcion)

    def cuando_reporten(self, funcion):
        self._al_reportar.append(funcion)

    def _avisar(self, lista, *args):
        for funcion in list(lista):
            try:
                funcion(*args)
            except Exception as e:
                print(f"[{self.nombre}] error avisando: {e}")

    def _avisar_una_vez(self, clave, texto):
        if clave not in self._avisos_dados:
            self._avisos_dados.add(clave)
            print(f"[{self.nombre}] {texto}")

    def _payload_minimo(self):
        return {"nombre": self.nombre,
                "puerto_tcp": self.mensajes.puerto_tcp}

    def _payload_presencia(self):
        p = self._payload_minimo()
        p["servicios"] = self.servicios
        p["grupos"] = self.mensajes.mis_grupos()
        return p

    def _difundir_presencia(self, tipo):
        for payload in (self._payload_presencia(), self._payload_minimo()):
            try:
                return self.mensajes.difundir(tipo, payload)
            except MensajeMuyGrande:
                self._avisar_una_vez(
                    "presencia", f"el {tipo} no cabe en un datagrama, "
                                 f"se manda sin servicios ni grupos")
        return None

    def anunciarse(self):
        self._difundir_presencia(HEARTBEAT)
        return self.publicar_recursos()

    def publicar_recursos(self):
        try:
            estado = self.leer_estado()
        except Exception as e:
            self._avisar_una_vez("leer_estado",
                                 f"no se pudo leer el estado: {e}")
            return None
        payload = self._payload_minimo()
        payload["estado"] = estado
        try:
            return self.mensajes.difundir(RESOURCE_UPDATE, payload)
        except MensajeMuyGrande:
            self._avisar_una_vez(
                "recursos", "el RESOURCE_UPDATE no cabe en un datagrama, "
                            "los demas no van a ver el estado de este nodo")
            return None

    def _anunciar_estado(self, node_id, nombre, nuevo, anterior):
        try:
            self.mensajes.difundir(NODE_STATUS, {
                "node_id": node_id, "nombre": nombre,
                "status": nuevo, "anterior": anterior})
        except MensajeMuyGrande:
            pass

    def publicar_servicio(self, nombre):
        if nombre not in self.servicios:
            self.servicios.append(nombre)

    def unirse(self, grupo):
        self.mensajes.unirse(grupo)

    def abandonar(self, grupo):
        self.mensajes.abandonar(grupo)

    def _recibir(self, m, ip_origen):
        if not self._corriendo:
            return
        if m.type == GOODBYE:
            self._retirar(m.sender)
            return
        if m.type == NODE_STATUS:
            self._recibir_reporte(m)
            return

        entro, anterior = self._registrar(m, ip_origen)

        if m.type == HELLO:
            self._difundir_presencia(HELLO_ACK)
            self.publicar_recursos()

        if anterior in (SOSPECHOSO, INACTIVO):
            v = self.buscar(m.sender)
            if v:
                self._anunciar_estado(v.node_id, v.nombre, ACTIVO, anterior)
        if entro:
            self._avisar(self._al_entrar, entro)

    def _recibir_reporte(self, m):
        p = m.payload or {}
        objetivo = p.get("node_id")
        status = p.get("status")
        if not objetivo or not status:
            return
        if objetivo == self.node_id:
            if status != ACTIVO:
                self._difundir_presencia(HEARTBEAT)
            return
        self._avisar(self._al_reportar, objetivo, status, m.sender)

    def _registrar(self, m, ip_origen):
        p = m.payload or {}
        entro = None
        anterior = None

        with self.candado:
            v = self.vecinos.get(m.sender)

            if v is None:
                v = Vecino(m.sender, p.get("nombre", m.sender), ip_origen,
                           p.get("puerto_tcp", 5001), p.get("servicios"),
                           p.get("grupos"))
                self.vecinos[m.sender] = v
                entro = v
            else:
                anterior = v.status
                if v.status == INACTIVO:
                    entro = v

                if m.seq < v.ultimo_seq:
                    v.estado = {}
                    v.servicios = []
                    v.grupos = []

                v.ip = ip_origen
                v.nombre = p.get("nombre", v.nombre)
                v.puerto_tcp = p.get("puerto_tcp", v.puerto_tcp)

            if p.get("servicios") is not None:
                v.servicios = p["servicios"]
            if p.get("grupos") is not None:
                v.grupos = p["grupos"]
            if p.get("estado"):
                v.estado = p["estado"]

            v.ultimo_seq = m.seq
            v.visto = time.monotonic()
            v.status = ACTIVO

        return entro, anterior

    def _retirar(self, node_id):
        with self.candado:
            salio = self.vecinos.pop(node_id, None)
        if salio and salio.status != INACTIVO:
            self._avisar(self._al_salir, node_id)

    def _ciclo_latido(self):
        proximos_recursos = 0.0
        while self._corriendo:
            try:
                self._difundir_presencia(HEARTBEAT)
                ahora = time.monotonic()
                if ahora >= proximos_recursos:
                    self.publicar_recursos()
                    proximos_recursos = ahora + self.t_recursos
            except Exception as e:
                print(f"[{self.nombre}] fallo el latido: {e}")
            time.sleep(self.t_hello)

    def _ciclo_vigilancia(self):
        while self._corriendo:
            cambios = []
            with self.candado:
                for node_id, v in list(self.vecinos.items()):
                    silencio = v.silencio()
                    if silencio > self.t_muerte:
                        if v.status != INACTIVO:
                            cambios.append((v.node_id, v.nombre,
                                            INACTIVO, v.status))
                            v.status = INACTIVO
                    elif silencio > self.t_sospecha:
                        if v.status == ACTIVO:
                            cambios.append((v.node_id, v.nombre,
                                            SOSPECHOSO, v.status))
                            v.status = SOSPECHOSO
            for node_id, nombre, nuevo, anterior in cambios:
                self._anunciar_estado(node_id, nombre, nuevo, anterior)
                if nuevo == SOSPECHOSO:
                    self._avisar(self._al_sospechar, node_id)
                else:
                    self._avisar(self._al_salir, node_id)
            time.sleep(1.0)

    def iniciar(self):
        self._corriendo = True

        def saludar():
            for _ in range(3):
                if not self._corriendo:
                    return
                self._difundir_presencia(HELLO)
                time.sleep(0.5)

        threading.Thread(target=saludar, daemon=True).start()

        for destino in (self._ciclo_latido, self._ciclo_vigilancia):
            h = threading.Thread(target=destino, daemon=True)
            h.start()
            self._hilos.append(h)
        return self

    def detener(self, despedirse=True):
        if despedirse:
            try:
                self.mensajes.difundir(GOODBYE, {"nombre": self.nombre})
            except Exception:
                pass
        self._corriendo = False
        for h in self._hilos:
            h.join(timeout=2.0)
        self._hilos = []

    def activos(self):
        with self.candado:
            return [v for v in self.vecinos.values() if v.status == ACTIVO]

    def todos(self):
        with self.candado:
            return list(self.vecinos.values())

    def buscar(self, node_id):
        with self.candado:
            return self.vecinos.get(node_id)

    def por_nombre(self, nombre):
        with self.candado:
            for v in self.vecinos.values():
                if v.nombre == nombre:
                    return v
        return None

    def que_ofrezcan(self, servicios):
        with self.candado:
            return [v for v in self.vecinos.values()
                    if v.status == ACTIVO and v.ofrece(servicios)]

    def miembros(self, grupo):
        with self.candado:
            return [v for v in self.vecinos.values()
                    if v.status == ACTIVO and v.esta_en(grupo)]

    def enviar_a_grupo(self, grupo, tipo, payload=None):
        try:
            m = self.mensajes.multidifundir(grupo, tipo, payload)
            return {"via": "udp", "mensaje": m}
        except MensajeMuyGrande:
            pass
        destinos = [(v.node_id, v.ip, v.puerto_tcp)
                    for v in self.miembros(grupo)]
        resultado = self.mensajes.enviar_a_varios(destinos, tipo, payload,
                                                  grupo=grupo)
        resultado["via"] = "tcp"
        return resultado

    def resumen(self):
        with self.candado:
            return [v.resumen() for v in self.vecinos.values()]
