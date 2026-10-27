import base64
import hashlib
import os
import tempfile
import threading
import time
import uuid
import zlib

from .message import FILE_ACK, FILE_CHUNK

TROZO = 256 * 1024
ABANDONO = 120.0
CARPETA_PARCIALES = ".parciales"

ZLIB = "zlib"
NIVEL = 6
MUESTRA = 256 * 1024
MINIMO_COMPRIMIR = 1024
VALE_LA_PENA = 0.9
BLOQUE = 1024 * 1024


def huella(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(BLOQUE), b""):
            h.update(bloque)
    return h.hexdigest()


def nombre_seguro(nombre):
    nombre = os.path.basename(str(nombre).replace("\\", "/")).strip()
    if nombre in ("", ".", ".."):
        return "archivo"
    return nombre


def comprimir_archivo(ruta, destino, nivel=NIVEL):
    compresor = zlib.compressobj(nivel)
    with open(ruta, "rb") as entrada, open(destino, "wb") as salida:
        for bloque in iter(lambda: entrada.read(BLOQUE), b""):
            salida.write(compresor.compress(bloque))
        salida.write(compresor.flush())
    return os.path.getsize(destino)


def descomprimir_archivo(ruta, destino, limite):
    descompresor = zlib.decompressobj()
    escritos = 0

    def escribir(salida, datos):
        nonlocal escritos
        escritos += len(datos)
        if escritos > limite:
            raise ValueError("lo descomprimido es mas grande de lo anunciado")
        salida.write(datos)

    with open(ruta, "rb") as entrada, open(destino, "wb") as salida:
        for bloque in iter(lambda: entrada.read(BLOQUE), b""):
            datos = descompresor.decompress(bloque, BLOQUE)
            escribir(salida, datos)
            while descompresor.unconsumed_tail:
                datos = descompresor.decompress(
                    descompresor.unconsumed_tail, BLOQUE)
                escribir(salida, datos)
        escribir(salida, descompresor.flush())
    if not descompresor.eof:
        raise ValueError("los datos comprimidos estan incompletos")
    return escritos


class _Recepcion:
    def __init__(self, transfer_id, sender, nombre, tamano, sha256, total,
                 puerto, ruta_parcial, compresion=None, tamano_enviado=None):
        self.transfer_id = transfer_id
        self.sender = sender
        self.nombre = nombre
        self.tamano = tamano
        self.sha256 = sha256
        self.total = total
        self.puerto = puerto
        self.ruta_parcial = ruta_parcial
        self.compresion = compresion
        self.tamano_enviado = tamano if tamano_enviado is None else tamano_enviado
        self.recibidos = set()
        self.cerrando = False
        self.ultimo = time.monotonic()


