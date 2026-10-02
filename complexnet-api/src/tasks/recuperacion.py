import threading
import time

NODO_CAIDO = "nodo_caido"
TIEMPO_AGOTADO = "tiempo_agotado"


class GestorRecuperacion:
    def __init__(self, gestor, intervalo=0.5):
        self.gestor = gestor
        self.intervalo = intervalo
        self.reintentos = 0
        self._corriendo = False
        self._hilo = None
        gestor.descubrimiento.cuando_salga(self.recuperar_nodo)

    def recuperar_nodo(self, node_id):
        for tarea in self.gestor.tareas_en(node_id):
            self._reasignar(tarea, NODO_CAIDO)

    def _reasignar(self, tarea, motivo):
        culpable = tarea.ejecutor
        if self.gestor.reasignar_tarea(tarea, motivo, culpable):
            self.gestor.planificador.registrar_fallo(culpable)
            self.reintentos += 1

    def _vigilar(self):
        while self._corriendo:
            for tarea in self.gestor.vencidas():
                self._reasignar(tarea, TIEMPO_AGOTADO)
            time.sleep(self.intervalo)

    def iniciar(self):
        self._corriendo = True
        self._hilo = threading.Thread(target=self._vigilar, daemon=True)
        self._hilo.start()

    def detener(self):
        self._corriendo = False
        if self._hilo:
            self._hilo.join(timeout=2.0)
            self._hilo = None
