import threading
import time


class Contacto:
    def __init__(self, node_id, nombre, ip, puerto_tcp):
        self.node_id = node_id
        self.nombre = nombre
        self.ip = ip
        self.puerto_tcp = puerto_tcp
        self.visto = time.monotonic()

    def resumen(self):
        return {"node_id": self.node_id, "nombre": self.nombre,
                "ip": self.ip, "puerto_tcp": self.puerto_tcp,
                "hace": round(time.monotonic() - self.visto, 1)}


class Directorio:
    def __init__(self):
        self._contactos = {}
        self._candado = threading.Lock()

    def registrar(self, node_id, nombre, ip, puerto_tcp):
        nuevo = False
        with self._candado:
            c = self._contactos.get(node_id)
            if c is None:
                self._contactos[node_id] = Contacto(node_id, nombre, ip,
                                                    puerto_tcp)
                nuevo = True
            else:
                c.ip, c.nombre, c.puerto_tcp = ip, nombre, puerto_tcp
                c.visto = time.monotonic()
        return nuevo

    def buscar(self, node_id):
        with self._candado:
            return self._contactos.get(node_id)

    def por_nombre(self, nombre):
        with self._candado:
            for c in self._contactos.values():
                if c.nombre == nombre:
                    return c
        return None

    def todos(self):
        with self._candado:
            return [c.resumen() for c in self._contactos.values()]

    def olvidar(self, node_id):
        with self._candado:
            self._contactos.pop(node_id, None)

    def __len__(self):
        with self._candado:
            return len(self._contactos)
