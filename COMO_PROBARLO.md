# Guía Práctica de Pruebas y Validación — COMPLEXNET

Esta guía describe el procedimiento paso a paso para comprobar el funcionamiento de COMPLEXNET, tanto en un solo computador (modo local) como en varios computadores conectados mediante la red inalámbrica ad hoc con hardware ESP32.

---

## 1. Opciones de Ejecución: Local vs Red Real

Antes de iniciar, elige el entorno de prueba:

* **Modo Local (Recomendado para desarrollo rápido):**
  Se ejecuta en un solo computador (Windows, Linux o macOS) abriendo varias terminales con la opción `--local`. No requiere tarjeta Wi-Fi en modo ad hoc ni permisos de superusuario.
* **Modo Red en Malla (Hardware real en laboratorio):**
  Se ejecuta en 2 o más computadores con Linux, configurados con `setup_adhoc.sh` o arrancados desde la memoria USB en vivo con `toram`.

---

## 2. Fase 1 — Comprobación de la Red en Malla (Solo modo real)

Si estás probando en computadores físicos con Linux y B.A.T.M.A.N. Advanced:

1. **Levantar la interfaz ad hoc en cada equipo:**
   ```bash
   sudo ./setup_adhoc.sh 1    # En el equipo 1 (IP 10.10.0.1)
   sudo ./setup_adhoc.sh 2    # En el equipo 2 (IP 10.10.0.2)
   ```
2. **Verificar que la interfaz virtual `bat0` existe:**
   ```bash
   ip -brief addr show bat0
   ```
   *Resultado esperado:* Debe mostrar `bat0 UP 10.10.0.X/24`.
3. **Verificar vecinos alcanzables directamente:**
   ```bash
   batctl meshif bat0 neighbors
   ```
   *Resultado esperado:* Debe listar las direcciones MAC de los equipos vecinos al alcance de radio directo.
4. **Verificar la tabla de originadores (rutas de la malla):**
   ```bash
   batctl meshif bat0 originators
   ```
   *Resultado esperado:* Lista todos los nodos de la red, indicando el siguiente salto y la métrica de calidad de enlace TQ (idealmente 255/255).
5. **Comprobar conectividad IP básica:**
   ```bash
   ping -c 3 10.10.0.2
   ```

---

## 3. Fase 2 — Inicio de Nodos y Descubrimiento Automático

### En modo local:
Abre tres terminales independientes dentro de la carpeta `complexnet-api/`:

* **Terminal 1 (Monitor de supervisión):**
  ```bash
  python applications/monitor.py --local
  ```
* **Terminal 2 (Nodo 1 — Baliza sensorial):**
  ```bash
  python applications/mensajeria.py --local --nombre nodo-01
  ```
* **Terminal 3 (Nodo 2 — Brigada de rescate):**
  ```bash
  python applications/mensajeria.py --local --nombre nodo-02
  ```

### En modo red real (laboratorio):
En cada computador, ejecuta simplemente:
```bash
sudo python3 applications/mensajeria.py
```
*(Y opcionalmente en una terminal secundaria: `python3 applications/monitor.py`)*

### Resultado esperado:
En cuestión de 2 a 5 segundos, cada consola mostrará:
```
>> entró nodo-02 en 10.10.0.2
```
Escribe `lista` en cualquier terminal para ver la tabla de vecinos activos y sus tiempos de último contacto.

---

## 4. Fase 3 — Lectura de Sensores Físicos (ESP32-S3)

1. Conecta la placa ESP32 mediante cable USB al computador donde corre `nodo-01`.
2. En la consola interactiva de `nodo-01`, escribe:
   ```
   sensor
   ```
3. **Salida esperada (con sensor físico conectado):**
   ```
   [Telemetria: esp32 (COM3 o /dev/ttyUSB0)]
     Temperatura:        24.2 °C
     Humedad del aire:   56.0 %
     Humedad de suelo:   14.2 %  (ADC: 3540 - Seco / Aire)
     Intensidad de luz:  185.0 lux
   ```
