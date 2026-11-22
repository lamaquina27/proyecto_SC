# Firmware de la Baliza Sensorial (ESP32-S3) — COMPLEXNET

Este directorio contiene el proyecto PlatformIO para compilar y cargar el firmware en la placa de desarrollo **ESP32-S3 N16R8** utilizada como baliza sensorial de campo.

---

## 1. Conexiones Físicas de Sensores

| Sensor | Señal del Sensor | Pin en ESP32-S3 | Alimentación |
|---|---|---|---|
| **DHT11** (Temp / Humedad aire) | DATA | **GPIO 4** | 3.3V / GND |
| **Sensor de Suelo Capacitivo v2** | AOUT (Analógico) | **GPIO 5** (ADC1_CH4) | 3.3V / GND |
| **GY-302 (BH1750)** (Luminosidad) | SDA | **GPIO 8** | 3.3V / GND |
| **GY-302 (BH1750)** (Luminosidad) | SCL | **GPIO 9** | 3.3V / GND |

---

## 2. Dependencias de Bibliotecas (PlatformIO)

Declaradas en `platformio.ini`:
* `adafruit/DHT sensor library` (Lectura digital del DHT11)
* `adafruit/Adafruit Unified Sensor` (Capa base de sensores Adafruit)
* `claws/BH1750` (Control I2C del sensor de iluminación)

---

## 3. Protocolo de Transmisión Serial

* **Velocidad de puerto serie:** `115200` baudios.
* **Frecuencia de emisión:** Cada 2 segundos (2000 ms).
* **Formato de trama:** JSON puro de una sola línea terminado en salto de línea `\n`:
  ```json
  {"temp": 24.2, "hum_aire": 56.0, "suelo": 3540, "luz": 185.0}
  ```
  *(Si un sensor falla o se desconecta físicamente, el campo correspondiente reporta `null`).*

---

## 4. Instrucciones para Flashear el Firmware

1. Instala la extensión **PlatformIO IDE** en VS Code o instala PlatformIO Core (`pip install platformio`).
2. Abre esta carpeta en VS Code / PlatformIO.
3. Conecta la ESP32 por USB (identifica el puerto, p. ej. `COM3` en Windows o `/dev/ttyUSB0` en Linux).
4. Compila y carga el firmware con:
   ```bash
   pio run -t upload
   ```
5. Abre el monitor serial para comprobar que emite las tramas JSON:
   ```bash
   pio device monitor
   ```
*(Nota: Asegúrate de cerrar el monitor serial de PlatformIO antes de iniciar `mensajeria.py` en Python, para evitar conflictos de bloqueo exclusivo del puerto serial).*
