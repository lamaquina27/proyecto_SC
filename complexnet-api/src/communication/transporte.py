import socket
import struct
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from .malla import difusion_de, ip_de, mtu_de
from .message import Mensaje, MensajeMuyGrande, RelojLamport, limite_udp

CABECERA = 4
MAX_TCP = 4 * 1024 * 1024
MAX_DATAGRAMA = 65535
REINTENTOS = 2
ESPERA_REINTENTO = 0.5
MEMORIA_DUPLICADOS = 1024
HILOS_ENVIO = 8


class ServicioMensajes:
    def __init__(self, node_id, interfaz="bat0", puerto_udp=5000,
                 puerto_tcp=5001, difusion=None):
        self.node_id = node_id
        self.interfaz = interfaz
        self.puerto_udp = puerto_udp
        self.puerto_tcp = puerto_tcp

        self.difusion = difusion or difusion_de(interfaz) or "255.255.255.255"
        self.ip = ip_de(interfaz) or self._ip_de_salida()
        self.mtu = mtu_de(interfaz)
        self.max_udp = limite_udp(self.mtu)

        self.reloj = RelojLamport()
        self.seq = 0
        self.grupos = set()

        self._manejadores = {}
        self._al_fallar = []
        self._vistos = OrderedDict()
        self._corriendo = False
        self._candado = threading.Lock()
        self._candado_stats = threading.Lock()
        self._hilos = []

        self.stats = {
            "enviados": 0, "recibidos": 0, "descartados": 0,
            "duplicados": 0, "bytes_enviados": 0, "bytes_recibidos": 0,
            "fallos_envio": 0, "reintentos": 0,
        }

        self._sock_udp = None
        self._sock_tcp = None
        self._error_inicio = None

        self._sock_envio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock_envio.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._atar_a_interfaz(self._sock_envio)

    def _atar_a_interfaz(self, sock):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE,
                            self.interfaz.encode())
            return True
        except (OSError, AttributeError):
            return False

    @staticmethod
    def _ip_de_salida():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            s.close()

    def _contar(self, clave, cuanto=1):
        with self._candado_stats:
            self.stats[clave] += cuanto

    def al_recibir(self, tipo, funcion):
        self._manejadores.setdefault(tipo, []).append(funcion)

    def cuando_falle(self, funcion):
        self._al_fallar.append(funcion)

    def _avisar_fallo(self, mensaje, ip, puerto, error):
        if not self._al_fallar:
            print(f"[{self.node_id}] no se pudo enviar {mensaje.type} a "
                  f"{ip}:{puerto}: {error}")
        for funcion in list(self._al_fallar):
            try:
                funcion(mensaje, ip, puerto, error)
            except Exception as e:
                print(f"[{self.node_id}] error avisando un fallo: {e}")

    def unirse(self, grupo):
        with self._candado:
            self.grupos.add(grupo)

    def abandonar(self, grupo):
        with self._candado:
            self.grupos.discard(grupo)

    def mis_grupos(self):
        with self._candado:
            return sorted(self.grupos)

    def _es_para_mi(self, mensaje):
        if mensaje.receiver and mensaje.receiver != self.node_id:
            return False
        if mensaje.group is not None:
            with self._candado:
                return mensaje.group in self.grupos
        return True

    def _ya_visto(self, mensaje):
        clave = (mensaje.sender, mensaje.message_id)
        with self._candado:
            if clave in self._vistos:
                return True
            self._vistos[clave] = True
            if len(self._vistos) > MEMORIA_DUPLICADOS:
                self._vistos.popitem(last=False)
        return False

    def _repartir(self, mensaje, origen_ip):
        if mensaje.sender == self.node_id:
            return
        if not self._es_para_mi(mensaje):
            self._contar("descartados")
            return
        if self._ya_visto(mensaje):
            self._contar("duplicados")
            return

        self.reloj.actualizar(mensaje.lamport)
        self._contar("recibidos")

        for funcion in list(self._manejadores.get(mensaje.type, [])):
            try:
                funcion(mensaje, origen_ip)
            except Exception as e:
                print(f"[{self.node_id}] error atendiendo {mensaje.type}: {e}")

    def _armar(self, tipo, receiver, payload, grupo=None):
        with self._candado:
            self.seq += 1
            seq = self.seq
        return Mensaje(tipo, self.node_id, receiver, payload,
                       seq=seq, lamport=self.reloj.tick(), grupo=grupo)

    def _difundir_mensaje(self, m):
        datos = m.to_bytes()
        if len(datos) > self.max_udp:
            raise MensajeMuyGrande(
                f"{len(datos)} bytes no caben en un datagrama de la malla "
                f"(maximo {self.max_udp}). Use enviar() por TCP.")
        try:
            self._sock_envio.sendto(datos, (self.difusion, self.puerto_udp))
        except OSError as e:
            self._contar("fallos_envio")
            self._avisar_fallo(m, self.difusion, self.puerto_udp, e)
            return None
        self._contar("enviados")
        self._contar("bytes_enviados", len(datos))
        return m

    def difundir(self, tipo, payload=None):
        return self._difundir_mensaje(self._armar(tipo, None, payload))

    def multidifundir(self, grupo, tipo, payload=None):
        return self._difundir_mensaje(self._armar(tipo, None, payload, grupo))

    def enviar(self, ip, puerto, tipo, receiver=None, payload=None,
               timeout=5.0, reintentos=REINTENTOS, grupo=None):
        m = self._armar(tipo, receiver, payload, grupo)
        datos = m.to_bytes()
        trama = struct.pack("!I", len(datos)) + datos
        error = None
        for intento in range(reintentos + 1):
            if intento:
                self._contar("reintentos")
                time.sleep(ESPERA_REINTENTO * intento)
            try:
                with socket.create_connection((ip, puerto),
                                              timeout=timeout) as s:
                    s.sendall(trama)
            except OSError as e:
                error = e
                continue
            self._contar("enviados")
            self._contar("bytes_enviados", len(trama))
            return m

        self._contar("fallos_envio")
        self._avisar_fallo(m, ip, puerto, error)
        return None

    def enviar_a_varios(self, destinos, tipo, payload=None, grupo=None,
                        timeout=5.0, reintentos=REINTENTOS):
        destinos = list(destinos)
        if not destinos:
            return {"entregados": [], "fallidos": []}

        def uno(destino):
            node_id, ip, puerto = destino
            m = self.enviar(ip, puerto, tipo, node_id, payload,
                            timeout, reintentos, grupo)
            return node_id, m is not None

        with ThreadPoolExecutor(min(HILOS_ENVIO, len(destinos))) as hilos:
            resultados = list(hilos.map(uno, destinos))
        return {
            "entregados": [n for n, ok in resultados if ok],
            "fallidos": [n for n, ok in resultados if not ok],
        }

    def _escuchar_udp(self, listo):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._atar_a_interfaz(s)
        s.settimeout(1.0)
        self._sock_udp = s
        try:
            s.bind(("", self.puerto_udp))
        except OSError as e:
            self._error_inicio = OSError(
                f"no se pudo abrir el puerto UDP {self.puerto_udp}: {e}")
            listo.set()
            return
        listo.set()

        while self._corriendo:
            try:
                datos, origen = s.recvfrom(MAX_DATAGRAMA)
            except socket.timeout:
                continue
            except OSError:
                break
            self._contar("bytes_recibidos", len(datos))
            m = Mensaje.from_bytes(datos)
            if m:
                self._repartir(m, origen[0])
            else:
                self._contar("descartados")
        s.close()

    def _escuchar_tcp(self, listo):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._atar_a_interfaz(s)
        s.settimeout(1.0)
        self._sock_tcp = s
        try:
            s.bind(("", self.puerto_tcp))
            s.listen(16)
        except OSError as e:
            self._error_inicio = OSError(
                f"no se pudo abrir el puerto TCP {self.puerto_tcp}: {e}")
            listo.set()
            return
        listo.set()

        while self._corriendo:
            try:
                conexion, origen = s.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._atender,
                             args=(conexion, origen[0]), daemon=True).start()
        s.close()

    def _atender(self, conexion, origen_ip):
        with conexion:
            conexion.settimeout(10)
            try:
                cabecera = self._leer_exacto(conexion, CABECERA)
                if cabecera is None:
                    return
                largo = struct.unpack("!I", cabecera)[0]
                if largo > MAX_TCP:
                    self._contar("descartados")
                    return
                datos = self._leer_exacto(conexion, largo)
            except OSError:
                return

        if datos is None:
            self._contar("descartados")
            return
        self._contar("bytes_recibidos", len(datos) + CABECERA)
        m = Mensaje.from_bytes(datos)
        if m:
            self._repartir(m, origen_ip)
        else:
            self._contar("descartados")

    @staticmethod
    def _leer_exacto(conexion, cuantos):
        trozos = bytearray()
        while len(trozos) < cuantos:
            pedazo = conexion.recv(min(8192, cuantos - len(trozos)))
            if not pedazo:
                return None
            trozos.extend(pedazo)
        return bytes(trozos)

    def iniciar(self):
        self._corriendo = True
        self._hilos = []
        self._error_inicio = None
        abiertos = []
        for destino in (self._escuchar_udp, self._escuchar_tcp):
            listo = threading.Event()
            h = threading.Thread(target=destino, args=(listo,), daemon=True)
            h.start()
            self._hilos.append(h)
            abiertos.append(listo)
        for listo in abiertos:
            listo.wait(timeout=5.0)
        if self._error_inicio is not None:
            error = self._error_inicio
            self.detener()
            raise error
        return self

    def detener(self):
        self._corriendo = False
        for s in (self._sock_envio, self._sock_udp, self._sock_tcp):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass
        for h in self._hilos:
            h.join(timeout=2.0)
        self._hilos = []
        self._sock_udp = None
        self._sock_tcp = None

    def metricas(self):
        with self._candado_stats:
            return dict(self.stats)