4. **Prueba de respuesta sensorial:**
   * **Luz:** Cubre el sensor BH1750 con la mano; al escribir `sensor` el valor caerá a `0.0 lux`. Alumbra con la linterna del teléfono y subirá a más de `2000.0 lux`.
   * **Suelo:** Con el sensor en seco reportará ~`3900` ADC (0-15%). Al introducirlo en un vaso con agua o tierra húmeda, el valor caerá hacia `1400-1800` ADC y el porcentaje subirá hacia 80-100%.

> Si no tienes la placa conectada, el sistema indicará `[Telemetria: simulada]` y entregará lecturas sintéticas estables.

---

## 5. Fase 4 — Simulación de Escenarios de Emergencia

Para verificar el comportamiento del sistema ante condiciones de peligro sin exponer los sensores físicos a fuego o inundaciones reales, se utiliza el comando `simular`:

```
simular incendio
sensor
```
*Salida:* Temperatura elevada (>45 °C) y humedad de aire extremadamente baja (<20%).

```
simular escombros
sensor
```
*Salida:* Iluminación nula (0.0 a 1.5 lux) con suelo y temperatura normales.

```
simular inundacion
sensor
```
*Salida:* Suelo saturado (>90%) con humedad atmosférica alta.

```
simular normal
sensor
```
*Salida:* Restablece condiciones ambientales templadas estándar.

---

## 6. Fase 5 — Inferencia Distribuida con Inteligencia Artificial

Para que la red clasifique el estado ambiental mediante el Árbol de Decisión CART:

1. Escribe en la consola:
   ```
   evaluar
   ```
2. **Proceso interno:**
   * El nodo emisor empaqueta su telemetría actual.
   * El planificador evalúa la función de aptitud `F(i, j)` sobre todos los nodos vecinos que ofrecen el servicio `clasificar_urgencia`.
   * Envía la petición por TCP al nodo seleccionado.
   * El nodo ejecutor procesa las reglas del árbol en sub-microsegundos y devuelve la respuesta.
3. **Salida esperada en condiciones normales:**
   ```
   ================ DIAGNOSTICO DE EMERGENCIA (IA) ================
   Clasificacion:       NORMAL_ESTABLE (91.3% confianza)
   Accion Recomendada:  Monitoreo perimetral rutinario. Sin riesgo inminente.
   Nodo Evaluador:      ea6fad2e (intentos: ea6fad2e)
   ================================================================
   ```
4. **Prueba combinada con simulación de desastres:**
   * Ejecuta `simular incendio` y luego `evaluar`:
     * Diagnóstico: `ALERTA_INCENDIO (100.0% confianza)`
     * Acción: *EVACUACION INMEDIATA. Despacho urgente de brigada contra incendios y cortafuegos.*
   * Ejecuta `simular escombros` y luego `evaluar`:
     * Diagnóstico: `POSIBLE_ATRAPADO_ESCOMBROS (100.0% confianza)`
     * Acción: *RESCATE USAR PRIORITARIO. Despachar equipo de busqueda canina y remocion de escombros.*

---

## 7. Fase 6 — Vigilancia Continua y Alertas Multicast

Para mantener monitoreo desatendido en el perímetro de rescate:

1. Asegúrate de tener abierto `applications/monitor.py` en una terminal.
2. En la terminal del nodo sensor, activa la vigilancia periódica (por ejemplo, cada 3 segundos):
   ```
   vigilancia 3
   ```
3. El nodo leerá los sensores cada 3 segundos y solicitará evaluación a la red.
4. Mientras el entorno sea normal, no se genera tráfico innecesario.
5. Inyecta una emergencia (p. ej. en otra terminal escribe `simular incendio` o cubre totalmente el sensor de luz):
   * En la terminal del nodo sensor aparecerá la advertencia de disparo.
   * En la pantalla del **monitor**, la alerta crítica se proyectará inmediatamente en **color rojo**, indicando la clasificación y el nodo origen.
