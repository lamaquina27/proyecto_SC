import json
import threading
import time
import uuid

HELLO = "HELLO"
HELLO_ACK = "HELLO_ACK"
RESOURCE_UPDATE = "RESOURCE_UPDATE"
TASK_REQUEST = "TASK_REQUEST"
TASK_ASSIGN = "TASK_ASSIGN"
TASK_RESULT = "TASK_RESULT"
HEARTBEAT = "HEARTBEAT"
NODE_STATUS = "NODE_STATUS"
GOODBYE = "GOODBYE"

ANUNCIO = "ANUNCIO"
PING = "PING"
PONG = "PONG"
APP_MSG = "APP_MSG"

MAX_UDP = 1400
CABECERAS_IP_UDP = 28


def limite_udp(mtu):
    if not mtu:
        return MAX_UDP
    return max(0, min(MAX_UDP, mtu - CABECERAS_IP_UDP))


class MensajeMuyGrande(Exception):
    pass


class Mensaje:
    def __init__(self, tipo, sender, receiver=None, payload=None,
                 seq=0, lamport=0, grupo=None):
        self.message_id = uuid.uuid4().hex[:8]
        self.type = tipo
        self.sender = sender
        self.receiver = receiver
        self.group = grupo
        self.timestamp = time.time()
        self.seq = seq
        self.lamport = lamport
        self.payload = payload if payload is not None else {}

    def to_bytes(self):
        return json.dumps({
            "message_id": self.message_id,
            "type": self.type,
            "sender": self.sender,
            "receiver": self.receiver,
            "group": self.group,
            "timestamp": self.timestamp,
            "seq": self.seq,
            "lamport": self.lamport,
            "payload": self.payload,
        }, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def from_bytes(datos):
        try:
            d = json.loads(datos.decode("utf-8", errors="ignore"))
        except (ValueError, AttributeError):
            return None
        if not isinstance(d, dict):
            return None
        if "type" not in d or "sender" not in d:
            return None

        m = Mensaje(d["type"], d["sender"], d.get("receiver"),
                    d.get("payload"), d.get("seq", 0), d.get("lamport", 0),
                    d.get("group"))
        m.message_id = d.get("message_id", m.message_id)
        m.timestamp = d.get("timestamp", m.timestamp)
        return m

    def cabe_en_udp(self, limite=MAX_UDP):
        return len(self.to_bytes()) <= limite

    def __repr__(self):
        return f"<{self.type} de {self.sender} seq={self.seq}>"


class RelojLamport:
    def __init__(self):
        self.valor = 0
        self._candado = threading.Lock()

    def tick(self):
        with self._candado:
            self.valor += 1
            return self.valor

    def actualizar(self, recibido):
        with self._candado:
            self.valor = max(self.valor, int(recibido or 0)) + 1
            return self.valor
