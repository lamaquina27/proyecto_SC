import os
import re
import uuid

CARPETA = os.path.join(os.path.expanduser("~"), ".complexnet")
FORMATO = re.compile(r"[0-9a-f]{8}")


def ruta_identidad(nombre, carpeta=None):
    limpio = re.sub(r"[^A-Za-z0-9_.-]", "_", nombre)
    return os.path.join(carpeta or CARPETA, f"{limpio}.id")


def identidad(nombre, carpeta=None):
    ruta = ruta_identidad(nombre, carpeta)
    try:
        with open(ruta, encoding="utf-8") as f:
            guardado = f.read().strip()
        if FORMATO.fullmatch(guardado):
            return guardado
    except OSError:
        pass

    nuevo = uuid.uuid4().hex[:8]
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(nuevo + "\n")
    except OSError:
        pass
    return nuevo
