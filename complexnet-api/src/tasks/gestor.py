import json
import queue
import threading
import time
from concurrent.futures import Future

from ..communication import (MensajeMuyGrande, TASK_ASSIGN, TASK_REQUEST,
                             TASK_RESULT)
from .recuperacion import GestorRecuperacion
from .tarea import ASIGNADA, Tarea, TareaFallida

DESCONOCIDA = "desconocida"
ERROR = "error"
ESPERA_CANDIDATOS = 1.0


class GestorTareas:
    def __init__(self, mensajes, descubrimiento, recursos, planificador,
                 registro=None, espera_candidatos=ESPERA_CANDIDATOS,
                 ejecutar_local=True):
        self.mensajes = mensajes
        self.descubrimiento = descubrimiento
        self.recursos = recursos
        self.planificador = planificador
        self.registro = registro
        self.espera_candidatos = espera_candidatos
        self.ejecutar_local = ejecutar_local
        self.node_id = mensajes.node_id

        self._operaciones = {}
        self._pendientes = {}
        self._cola = queue.Queue()
        self._trabajadores = []
        self._corriendo = False
        self._candado = threading.Lock()
        self._eleccion = threading.Lock()
        self.recuperacion = GestorRecuperacion(self)

        mensajes.al_recibir(TASK_REQUEST, self._al_recibir_solicitud)
        mensajes.al_recibir(TASK_ASSIGN, self._al_recibir_asignacion)
        mensajes.al_recibir(TASK_RESULT, self._al_recibir_resultado)

    def _evento(self, tipo, **datos):
        if self.registro is not None:
            self.registro.evento(tipo, **datos)

    def _nombre(self, node_id):
        if node_id == self.node_id:
            return self.descubrimiento.nombre
        v = self.descubrimiento.buscar(node_id)
        return v.nombre if v else node_id

    def registrar_operacion(self, nombre, funcion):
        self._operaciones[nombre] = funcion
        self.descubrimiento.publicar_servicio(nombre)

    def sabe_hacer(self, requisitos):
        return all(r in self.descubrimiento.servicios for r in requisitos)

    def crear_tarea(self, operacion, datos=None, requisitos=None, prioridad=0,
                    timeout=30.0, intentos=3):
        return Tarea(operacion, datos, requisitos, prioridad, timeout,
                     intentos)

    def enviar_async(self, operacion, datos=None, requisitos=None,
                     prioridad=0, timeout=30.0, intentos=3):
        tarea = self.crear_tarea(operacion, datos, requisitos, prioridad,
                                 timeout, intentos)
        futuro = Future()
        futuro.tarea = tarea
        with self._candado:
            self._pendientes[tarea.tarea_id] = (tarea, futuro)
            tarea.asignando = True
        self._evento("tarea_creada", tarea=tarea.tarea_id,
                     operacion=operacion)
        threading.Thread(target=self._asignar_en_hilo, args=(tarea,),
                         daemon=True).start()
        return futuro

    def enviar(self, operacion, datos=None, **opciones):
        return self.enviar_async(operacion, datos, **opciones).result()

    def _asignar_en_hilo(self, tarea):
        try:
            self.asignar_tarea(tarea)
        except Exception as e:
            self._terminar(tarea, error=f"error interno asignando: {e}")
        finally:
            tarea.asignando = False

    def asignar_tarea(self, tarea):
        while self._sigue_pendiente(tarea):
            if tarea.intentos >= tarea.max_intentos:
                self._terminar(tarea, error=f"se agotaron los "
                                            f"{tarea.max_intentos} intentos")
                return
            vecino, aptitud = self._elegir(tarea)
            if vecino is None:
                self._sin_candidatos(tarea)
                return

            self._evento("tarea_asignada", tarea=tarea.tarea_id,
                         operacion=tarea.operacion, ejecutor=vecino.nombre,
                         ejecutor_id=vecino.node_id,
                         aptitud=round(aptitud, 3), intento=tarea.intentos)
            entregada = self.mensajes.enviar(
                vecino.ip, vecino.puerto_tcp, TASK_ASSIGN, vecino.node_id,
                tarea.payload(self.mensajes.puerto_tcp),
                timeout=3.0, reintentos=1)
            if entregada is not None:
                return

            self._soltar(tarea)
            self.planificador.registrar_fallo(vecino.node_id)
            tarea.excluidos.add(vecino.node_id)
            self._evento("tarea_reasignada", tarea=tarea.tarea_id,
                         motivo="no_entregada", desde=vecino.nombre)

    def _sigue_pendiente(self, tarea):
        with self._candado:
            return tarea.tarea_id in self._pendientes

    def _reservar(self, tarea):
        with self._eleccion:
            vecino, aptitud = self.planificador.seleccionar_nodo(
                self.descubrimiento.que_ofrezcan(tarea.requisitos),
                excluir=tarea.excluidos)
            if vecino is not None:
                tarea.asignar(vecino.node_id)
                tarea.contado = vecino.node_id
                self.planificador.sumar_pendiente(vecino.node_id)
        return vecino, aptitud

    def _elegir(self, tarea):
        vecino, aptitud = self._reservar(tarea)
        if vecino is not None or tarea.pregunto:
            return vecino, aptitud

        tarea.pregunto = True
        try:
            self.mensajes.difundir(TASK_REQUEST, {
                "tarea_id": tarea.tarea_id,
                "requisitos": tarea.requisitos})
            self._evento("tarea_solicitada", tarea=tarea.tarea_id,
                         requisitos=tarea.requisitos)
        except MensajeMuyGrande:
            pass
        time.sleep(self.espera_candidatos)
        return self._reservar(tarea)

    def _sin_candidatos(self, tarea):
        funcion = self._operaciones.get(tarea.operacion)
        if (self.ejecutar_local and funcion is not None
                and self.sabe_hacer(tarea.requisitos)):
            tarea.asignar(self.node_id)
            self._evento("tarea_asignada", tarea=tarea.tarea_id,
                         operacion=tarea.operacion,
                         ejecutor=self.descubrimiento.nombre,
                         ejecutor_id=self.node_id, aptitud=None,
                         intento=tarea.intentos, local=True)
            self._encolar(tarea.tarea_id, funcion, tarea.datos,
                          lambda r: self._resolver(tarea.tarea_id,
                                                   self.node_id, r))
            return
        requisitos = ", ".join(tarea.requisitos)
        self._terminar(tarea, error=f"ningun nodo activo ofrece {requisitos}")

    def _soltar(self, tarea):
        if tarea.contado is not None:
            self.planificador.sumar_pendiente(tarea.contado, -1)
            tarea.contado = None

    def reasignar_tarea(self, tarea, motivo, culpable=None):
        with self._candado:
            if tarea.tarea_id not in self._pendientes or tarea.asignando:
                return False
            tarea.asignando = True
        self._soltar(tarea)
        if culpable is not None:
            tarea.excluidos.add(culpable)
        self._evento("tarea_reasignada", tarea=tarea.tarea_id, motivo=motivo,
                     desde=self._nombre(culpable) if culpable else None)
        threading.Thread(target=self._asignar_en_hilo, args=(tarea,),
                         daemon=True).start()
        return True

    def tareas_en(self, node_id):
        with self._candado:
            return [t for t, _ in self._pendientes.values()
                    if t.ejecutor == node_id and t.estado == ASIGNADA
                    and not t.asignando and node_id != self.node_id]

    def vencidas(self):
        with self._candado:
            return [t for t, _ in self._pendientes.values()
                    if t.vencida() and not t.asignando
                    and t.ejecutor != self.node_id]

    def pendientes(self):
        with self._candado:
            return [t for t, _ in self._pendientes.values()]

    def _al_recibir_resultado(self, m, ip_origen):
        self._resolver((m.payload or {}).get("tarea_id"), m.sender,
                       m.payload or {})

    def _resolver(self, tarea_id, quien, r):
        with self._candado:
            par = self._pendientes.get(tarea_id)
        if par is None:
            return
        tarea = par[0]
        if r.get("ok"):
            if quien != self.node_id:
                self.planificador.registrar_exito(quien)
            self._terminar(tarea, resultado=r.get("resultado"),
                           ejecutor=quien, duracion=r.get("duracion"))
        elif r.get("codigo") == DESCONOCIDA:
            threading.Thread(target=self._reasignar_cuando_pueda,
                             args=(tarea, quien), daemon=True).start()
        else:
            self._terminar(tarea, error=r.get("error"), ejecutor=quien)

    def _reasignar_cuando_pueda(self, tarea, quien):
        for _ in range(200):
            if not self._sigue_pendiente(tarea):
                return
            if self.reasignar_tarea(tarea, "operacion_desconocida", quien):
                return
            time.sleep(0.05)

    def _terminar(self, tarea, resultado=None, error=None, ejecutor=None,
                  duracion=None):
        with self._candado:
            par = self._pendientes.pop(tarea.tarea_id, None)
        if par is None:
            return
        self._soltar(tarea)
        futuro = par[1]
        if error is None:
            tarea.completar(resultado, ejecutor)
            self._evento("tarea_completada", tarea=tarea.tarea_id,
                         operacion=tarea.operacion,
                         ejecutor=self._nombre(ejecutor),
                         intentos=tarea.intentos, duracion=duracion)
            futuro.set_result(resultado)
        else:
            tarea.fallar(error)
            self._evento("tarea_fallida", tarea=tarea.tarea_id,
                         operacion=tarea.operacion, error=error,
                         intentos=tarea.intentos)
            futuro.set_exception(TareaFallida(error))

    def _al_recibir_solicitud(self, m, ip_origen):
        requisitos = (m.payload or {}).get("requisitos") or []
        if requisitos and self.sabe_hacer(requisitos):
            self.descubrimiento.anunciarse()

    def _al_recibir_asignacion(self, m, ip_origen):
        p = m.payload or {}
        tarea_id = p.get("tarea_id")
        puerto = p.get("puerto_tcp")
        solicitante = m.sender

        def responder(r):
            self.mensajes.enviar(ip_origen, puerto, TASK_RESULT, solicitante,
                                 r, timeout=3.0, reintentos=2)

        funcion = self._operaciones.get(p.get("operacion"))
        if funcion is None or not puerto:
            responder({"tarea_id": tarea_id, "ok": False,
                       "codigo": DESCONOCIDA,
                       "error": f"no se ejecutar {p.get('operacion')}"})
            return
        self._evento("tarea_recibida", tarea=tarea_id,
                     operacion=p.get("operacion"),
                     solicitante=self._nombre(solicitante))
        self._encolar(tarea_id, funcion, p.get("datos"), responder)

    def _encolar(self, tarea_id, funcion, datos, al_terminar):
        self.recursos.tarea_iniciada()
        self.descubrimiento.publicar_recursos()
        self._cola.put((tarea_id, funcion, datos, al_terminar))

    def _trabajar(self):
        while self._corriendo:
            try:
                tarea_id, funcion, datos, al_terminar = self._cola.get(
                    timeout=0.5)
            except queue.Empty:
                continue
            inicio = time.monotonic()
            try:
                resultado = funcion(datos)
                json.dumps(resultado)
                r = {"tarea_id": tarea_id, "ok": True, "resultado": resultado}
            except Exception as e:
                r = {"tarea_id": tarea_id, "ok": False, "codigo": ERROR,
                     "error": f"{type(e).__name__}: {e}"}
            r["duracion"] = round(time.monotonic() - inicio, 3)
            self.recursos.tarea_terminada(r["ok"])
            self.descubrimiento.publicar_recursos()
            try:
                al_terminar(r)
            except Exception as e:
                print(f"[{self.descubrimiento.nombre}] no se pudo devolver "
                      f"el resultado de {tarea_id}: {e}")

    def iniciar(self):
        self._corriendo = True
        self._trabajadores = []
        for _ in range(self.recursos.max_tareas):
            h = threading.Thread(target=self._trabajar, daemon=True)
            h.start()
            self._trabajadores.append(h)
        self.recuperacion.iniciar()
        return self

    def detener(self):
        self._corriendo = False
        self.recuperacion.detener()
        for tarea in self.pendientes():
            self._terminar(tarea, error="el nodo se detuvo")
        for h in self._trabajadores:
            h.join(timeout=1.0)
        self._trabajadores = []
