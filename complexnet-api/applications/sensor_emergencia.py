"""
Gestion de sensores ambientales para ComplexNet API (Fase 3).
Soporta lectura real desde la ESP32 por puerto serie (USB) y fallback simulado.

Cuando la ESP32 esta conectada (por ejemplo en /dev/ttyUSB0, /dev/ttyACM0 o COM):
    Lee las lineas JSON emitidas por la ESP32 cada ~2 segundos.

Cuando no hay ESP32 (los otros nodos de la red):
    Genera telemetria base realista con fluctuaciones ambientales naturales.
    Permite inyectar emergencias para demostracion (incendio, inundacion, escombros).
"""

import json
import os
import random
import sys
import threading
import time

try:
    import serial
    import serial.tools.list_ports
    TIENE_SERIAL = True
except ImportError:
    TIENE_SERIAL = False


PUERTOS_LINUX = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"]

VALOR_ADC_SECO = 3900.0    # Lectura del sensor en aire / seco total (0%)
VALOR_ADC_MOJADO = 1400.0  # Lectura del sensor sumergido / mojado (100%)


def calibrar_suelo(valor):
    """Convierte la lectura ADC (0-4095) a porcentaje de humedad de suelo (0-100%)."""
    if valor is None:
        return 40.0, None
    val = float(valor)
    if val <= 100.0:
        return round(max(0.0, min(100.0, val)), 1), None
    # Escala inversa: mayor ADC = menor humedad
    pct = 100.0 * (VALOR_ADC_SECO - val) / (VALOR_ADC_SECO - VALOR_ADC_MOJADO)
    pct_calibrado = round(max(0.0, min(100.0, pct)), 1)
    return pct_calibrado, int(val)


