import time

ACTIVO = "ACTIVO"
SOSPECHOSO = "SOSPECHOSO"
INACTIVO = "INACTIVO"


class Vecino:
    def __init__(self, node_id, nombre, ip, puerto_tcp, servicios=None,
                 grupos=None):
        self.node_id = node_id
        self.nombre = nombre
        self.ip = ip
        self.puerto_tcp = puerto_tcp
        self.servicios = servicios or []
        self.grupos = grupos or []

        self.estado = {}
        self.status = ACTIVO
        self.visto = time.monotonic()
        self.ultimo_seq = 0

    def disponible(self):
        return self.status == ACTIVO

    def ofrece(self, servicios_pedidos):
        return all(s in self.servicios for s in servicios_pedidos)

    def esta_en(self, grupo):
        return grupo in self.grupos

    def silencio(self):
        return time.monotonic() - self.visto

    def resumen(self):
        return {
            "node_id": self.node_id,
            "nombre": self.nombre,
            "ip": self.ip,
            "puerto_tcp": self.puerto_tcp,
            "status": self.status,
            "servicios": list(self.servicios),
            "grupos": list(self.grupos),
            "estado": dict(self.estado),
            "silencio": round(self.silencio(), 1),
        }

    def __repr__(self):
        return f"<{self.nombre} {self.status} hace {self.silencio():.0f}s>"
