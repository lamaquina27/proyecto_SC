import os
import shutil
import threading
import time

from ..communication import malla

try:
    import psutil
except ImportError:
    psutil = None

NEUTRO = 0.5
EN_COLA = "cola"
CORRIENDO = "corriendo"
TAREAS_PUBLICADAS = 6


def _acotar(valor):
    return round(max(0.0, min(1.0, float(valor))), 3)


class Recurso:
    def __init__(self, nombre, tipo, capacidad=1.0, disponible=True):
        self.nombre = nombre
        self.tipo = tipo
        self.capacidad = capacidad
        self.disponible = disponible

    def resumen(self):
        return {"nombre": self.nombre, "tipo": self.tipo,
                "capacidad": self.capacidad, "disponible": self.disponible}


class GestorRecursos:
    def __init__(self, max_tareas=2, carpeta_disco="."):
        self.max_tareas = max(1, int(max_tareas))
        self.carpeta_disco = carpeta_disco
        self._recursos = {}
        self._en_curso = 0
        self._tareas = {}
        self._exitos = 0
        self._fallos = 0
        self._candado = threading.Lock()

    def registrar_recurso(self, nombre, tipo, capacidad=1.0):
        with self._candado:
            self._recursos[nombre] = Recurso(nombre, tipo, capacidad)

    def actualizar_recurso(self, nombre, disponible=None, capacidad=None):
        with self._candado:
            r = self._recursos.get(nombre)
            if r is None:
                return False
            if disponible is not None:
                r.disponible = disponible
            if capacidad is not None:
                r.capacidad = capacidad
            return True

    def obtener_recursos(self):
        with self._candado:
            return [r.resumen() for r in self._recursos.values()]

    def tarea_iniciada(self, tarea_id=None, operacion=None, solicitante=None):
        with self._candado:
            self._en_curso += 1
            if tarea_id is not None:
                self._tareas[tarea_id] = {
                    "tarea_id": tarea_id, "operacion": operacion,
                    "de": solicitante, "estado": EN_COLA,
                    "inicio": time.monotonic()}

    def tarea_corriendo(self, tarea_id):
        with self._candado:
            t = self._tareas.get(tarea_id)
            if t is None:
                return 0.0
            espera = time.monotonic() - t["inicio"]
            t["estado"] = CORRIENDO
            t["inicio"] = time.monotonic()
            return espera

    def tarea_terminada(self, exito, tarea_id=None):
        with self._candado:
            self._en_curso = max(0, self._en_curso - 1)
            self._tareas.pop(tarea_id, None)
            if exito:
                self._exitos += 1
            else:
                self._fallos += 1

    def tareas(self):
        ahora = time.monotonic()
        with self._candado:
            lista = [dict(t) for t in self._tareas.values()]
        for t in lista:
            t["segundos"] = round(ahora - t.pop("inicio"), 1)
        lista.sort(key=lambda t: (t["estado"] != CORRIENDO, -t["segundos"]))
        return lista

    def historial(self):
        with self._candado:
            return {"hechas": self._exitos, "fallidas": self._fallos}

    def carga(self):
        with self._candado:
            return _acotar(self._en_curso / self.max_tareas)

    def confiabilidad(self):
        with self._candado:
            return _acotar((self._exitos + 1) / (self._exitos + self._fallos + 2))

    @staticmethod
    def cpu_libre():
        if psutil:
            return _acotar(1.0 - psutil.cpu_percent(interval=None) / 100.0)
        if hasattr(os, "getloadavg"):
            nucleos = os.cpu_count() or 1
            return _acotar(1.0 - os.getloadavg()[0] / nucleos)
        return NEUTRO

    @staticmethod
    def memoria_libre():
        if psutil:
            m = psutil.virtual_memory()
            return _acotar(m.available / m.total)
        try:
            datos = {}
            with open("/proc/meminfo", encoding="utf-8") as f:
                for linea in f:
                    clave, valor = linea.split(":", 1)
                    datos[clave] = int(valor.split()[0])
            return _acotar(datos["MemAvailable"] / datos["MemTotal"])
        except (OSError, KeyError, ValueError):
            return NEUTRO

    def almacenamiento_libre(self):
        try:
            uso = shutil.disk_usage(self.carpeta_disco)
            return _acotar(uso.free / uso.total)
        except OSError:
            return NEUTRO

    @staticmethod
    def disponibilidad():
        if psutil and hasattr(psutil, "sensors_battery"):
            try:
                bateria = psutil.sensors_battery()
            except Exception:
                bateria = None
            if bateria is not None and not bateria.power_plugged:
                return _acotar(bateria.percent / 100.0)
        return 1.0

    def medir(self):
        estado = {
            "cpu": self.cpu_libre(),
            "memoria": self.memoria_libre(),
            "ancho_banda": _acotar(malla.calidad_promedio()),
            "confiabilidad": self.confiabilidad(),
            "disponibilidad": self.disponibilidad(),
            "carga": self.carga(),
            "almacenamiento": self.almacenamiento_libre(),
            "capacidad": self.max_tareas,
        }
        estado.update(self.historial())
        tareas = self.tareas()
        if tareas:
            estado["tareas"] = [
                [t["tarea_id"], t["operacion"], t["de"], t["estado"],
                 int(t["segundos"])]
                for t in tareas[:TAREAS_PUBLICADAS]]
            estado["en_cola"] = sum(t["estado"] == EN_COLA for t in tareas)
        recursos = self.obtener_recursos()
        if recursos:
            estado["recursos"] = recursos
        return estado