6. Para detener el ciclo de vigilancia, presiona `Enter` en la consola.

---

## 8. Fase 7 — Mensajería y Grupos Temáticos

1. **Mensaje a toda la malla (Broadcast UDP):**
   ```
   todos Aviso a todas las unidades de campo
   ```
   *Aparece en todas las terminales activas de la red.*

2. **Mensaje directo punto a punto (TCP Unicast):**
   ```
   msg nodo-02 Verificando estado de bateria
   ```
   *Llega exclusivamente a `nodo-02` con confirmación de entrega.*

3. **Comunicación por grupos (Multicast):**
   * En `nodo-02`, suscríbete al grupo de rescate:
     ```
     unir rescate
     ```
   * En `nodo-01`, envía un mensaje al grupo:
     ```
     grupo rescate Brigada alfa en posicion
     ```
   * `nodo-02` recibe el mensaje. Si hubiera un `nodo-03` que no se ha unido al grupo `rescate`, descartará el mensaje a nivel de aplicación.

---

## 9. Fase 8 — Cómputo Colaborativo y Balanceo de Carga

1. **Cálculo matemático seguro (`calc`):**
   ```
   calc (50 * 4) + sqrt(144)
   ```
   *El planificador asigna la operación al mejor nodo según `F(i, j)`. El nodo ejecutor evalúa la expresión mediante análisis de sintaxis abstracta (AST seguro, sin `eval`) y retorna `212.0`.*

2. **Estrés de carga computacional (`estres`):**
   ```
   estres 10 4
   ```
   *Reparte 4 tareas de consumo intensivo de CPU (durante 10 s cada una) entre los nodos disponibles en la red. Si observas la pantalla de `monitor.py`, verás reflejado el incremento de carga y cómo las siguientes tareas evitan a los nodos saturados.*

---

## 10. Fase 9 — Tolerancia a Fallos y Reasignación

Esta prueba verifica que las tareas sobreviven a la desconexión o muerte de un nodo ejecutor:

### Verificación mediante suite automatizada (100% reproducible):
Ejecuta la prueba que simula la caída del nodo ejecutor en medio de una inferencia de IA:
```bash
cd complexnet-api
python -m pytest tests/test_ia_urgencias.py -k "reasignacion" -v
```
*Resultado:* La prueba inicia 2 nodos, envía una tarea de IA al nodo 2, apaga abruptamente el nodo 2 antes de que responda, y comprueba que el `GestorRecuperacion` reasigna la tarea al nodo local completando el diagnóstico exitosamente.

### Verificación en red activa:
1. Con 2 o más nodos corriendo, lanza una tarea de estrés prolongada: `estres 30 2`.
2. Cierra inmediatamente la terminal de uno de los nodos ejecutores (simulando corte de energía).
3. A los 15 segundos el nodo restante lo marcará como `SOSPECHOSO`, a los 30 segundos como `INACTIVO`, y la tarea huérfana será rescatada y completada.

---

## 11. Fase 10 — Inspección de Paquetes en Tránsito

Para verificar que los mensajes viajan realmente por la interfaz de red y comprobar su estructura:

1. **Inspeccionar tramas de descubrimiento y latidos (UDP puerto 5000):**
   ```bash
   sudo tcpdump -i bat0 -A -n udp port 5000
   ```
   *Verás pasar en texto claro las tramas JSON con encabezados de secuencia y relojes de Lamport (`HEARTBEAT` y `RESOURCE_UPDATE`).*

2. **Inspeccionar tareas y mensajes directos (TCP puerto 5001):**
   ```bash
   sudo tcpdump -i bat0 -A -n tcp port 5001
   ```