class ServicioArchivos:
    def __init__(self, mensajes, carpeta="recibidos", trozo=TROZO,
                 abandono=ABANDONO, nivel=NIVEL):
        self.mensajes = mensajes
        self.carpeta = carpeta
        self.trozo = trozo
        self.abandono = abandono
        self.nivel = nivel
        self.registro = None
        self.node_id = mensajes.node_id

        self._recepciones = {}
        self._esperando = {}
        self._al_llegar = []
        self._candado = threading.Lock()

        mensajes.al_recibir(FILE_CHUNK, self._al_recibir_trozo)
        mensajes.al_recibir(FILE_ACK, self._al_recibir_confirmacion)

    def _evento(self, tipo, **datos):
        if self.registro is not None:
            self.registro.evento(tipo, **datos)

    def cuando_llegue(self, funcion):
        self._al_llegar.append(funcion)

    def _vale_comprimir(self, ruta, tamano):
        if tamano < MINIMO_COMPRIMIR:
            return False
        with open(ruta, "rb") as f:
            muestra = f.read(MUESTRA)
        return len(zlib.compress(muestra, self.nivel)) < len(muestra) * VALE_LA_PENA

    def _preparar(self, ruta, tamano, comprimir):
        if comprimir is False:
            return None
        if comprimir is None and not self._vale_comprimir(ruta, tamano):
            return None
        descriptor, temporal = tempfile.mkstemp(prefix="complexnet-",
                                                suffix=".zlib")
        os.close(descriptor)
        try:
            comprimido = comprimir_archivo(ruta, temporal, self.nivel)
        except Exception:
            os.remove(temporal)
            raise
        if comprimir is None and comprimido >= tamano * VALE_LA_PENA:
            os.remove(temporal)
            return None
        return temporal

    def enviar(self, ip, puerto, receiver, ruta, nombre=None, timeout=30.0,
               al_avanzar=None, comprimir=None):
        tamano = os.path.getsize(ruta)
        nombre = nombre_seguro(nombre or ruta)
        sha256 = huella(ruta)
        inicio = time.monotonic()
        temporal = self._preparar(ruta, tamano, comprimir)
        try:
            return self._enviar_trozos(ip, puerto, receiver, temporal or ruta,
                                       nombre, tamano, sha256, temporal,
                                       timeout, al_avanzar, inicio)
        finally:
            if temporal is not None:
                try:
                    os.remove(temporal)
                except OSError:
                    pass

    def _enviar_trozos(self, ip, puerto, receiver, origen, nombre, tamano,
                       sha256, comprimido, timeout, al_avanzar, inicio):
        tamano_enviado = os.path.getsize(origen)
        total = max(1, -(-tamano_enviado // self.trozo))
        transfer_id = uuid.uuid4().hex[:8]

        listo = threading.Event()
        with self._candado:
            self._esperando[transfer_id] = [listo, None]

        resultado = {"transfer_id": transfer_id, "nombre": nombre,
                     "tamano": tamano, "trozos": total, "sha256": sha256,
                     "comprimido": comprimido is not None,
                     "tamano_enviado": tamano_enviado,
                     "entregado": False, "ruta": None, "error": None}
        self._evento("archivo_envio", transfer=transfer_id, nombre=nombre,
                     tamano=tamano, trozos=total, destino=receiver,
                     compresion=ZLIB if comprimido else None,
                     tamano_enviado=tamano_enviado)
        try:
            with open(origen, "rb") as f:
                for indice in range(total):
                    datos = f.read(self.trozo)
                    payload = {
                        "transfer_id": transfer_id, "nombre": nombre,
                        "tamano": tamano, "sha256": sha256,
                        "indice": indice, "total": total,
                        "posicion": indice * self.trozo,
                        "puerto_tcp": self.mensajes.puerto_tcp,
                        "datos": base64.b64encode(datos).decode("ascii"),
                    }
                    if comprimido is not None:
                        payload["compresion"] = ZLIB
                        payload["tamano_enviado"] = tamano_enviado
                    if self.mensajes.enviar(ip, puerto, FILE_CHUNK, receiver,
                                            payload) is None:
                        resultado["error"] = (f"no se pudo entregar el trozo "
                                              f"{indice + 1} de {total}")
                        return self._cerrar_envio(resultado, inicio)
                    if al_avanzar is not None:
                        al_avanzar(indice + 1, total)

            if not listo.wait(timeout):
                resultado["error"] = "el destino no confirmo la recepcion"
                return self._cerrar_envio(resultado, inicio)
            with self._candado:
                respuesta = self._esperando[transfer_id][1]
            if respuesta.get("ok"):
                resultado["entregado"] = True
                resultado["ruta"] = respuesta.get("ruta")
            else:
                resultado["error"] = respuesta.get("error", "rechazado")
            return self._cerrar_envio(resultado, inicio)
        finally:
            with self._candado:
                self._esperando.pop(transfer_id, None)

    def _cerrar_envio(self, resultado, inicio):
        resultado["segundos"] = round(time.monotonic() - inicio, 3)
        if resultado["entregado"]:
            self._evento("archivo_enviado", transfer=resultado["transfer_id"],
                         nombre=resultado["nombre"],
                         tamano=resultado["tamano"],
                         tamano_enviado=resultado["tamano_enviado"],
                         segundos=resultado["segundos"])
        else:
            self._evento("archivo_fallido", transfer=resultado["transfer_id"],
                         nombre=resultado["nombre"], error=resultado["error"])
        return resultado

    def _al_recibir_confirmacion(self, mensaje, origen_ip):
        p = mensaje.payload or {}
        with self._candado:
            espera = self._esperando.get(p.get("transfer_id"))
            if espera is None or espera[0].is_set():
                return
            espera[1] = p
            espera[0].set()

    def _al_recibir_trozo(self, mensaje, origen_ip):
        p = mensaje.payload or {}
        try:
            transfer_id = str(p["transfer_id"])
            indice = int(p["indice"])
            total = int(p["total"])
            posicion = int(p["posicion"])
            datos = base64.b64decode(p["datos"])
            tamano = int(p.get("tamano", 0))
            tamano_enviado = int(p.get("tamano_enviado", tamano))
        except (KeyError, TypeError, ValueError):
            return
        if not 0 <= indice < total or posicion < 0:
            return

        self._limpiar_abandonadas()
        clave = (mensaje.sender, transfer_id)
        with self._candado:
            r = self._recepciones.get(clave)
            if r is None:
                parciales = os.path.join(self.carpeta, CARPETA_PARCIALES)
                os.makedirs(parciales, exist_ok=True)
                ruta = os.path.join(parciales,
                                    f"{mensaje.sender}-{transfer_id}")
                open(ruta, "wb").close()
                r = _Recepcion(transfer_id, mensaje.sender,
                               nombre_seguro(p.get("nombre")), tamano,
                               p.get("sha256"), total, p.get("puerto_tcp"),
                               ruta, p.get("compresion"), tamano_enviado)
                self._recepciones[clave] = r
                self._evento("archivo_llegando", transfer=transfer_id,
                             nombre=r.nombre, tamano=r.tamano, trozos=total,
                             origen=mensaje.sender, compresion=r.compresion,
                             tamano_enviado=r.tamano_enviado)
            if r.cerrando or indice in r.recibidos:
                return
            if posicion + len(datos) > r.tamano_enviado:
                return
            with open(r.ruta_parcial, "r+b") as f:
                f.seek(posicion)
                f.write(datos)
            r.recibidos.add(indice)
            r.ultimo = time.monotonic()
            if len(r.recibidos) < r.total:
                return
            r.cerrando = True
            del self._recepciones[clave]

        self._terminar(r, origen_ip)

    def _revisar(self, r):
        if os.path.getsize(r.ruta_parcial) != r.tamano_enviado:
            return "el tamano no coincide"
        if r.compresion is not None:
            if r.compresion != ZLIB:
                return f"compresion {r.compresion} no soportada"
            descomprimido = r.ruta_parcial + ".descomprimido"
            try:
                descomprimir_archivo(r.ruta_parcial, descomprimido, r.tamano)
                os.replace(descomprimido, r.ruta_parcial)
            except (zlib.error, ValueError, OSError) as e:
                if os.path.exists(descomprimido):
                    os.remove(descomprimido)
                return f"no se pudo descomprimir: {e}"
            if os.path.getsize(r.ruta_parcial) != r.tamano:
                return "el tamano descomprimido no coincide"
        if huella(r.ruta_parcial) != r.sha256:
            return "la huella sha256 no coincide"
        return None

    def _terminar(self, r, origen_ip):
        ruta = None
        error = self._revisar(r)
        if error is None:
            ruta = self._ruta_libre(r.nombre)
            os.replace(r.ruta_parcial, ruta)
        else:
            os.remove(r.ruta_parcial)

        if r.puerto is not None:
            self.mensajes.enviar(origen_ip, int(r.puerto), FILE_ACK, r.sender,
                                 {"transfer_id": r.transfer_id,
                                  "ok": error is None, "error": error,
                                  "ruta": ruta},
                                 timeout=3.0, reintentos=1)
        if error is not None:
            self._evento("archivo_rechazado", transfer=r.transfer_id,
                         nombre=r.nombre, origen=r.sender, error=error)
            return

        info = {"transfer_id": r.transfer_id, "nombre": r.nombre,
                "ruta": ruta, "tamano": r.tamano, "sha256": r.sha256,
                "de": r.sender, "ip": origen_ip,
                "comprimido": r.compresion is not None,
                "tamano_enviado": r.tamano_enviado}
        self._evento("archivo_recibido", transfer=r.transfer_id,
                     nombre=r.nombre, tamano=r.tamano, origen=r.sender,
                     ruta=ruta, compresion=r.compresion,
                     tamano_enviado=r.tamano_enviado)
        for funcion in list(self._al_llegar):
            try:
                funcion(info)
            except Exception as e:
                print(f"[{self.node_id}] error avisando un archivo: {e}")

    def _ruta_libre(self, nombre):
        base, extension = os.path.splitext(nombre)
        ruta = os.path.join(self.carpeta, nombre)
        n = 1
        while os.path.exists(ruta):
            ruta = os.path.join(self.carpeta, f"{base} ({n}){extension}")
            n += 1
        return ruta

    def _limpiar_abandonadas(self):
        ahora = time.monotonic()
        with self._candado:
            viejas = [c for c, r in self._recepciones.items()
                      if ahora - r.ultimo > self.abandono]
            quitadas = [self._recepciones.pop(c) for c in viejas]
        for r in quitadas:
            try:
                os.remove(r.ruta_parcial)
            except OSError:
                pass
            self._evento("archivo_abandonado", transfer=r.transfer_id,
                         nombre=r.nombre, origen=r.sender,
                         recibidos=len(r.recibidos), trozos=r.total)

    def en_curso(self):
        with self._candado:
            return [{"transfer_id": r.transfer_id, "nombre": r.nombre,
                     "de": r.sender, "recibidos": len(r.recibidos),
                     "trozos": r.total, "comprimido": r.compresion is not None}
                    for r in self._recepciones.values()]
