import threading

PESOS = {
    "cpu": 1.0,
    "memoria": 1.0,
    "ancho_banda": 1.0,
    "confiabilidad": 1.0,
    "carga": 1.0,
}
NEUTRO = 0.5
UMBRAL_DISPONIBILIDAD = 0.2


def _acotar(valor):
    try:
        return max(0.0, min(1.0, float(valor)))
    except (TypeError, ValueError):
        return NEUTRO


class PlanificadorDistribuido:
    def __init__(self, pesos=None, umbral_disponibilidad=UMBRAL_DISPONIBILIDAD):
        self.pesos = dict(PESOS)
        self.pesos.update(pesos or {})
        self.umbral_disponibilidad = umbral_disponibilidad
        self._exitos = {}
        self._fallos = {}
        self._pendientes = {}
        self._candado = threading.Lock()

    def registrar_exito(self, node_id):
        with self._candado:
            self._exitos[node_id] = self._exitos.get(node_id, 0) + 1

    def registrar_fallo(self, node_id):
        with self._candado:
            self._fallos[node_id] = self._fallos.get(node_id, 0) + 1

    def reputacion(self, node_id):
        with self._candado:
            e = self._exitos.get(node_id, 0)
            f = self._fallos.get(node_id, 0)
        return (e + 1) / (e + f + 2)

    def sumar_pendiente(self, node_id, cuanto=1):
        with self._candado:
            valor = self._pendientes.get(node_id, 0) + cuanto
            self._pendientes[node_id] = max(0, valor)

    def pendientes(self, node_id):
        with self._candado:
            return self._pendientes.get(node_id, 0)

    def variables(self, vecino):
        e = vecino.estado or {}
        capacidad = max(1, int(e.get("capacidad", 1) or 1))
        publicada = _acotar(e.get("confiabilidad", 1.0))
        carga = _acotar(e.get("carga", 0.0))
        return {
            "C": _acotar(e.get("cpu", NEUTRO)),
            "M": _acotar(e.get("memoria", NEUTRO)),
            "B": _acotar(e.get("ancho_banda", NEUTRO)),
            "R": min(publicada, self.reputacion(vecino.node_id)),
            "A": _acotar(e.get("disponibilidad", 1.0)),
            "L": min(1.0, carga + self.pendientes(vecino.node_id) / capacidad),
        }

    def calcular_aptitud(self, vecino):
        v = self.variables(vecino)
        w = self.pesos
        return (w["cpu"] * v["C"] + w["memoria"] * v["M"]
                + w["ancho_banda"] * v["B"] + w["confiabilidad"] * v["R"]
                - w["carga"] * v["L"])

    def candidatos(self, vecinos, excluir=()):
        return [v for v in vecinos
                if v.node_id not in excluir
                and self.variables(v)["A"] >= self.umbral_disponibilidad]

    def seleccionar_nodo(self, vecinos, excluir=()):
        opciones = self.candidatos(vecinos, excluir)
        if not opciones:
            return None, None
        puntajes = [(round(self.calcular_aptitud(v), 6),
                     -self.pendientes(v.node_id), v.node_id, v)
                    for v in opciones]
        mejor = max(puntajes, key=lambda p: p[:3])
        return mejor[3], mejor[0]