3. **Inspección visual con Wireshark:**
   Abre Wireshark sobre la interfaz `bat0` y aplica el filtro:
   `udp.port == 5000 || tcp.port == 5001`

---

## 12. Fase 11 — Ejecución de Pruebas Automatizadas por Grupos

El framework cuenta con 128 pruebas automatizadas. Para ejecutarlas de manera ordenada y reproducible:

### A. Pruebas Unitarias de Algoritmos y Lógica (100% reproducibles en cualquier SO)
No dependen de la red ni de sockets externos; validan matemáticas, seguridad AST, reglas del árbol y planificación:

```bash
cd complexnet-api

# 1. Operaciones matematicas seguras (AST, funciones, primos, prevencion de inyeccion de codigo) - 29 pruebas
python -m pytest tests/test_operaciones.py -v

# 2. Inteligencia Artificial (clasificador CART, inferencia local y tolerancia a fallos) - 3 pruebas
python -m pytest tests/test_ia_urgencias.py -v

# 3. Logica del Planificador F(i,j) y vector de recursos - 11 pruebas unitarias
python -m pytest tests/test_tareas.py -k "formula or aptitud or disponibilidad or carga or reputacion" -v

# 4. Seguridad de archivos (bombas de compresion zlib, hashes SHA-256 y corrupcion) - 8 pruebas unitarias
python -m pytest tests/test_archivos.py -k "rechaza or bomba or huella" -v
```

### B. Medición de Tiempos de Inferencia (Benchmark CPU)
Para medir con precisión estadística el tiempo de inferencia del árbol CART en microsegundos sobre tu procesador:

```bash
python scripts/benchmark_ia.py
```
*Ejecuta 20,000 inferencias con calentamiento y reporta el promedio, mediana, mínimo y máximo en microsegundos.*

### C. Pruebas de Integración y Malla Inalámbrica (Entorno Linux / ad hoc)
Validan la convergencia de paquetes de difusión UDP (`127.255.255.255` o `bat0`) y el enrutamiento multi-nodo:

```bash
# Requiere Linux con interfaz de loopback lo o interfaz de malla bat0
python -m pytest tests/test_comunicacion.py tests/test_descubrimiento.py tests/test_integracion.py -v
```
*(Nota técnica: En Windows, Microsoft Winsock restringe la difusión UDP en loopback, por lo que estas pruebas de sockets de red deben ejecutarse en Linux, en WSL2 o en la red real ad hoc).*

---

## 13. Resolución de Problemas Frecuentes

| Síntoma | Causa Probable | Solución |
|---|---|---|
| `bat0: No such device` | No se ha cargado el módulo de kernel de batman-adv. | Ejecuta `sudo modprobe batman-adv`. Si no existe el módulo, revisa `PREPARAR_USB.md` para instalar `linux-modules-extra`. |
| `batctl originators` aparece vacío | Los paquetes de anuncio (OGM) tardan unos segundos en converger. | Espera 10 a 15 segundos con las interfaces Wi-Fi encendidas. Verifica que todos los equipos usen el mismo SSID y canal (`COMPLEXNET`, canal 1). |
| `PermissionError: COM3` o `/dev/ttyUSB0` | El monitor serial de PlatformIO / Arduino IDE tiene abierto el puerto exclusivamente. | Cierra el monitor serie en VS Code o cualquier programa que esté leyendo la ESP32. En Linux, añade tu usuario al grupo dialout: `sudo usermod -aG dialout $USER`. |
| Los nodos no se ven en la mensajería | La difusión UDP está saliendo por una interfaz de red equivocada. | Asegúrate de pasar la interfaz correspondiente (en red real: `bat0`, en modo local: `--local`). |
| `Address already in use` | Se intentó iniciar dos nodos con el mismo puerto TCP en la misma máquina. | Asigna puertos TCP distintos con `--puerto-tcp 5002` o utiliza `--local`, que gestiona puertos automáticamente. |
