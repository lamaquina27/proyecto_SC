import socket

from ..communication import (APP_MSG, MensajeMuyGrande, ServicioArchivos,
                             ServicioMensajes)
from ..discovery import ACTIVO, ServicioDescubrimiento, Vecino
from ..monitoring import Registro
from ..resources import GestorRecursos
from ..scheduler import PlanificadorDistribuido
from ..tasks import GestorTareas
from .identidad import identidad


class Nodo:
    def __init__(self, nombre=None, interfaz="bat0", difusion=None,
                 puerto_udp=5000, puerto_tcp=5001, servicios=None,
                 leer_estado=None, carpeta_logs="logs", carpeta_id=None,
                 node_id=None, t_hello=5.0, t_sospecha=15.0, t_muerte=30.0,
                 max_tareas=2, pesos=None, carpeta_archivos="recibidos"):
        self.nombre = nombre or socket.gethostname()
        self.node_id = node_id or identidad(self.nombre, carpeta_id)
        self.interfaz = interfaz
        self.carpeta_logs = carpeta_logs

        self.recursos = GestorRecursos(max_tareas=max_tareas)
        self.leer_estado = leer_estado or self.recursos.medir
        self.planificador = PlanificadorDistribuido(pesos)

        self.mensajes = ServicioMensajes(self.node_id, interfaz=interfaz,
                                         puerto_udp=puerto_udp,
                                         puerto_tcp=puerto_tcp,
                                         difusion=difusion)
        self.descubrimiento = ServicioDescubrimiento(
            self.mensajes, self.node_id, self.nombre,
            leer_estado=self.leer_estado, servicios=servicios,
            t_hello=t_hello, t_sospecha=t_sospecha, t_muerte=t_muerte)
        self.tareas = GestorTareas(self.mensajes, self.descubrimiento,
                                   self.recursos, self.planificador)
        self.archivos = ServicioArchivos(self.mensajes,
                                         carpeta=carpeta_archivos)
        self.registro = None
        self.activo = False

    @property
    def ip(self):
        return self.mensajes.ip

    @property
    def puerto(self):
        return self.mensajes.puerto_tcp

    def iniciar(self):
        self.mensajes.iniciar()
        if self.carpeta_logs:
            self.registro = Registro(self.node_id, self.nombre,
                                     carpeta=self.carpeta_logs)
            self.registro.observar(self.mensajes, self.descubrimiento)
            self.registro.evento("inicio", ip=self.ip,
                                 interfaz=self.interfaz)
            self.tareas.registro = self.registro
            self.archivos.registro = self.registro
        self.tareas.iniciar()
        self.descubrimiento.iniciar()
        self.activo = True
        return self

    def detener(self, despedirse=True):
        if not self.activo:
            return
        self.activo = False
        self.tareas.detener()
        self.descubrimiento.detener(despedirse)
        self.mensajes.detener()
        if self.registro:
            self.registro.cerrar(self.mensajes)

    def __enter__(self):
        return self.iniciar()

    def __exit__(self, *args):
        self.detener()

    def obtener_estado(self):
        return {
            "node_id": self.node_id,
            "nombre": self.nombre,
            "ip": self.ip,
            "puerto": self.puerto,
            "activo": self.activo,
            "servicios": list(self.descubrimiento.servicios),
            "grupos": self.mensajes.mis_grupos(),
            "recursos": self.leer_estado(),
            "trafico": self.mensajes.metricas(),
        }

    def consultar_estado_red(self, incluir_caidos=False):
        vecinos = self.descubrimiento.resumen()
        if incluir_caidos:
            return vecinos
        return [v for v in vecinos if v["status"] == ACTIVO]

    def consultar_recursos(self, destino=None):
        if destino is not None:
            v = self.buscar(destino)
            return dict(v.estado) if v else None
        return {v.node_id: dict(v.estado)
                for v in self.descubrimiento.activos()}

    def buscar(self, destino):
        if isinstance(destino, Vecino):
            return destino
        return (self.descubrimiento.buscar(destino)
                or self.descubrimiento.por_nombre(destino))

    def enviar_mensaje(self, destino, datos, tipo=APP_MSG, **opciones):
        v = self.buscar(destino)
        if v is None:
            raise LookupError(f"no conozco al nodo {destino}")
        return self.mensajes.enviar(v.ip, v.puerto_tcp, tipo, v.node_id,
                                    datos, **opciones) is not None

    def difundir(self, datos, tipo=APP_MSG):
        try:
            return {"via": "udp", "mensaje": self.mensajes.difundir(tipo, datos)}
        except MensajeMuyGrande:
            pass
        destinos = [(v.node_id, v.ip, v.puerto_tcp)
                    for v in self.descubrimiento.activos()]
        resultado = self.mensajes.enviar_a_varios(destinos, tipo, datos)
        resultado["via"] = "tcp"
        return resultado

    def enviar_a_grupo(self, grupo, datos, tipo=APP_MSG):
        return self.descubrimiento.enviar_a_grupo(grupo, tipo, datos)

    def unirse_a_grupo(self, grupo):
        self.descubrimiento.unirse(grupo)

    def salir_de_grupo(self, grupo):
        self.descubrimiento.abandonar(grupo)

    def publicar_servicio(self, nombre):
        self.descubrimiento.publicar_servicio(nombre)

    def que_ofrezcan(self, servicios):
        return self.descubrimiento.que_ofrezcan(servicios)

    def registrar_operacion(self, nombre, funcion):
        self.tareas.registrar_operacion(nombre, funcion)

    def enviar_tarea(self, operacion, datos=None, **opciones):
        return self.tareas.enviar(operacion, datos, **opciones)

    def enviar_tarea_async(self, operacion, datos=None, **opciones):
        return self.tareas.enviar_async(operacion, datos, **opciones)

    def enviar_archivo(self, destino, ruta, nombre=None, **opciones):
        v = self.buscar(destino)
        if v is None:
            raise LookupError(f"no conozco al nodo {destino}")
        return self.archivos.enviar(v.ip, v.puerto_tcp, v.node_id, ruta,
                                    nombre, **opciones)

    def cuando_llegue_archivo(self, funcion):
        self.archivos.cuando_llegue(funcion)

    def al_recibir(self, tipo, funcion):
        self.mensajes.al_recibir(tipo, funcion)

    def cuando_entre(self, funcion):
        self.descubrimiento.cuando_entre(funcion)

    def cuando_sospeche(self, funcion):
        self.descubrimiento.cuando_sospeche(funcion)

    def cuando_salga(self, funcion):
        self.descubrimiento.cuando_salga(funcion)

    def cuando_reporten(self, funcion):
        self.descubrimiento.cuando_reporten(funcion)

    def cuando_falle(self, funcion):
        self.mensajes.cuando_falle(funcion)
