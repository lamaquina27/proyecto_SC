import socket
import struct
import subprocess

try:
    import fcntl
except ImportError:
    fcntl = None

SIOCGIFADDR = 0x8915
SIOCGIFBRDADDR = 0x8919
SIOCGIFMTU = 0x8921


def _consultar(interfaz, operacion):
    if fcntl is None:
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        return fcntl.ioctl(s.fileno(), operacion,
                           struct.pack("256s", interfaz.encode()[:15]))
    except OSError:
        return None
    finally:
        s.close()


def ip_de(interfaz="bat0"):
    r = _consultar(interfaz, SIOCGIFADDR)
    return socket.inet_ntoa(r[20:24]) if r else None


def difusion_de(interfaz="bat0"):
    r = _consultar(interfaz, SIOCGIFBRDADDR)
    return socket.inet_ntoa(r[20:24]) if r else None


def mtu_de(interfaz="bat0"):
    r = _consultar(interfaz, SIOCGIFMTU)
    return struct.unpack("i", r[16:20])[0] if r else None


def existe(interfaz="bat0"):
    return ip_de(interfaz) is not None


def vecinos_batman():
    try:
        salida = subprocess.run(["batctl", "neighbors"],
                                capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

    vecinos = []
    for linea in salida.stdout.splitlines():
        partes = linea.split()
        for i, p in enumerate(partes):
            if ":" in p and len(p) == 17:
                tq = None
                for siguiente in partes[i + 1:]:
                    limpio = siguiente.strip("()")
                    if limpio.isdigit():
                        tq = int(limpio)
                        break
                if tq is not None:
                    vecinos.append({"mac": p, "tq": tq,
                                    "calidad": round(tq / 255.0, 3)})
                break
    return vecinos


def calidad_promedio():
    v = vecinos_batman()
    if not v:
        return 1.0
    return round(sum(x["calidad"] for x in v) / len(v), 3)


def resumen(interfaz="bat0"):
    return {
        "interfaz": interfaz,
        "existe": existe(interfaz),
        "ip": ip_de(interfaz),
        "difusion": difusion_de(interfaz),
        "mtu": mtu_de(interfaz),
        "vecinos_directos": len(vecinos_batman()),
        "calidad_promedio": calidad_promedio(),
    }
