import time
import uuid

CREADA = "CREADA"
ASIGNADA = "ASIGNADA"
COMPLETADA = "COMPLETADA"
FALLIDA = "FALLIDA"


class TareaFallida(Exception):
    pass


class Tarea:
    def __init__(self, operacion, datos=None, requisitos=None, prioridad=0,
                 timeout=30.0, max_intentos=3):
        self.tarea_id = uuid.uuid4().hex[:8]
        self.operacion = operacion
        self.datos = datos
        self.requisitos = list(requisitos) if requisitos else [operacion]
        self.prioridad = prioridad
        self.timeout = timeout
        self.max_intentos = max(1, int(max_intentos))

        self.estado = CREADA
        self.intentos = 0
        self.ejecutor = None
        self.enviada = None
        self.historial = []
        self.excluidos = set()
        self.resultado = None
        self.error = None

        self.asignando = False
        self.pregunto = False
        self.contado = None

    def asignar(self, node_id):
        self.intentos += 1
        self.ejecutor = node_id
        self.enviada = time.monotonic()
        self.estado = ASIGNADA
        self.historial.append(node_id)

    def vencida(self):
        return (self.estado == ASIGNADA and self.enviada is not None
                and time.monotonic() - self.enviada > self.timeout)

    def completar(self, resultado, ejecutor):
        self.resultado = resultado
        self.ejecutor = ejecutor
        self.estado = COMPLETADA

    def fallar(self, error):
        self.error = error
        self.estado = FALLIDA

    def payload(self, puerto_tcp):
        return {"tarea_id": self.tarea_id, "operacion": self.operacion,
                "datos": self.datos, "requisitos": self.requisitos,
                "prioridad": self.prioridad, "intento": self.intentos,
                "puerto_tcp": puerto_tcp}

    def resumen(self):
        return {"tarea_id": self.tarea_id, "operacion": self.operacion,
                "estado": self.estado, "intentos": self.intentos,
                "ejecutor": self.ejecutor, "historial": list(self.historial),
                "error": self.error}

    def __repr__(self):
        return f"<Tarea {self.tarea_id} {self.operacion} {self.estado}>"