class SensorEmergencia:
    def __init__(self, puerto=None, baudios=115200, forzar_simulacion=False):
        self.puerto = puerto
        self.baudios = baudios
        self.forzar_simulacion = forzar_simulacion
        self.es_hardware = False
        self._serial = None
        self._hilo = None
        self._activo = False
        self._candado = threading.Lock()

        # Ultima lectura
        self._lectura = {
            "temp": 22.0,
            "hum_aire": 58.0,
            "suelo": 40.0,
            "luz": 1200.0,
            "fuente": "simulado",
            "t": time.time(),
        }

        # Estado de simulacion
        self.modo_simulado = "normal"
        self._puerto_candidato = None

    def iniciar(self):
        self._activo = True
        if not self.forzar_simulacion and TIENE_SERIAL:
            self._conectar_hardware(aviso_inicial=True)

        self._hilo = threading.Thread(target=self._bucle_lectura, daemon=True)
        self._hilo.start()
        return self

    def _conectar_hardware(self, aviso_inicial=False):
        puerto = self._detectar_puerto()
        if not puerto:
            if aviso_inicial:
                print("  [SENSOR] No se detecto ESP32 fisica. Usando modo simulador.", flush=True)
            return False

        self._puerto_candidato = puerto
        try:
            self._serial = serial.Serial(puerto, self.baudios, timeout=2.0)
            self.es_hardware = True
            self.puerto = puerto
            print(f"  [SENSOR] >>> ESP32 conectada exitosamente en {puerto} <<<", flush=True)
            return True
        except serial.SerialException as e:
            self._serial = None
            self.es_hardware = False
            msg = str(e)
            if "PermissionError" in msg or "Acceso denegado" in msg or "access is denied" in msg.lower():
                print(f"  [SENSOR] AVISO: Se detecto la ESP32 en {puerto}, pero el puerto esta ocupado.", flush=True)
                print(f"          Cierra la terminal del Monitor Serial en PlatformIO / VS Code para liberar {puerto}.", flush=True)
            elif aviso_inicial:
                print(f"  [SENSOR] No se pudo abrir {puerto}: {e}. Usando simulador.", flush=True)
            return False

    def detener(self):
        self._activo = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass

    def _detectar_puerto(self):
        if self.puerto:
            return self.puerto
        # Buscar en Windows o Linux usando pyserial
        try:
            puertos = list(serial.tools.list_ports.comports())
            # 1. Prioridad: dispositivos con chips USB-Serial conocidos
            for p in puertos:
                nom = p.device
                desc = (p.description or "").lower()
                hw = (p.hwid or "").lower()
                texto = f"{desc} {hw}"
                if "bluetooth" in texto or "vinculo bluetooth" in texto:
                    continue
                if any(k in texto for k in ("usb", "ch34", "cp210", "uart", "esp32", "serial")):
                    return nom

            # 2. Cualquier puerto COM que no sea Bluetooth
            for p in puertos:
                nom = p.device
                desc = (p.description or "").lower()
                if "bluetooth" not in desc:
                    return nom
        except Exception:
            pass

        # Buscar en rutas directas de Linux
        for p in PUERTOS_LINUX:
            if os.path.exists(p):
                return p
        return None

    def _bucle_lectura(self):
        ultimo_intento_reconnect = time.time()
        while self._activo:
            if self.es_hardware and self._serial:
                try:
                    linea = self._serial.readline().decode("utf-8", errors="ignore").strip()
                    if linea.startswith("{") and linea.endswith("}"):
                        datos = json.loads(linea)
                        suelo_pct, suelo_adc = calibrar_suelo(datos.get("suelo"))
                        with self._candado:
                            self._lectura = {
                                "temp": datos.get("temp", self._lectura["temp"]),
                                "hum_aire": datos.get("hum_aire", self._lectura["hum_aire"]),
                                "suelo": suelo_pct,
                                "suelo_adc": suelo_adc,
                                "luz": datos.get("luz", self._lectura["luz"]),
                                "fuente": f"esp32 ({self.puerto})",
                                "t": time.time(),
                            }
                except Exception:
                    self.es_hardware = False
                    if self._serial:
                        try:
                            self._serial.close()
                        except Exception:
                            pass
                    self._serial = None
            else:
                # Intentar reconectar cada 4 segundos si no tenemos hardware conectado
                ahora = time.time()
                if not self.forzar_simulacion and TIENE_SERIAL and (ahora - ultimo_intento_reconnect > 4.0):
                    ultimo_intento_reconnect = ahora
                    if self._conectar_hardware(aviso_inicial=False):
                        continue

                # Generacion simulada mientras no haya hardware
                self._actualizar_simulado()
                time.sleep(2.0)

    def _actualizar_simulado(self):
        with self._candado:
            m = self.modo_simulado
            if m == "incendio":
                t = round(random.uniform(55.0, 68.0), 1)
                ha = round(random.uniform(12.0, 20.0), 1)
                s = round(random.uniform(5.0, 15.0), 1)
                l = round(random.uniform(4000.0, 6500.0), 1)
            elif m == "inundacion":
                t = round(random.uniform(16.0, 22.0), 1)
                ha = round(random.uniform(88.0, 96.0), 1)
                s = round(random.uniform(88.0, 98.0), 1)
                l = round(random.uniform(200.0, 600.0), 1)
            elif m == "escombros":
                t = round(random.uniform(18.0, 21.0), 1)
                ha = round(random.uniform(60.0, 75.0), 1)
                s = round(random.uniform(35.0, 50.0), 1)
                l = round(random.uniform(0.0, 2.5), 1)  # Oscuridad casi total
            elif m == "calor":
                t = round(random.uniform(38.0, 43.0), 1)
                ha = round(random.uniform(40.0, 55.0), 1)
                s = round(random.uniform(25.0, 40.0), 1)
                l = round(random.uniform(1800.0, 3200.0), 1)
            else:  # normal
                t = round(22.0 + random.uniform(-1.5, 1.5), 1)
                ha = round(58.0 + random.uniform(-4.0, 4.0), 1)
                s = round(42.0 + random.uniform(-3.0, 3.0), 1)
                l = round(1200.0 + random.uniform(-150.0, 150.0), 1)

            self._lectura = {
                "temp": t,
                "hum_aire": ha,
                "suelo": s,
                "luz": l,
                "fuente": f"simulado ({m})",
                "t": time.time(),
            }

    def simular(self, modo):
        modos_validos = ["normal", "incendio", "inundacion", "escombros", "calor"]
        if modo not in modos_validos:
            raise ValueError(f"modo no valido. Opciones: {modos_validos}")
        with self._candado:
            self.modo_simulado = modo
        self._actualizar_simulado()
        return self.modo_simulado

    def leer(self):
        with self._candado:
            return dict(self._lectura)


if __name__ == "__main__":
    sensor = SensorEmergencia().iniciar()
    print("Iniciando sensor... Fuente:", sensor.leer()["fuente"])
    time.sleep(2.5)
    print("Lectura normal:", sensor.leer())
    sensor.simular("incendio")
    print("Lectura incendio:", sensor.leer())
    sensor.simular("escombros")
    print("Lectura escombros:", sensor.leer())
    sensor.detener()
