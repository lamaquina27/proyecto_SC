<p align="center">
  <img src="complexnet-api/LOGO.jpg" alt="ComplexNet API" width="340">
</p>

# COMPLEXNET
### Sistema Descentralizado de Monitoreo Ambiental, Telemetría y Alerta Temprana sobre Redes Ad hoc

COMPLEXNET es una plataforma de software y hardware abierta diseñada para operar en **zonas de emergencia y desastres naturales** (terremotos, inundaciones, deslizamientos de tierra o incendios) donde la infraestructura convencional de comunicaciones (redes celulares, internet, fibra óptica y tendido eléctrico) queda inoperativa.

El sistema combina **microcontroladores ESP32 con sensores ambientales** y **computadores portátiles conectados en una red mallada inalámbrica (ad hoc)**, logrando que los equipos se descubran entre sí, compartan telemetría, se distribuyan tareas computacionales y evalúen riesgos en tiempo real mediante **inteligencia artificial explicable**, sin depender de ningún servidor central o conexión a internet.

---

## 1. Presentación del Proyecto

### ¿Qué problema aborda?
En las primeras horas tras un desastre natural, la falta de información y la pérdida de telecomunicaciones retrasan la respuesta de los equipos de rescate. Instalar infraestructura provisional (torres celulares o enlaces satelitales) requiere tiempo y recursos que no siempre están disponibles de inmediato.

### ¿Cuál es la propuesta de COMPLEXNET?
Aprovechar el hardware que los brigadistas ya transportan (computadores portátiles, placas de desarrollo compactas como la ESP32 y sensores de bajo costo) para crear una **red de campo autónoma**:
* **Descentralizada:** No hay un nodo maestro. Si un equipo se apaga o se aleja de la zona, los demás continúan operando sin interrupción.
* **Autoorganizada:** Los nodos detectan automáticamente a sus vecinos por proximidad Wi-Fi.
* **Inteligente en el borde:** Clasifica condiciones de peligro mediante un modelo de aprendizaje automático diseñado para ejecutarse localmente en sub-milisegundos.

---

## 2. Cómo Funciona: Del Sensor a la Alerta

El flujo de información en COMPLEXNET abarca desde la captura física hasta la notificación en pantalla:

```
 [Entorno Físico]
        │  (Temperatura, Humedad de aire, Humedad de suelo, Luminosidad)
        ▼
 ┌──────────────┐
 │   ESP32-S3   │  Captura analógica/digital, calibración y empaquetado JSON
 └──────┬───────┘
        │  (Puerto Serial / USB a 115200 baudios)
        ▼
 ┌──────────────┐
 │ Nodo Pasarela│  Aplicación de mensajería lee telemetría de campo
 └──────┬───────┘
        │  (Malla inalámbrica Wi-Fi ad hoc + B.A.T.M.A.N. Advanced)
        ▼
 ┌──────────────┐
 │ Planificador │  Calcula aptitud F(i,j) y selecciona el mejor nodo disponible
 └──────┬───────┘
        │  (Envío directo por TCP enmarcado)
        ▼
 ┌──────────────┐
 │ Clasificador │  Árbol de Decisión CART procesa la telemetría (< 0.001 ms)
 │     (IA)     │  Diagnóstico: NORMAL, INCENDIO, INUNDACIÓN, ESCOMBROS o CALOR
 └──────┬───────┘
        │  (Canal Multicast UDP 'rescate')
        ▼
 ┌──────────────┐
 │   Monitor    │  Pantalla de supervisión proyecta la alerta en color rojo
 └──────────────┘
```

1. **Captura:** La placa ESP32 lee los 4 sensores cada 2 segundos y emite una trama JSON estructurada por el puerto serial.
2. **Recepción en el nodo:** El computador conectado a la ESP32 recibe la lectura mediante el módulo `sensor_emergencia.py`. Si no hay hardware conectado, se activa automáticamente un generador de telemetría simulada.
3. **Distribución:** Al solicitar un diagnóstico (`evaluar` o `vigilancia`), el nodo consulta su tabla de vecinos y selecciona al nodo con mejores recursos mediante una función de aptitud.
4. **Inferencia:** El nodo seleccionado ejecuta el Árbol de Decisión CART sobre los datos y devuelve el diagnóstico y nivel de confianza.
5. **Notificación:** Si se detecta una condición crítica, se emite un mensaje al grupo de difusión `"rescate"`, alertando inmediatamente a todas las terminales de supervisión.

---

## 3. Hardware Utilizado y Conexiones

La baliza sensorial física utiliza un microcontrolador de bajo consumo y tres módulos de sensado ambiental:

| Componente | Modelo | Parámetro que Mide | Rango / Características | Interfaz / Pin ESP32 |
|---|---|---|---|---|
| **Microcontrolador** | ESP32-S3 N16R8 | Procesamiento y telemetría | Dual-Core 240 MHz, 16MB Flash, 8MB PSRAM | Puerto USB (Serial 115200 bps) |
| **Sensor de Ambiente** | DHT11 | Temperatura y Humedad del aire | 0 a 50 °C (±2 °C) / 20 a 90% RH (±5%) | Señal Digital: **GPIO 4** |
| **Sensor de Suelo** | Capacitivo v2.0 | Humedad del terreno / lodo | Voltaje analógico proporcional inverso | Entrada Analógica: **GPIO 5** (ADC 12 bits) |
| **Sensor de Luz** | GY-302 (BH1750) | Iluminación ambiente | 1 a 65,535 lux (resolución 1 lux) | Bus I2C: **SDA GPIO 8**, **SCL GPIO 9** (0x23) |

```
                       ESP32-S3 N16R8
                   ┌───────────────────┐
      DHT11 (DATA) ┤ GPIO 4            │
      SUELO (AOUT) ┤ GPIO 5            │
       BH1750(SDA) ┤ GPIO 8            │
       BH1750(SCL) ┤ GPIO 9            │
                   │               GND ┼─── Línea común de tierra
                   │               3V3 ┼─── Alimentación de sensores (3.3V)
                   │        [USB-UART] ┼═══ Cable USB al Computador
                   └───────────────────┘
```

> **Calibración del sensor de suelo:** El sensor capacitivo entrega valores ADC de 12 bits (rango 0 a 4095). En aire seco reporta valores cercanos a `3900` (humedad 0%), mientras que sumergido en agua reporta alrededor de `1400` (humedad 100%). La conversión a porcentaje se realiza aplicando:
>
> $$\text{Humedad (\%)} = \frac{3900 - \text{ADC}}{3900 - 1400} \times 100$$

---

## 4. Arquitectura Distribuida y Red en Malla

El sistema no utiliza clientes ni servidores fijos. Cada computador ejecuta una instancia de la clase `Nodo`, la cual opera de forma simétrica:

```
  ┌──────────────────────────────────────────────────────────────┐
  │                        APLICACIONES                          │
  │     mensajeria.py   ·   monitor.py   ·   operaciones.py      │
  ├──────────────────────────────────────────────────────────────┤
  │                 API DE ALTO NIVEL (Nodo)                     │
  │   enviar_mensaje() · difundir() · enviar_tarea_async()       │
  ├──────────────────────────────────────────────────────────────┤
  │                    SERVICIOS DISTRIBUIDOS                    │
  │  Descubrimiento  ·  Gestor Recursos  ·  Planificador F(i,j)  │
  │  Detector Fallos ·  Gestor Tareas    ·  Registro Eventos     │
  ├──────────────────────────────────────────────────────────────┤
  │                 COMUNICACIÓN Y TRANSPORTE                    │
  │      UDP (broadcast / multicast)   ·   TCP (enmarcado 4B)    │
  ├──────────────────────────────────────────────────────────────┤
  │                 RED EN MALLA (Capa 2 Linux)                  │
  │            B.A.T.M.A.N. Advanced (interfaz bat0)             │
  │                 Wi-Fi en modo ad hoc (IBSS)                  │
  └──────────────────────────────────────────────────────────────┘
```

### Protocolo de Red: B.A.T.M.A.N. Advanced
En lugar de enrutar paquetes en capa 3 con tablas estáticas, se emplea **B.A.T.M.A.N. Advanced** (*Better Approach To Mobile Adhoc Networking*), un módulo del kernel de Linux que crea un conmutador virtual ethernet (`bat0`) sobre interfaces Wi-Fi en modo ad hoc (IBSS):
* Cada nodo propaga paquetes de anuncio de origen (OGM) para medir la calidad del enlace ($TQ$, 0 a 255).
* Los nodos retransmiten automáticamente los paquetes entre sí si el destino no está al alcance de radio directo (enrutamiento multi-salto transparente).

### Planificación y Asignación de Tareas: Función de Aptitud
Cuando un nodo necesita delegar una tarea computacional (como clasificar una emergencia o resolver un cálculo), evalúa a todos sus vecinos activos mediante una función de aptitud multi-criterio:

$$F(i, j) = w_1 \cdot C_i + w_2 \cdot M_i + w_3 \cdot B_i + w_4 \cdot R_i - w_5 \cdot L_i$$

Donde:
* **$C_i$**: Capacidad de CPU libre ($1.0 - \text{carga\_cpu}$).
* **$M_i$**: Memoria RAM libre disponible.
* **$B_i$**: Calidad del enlace inalámbrico ($TQ / 255$).
* **$R_i$**: Confiabilidad histórica de tareas exitosas.
* **$L_i$**: Carga de tareas actualmente en ejecución en ese nodo.

El nodo con mayor valor $F(i, j)$ recibe la tarea por una conexión TCP directa.

---

## 5. Inteligencia Artificial: Clasificador de Emergencias

Para la toma de decisiones en campo, se implementó un **Árbol de Decisión CART** (Classification and Regression Trees) nativo.

### Variables de Entrada
El modelo recibe 4 variables numéricas normalizadas por lectura:
1. `temperatura` (°C): Temperatura ambiente detectada por el DHT11.
2. `humedad_aire` (%): Humedad relativa del aire detectada por el DHT11.
3. `suelo` (%): Humedad del terreno calibrada desde el sensor capacitivo.
4. `luz` (lux): Iluminación superficial leída por el BH1750.

### Categorías de Diagnóstico

| Diagnóstico | Condiciones Típicas de Activación | Acción Recomendada por el Sistema |
|---|---|---|
| `NORMAL_ESTABLE` | Temperatura 15-32 °C, humedad 40-70%, iluminación ambiental normal | Monitoreo perimetral rutinario sin riesgo. |
| `ALERTA_INCENDIO` | Humedad de aire $\le 24.4\%$, temperatura elevada | Evacuación preventiva y despacho de brigada forestal. |
| `ALERTA_INUNDACION_LODO` | Humedad de suelo $> 84.8\%$ con humedad atmosférica alta | Riesgo de alud o desbordamiento; evacuar a cota alta. |
| `POSIBLE_ATRAPADO_ESCOMBROS` | Iluminación extrema baja ($\le 2.75\text{ lux}$) con suelo no saturado | Prioridad de búsqueda canina en zona de derrumbe. |
| `ALERTA_CALOR_EXTREMO` | Temperatura $> 36.3 °C$ con aire seco | Hidratación obligatoria y rotación de brigadistas. |

### ¿Por qué se eligió un Árbol de Decisión?
1. **Explicabilidad (XAI):** En situaciones de emergencia, un diagnóstico no puede provenir de una "caja negra" incomprensible. El árbol genera reglas lógicas directas que los rescatistas pueden auditar e inspeccionar.
2. **Cero Dependencias en RAM:** El modelo se entrena con un script offline (`entrenar_arbol.py`) usando el criterio de impureza de Gini y se exporta como funciones condicionales nativas en Python. No requiere librerías pesadas como `scikit-learn`, `torch` ni `tensorflow`, lo que permite cargarlo en sistemas efímeros en RAM.
3. **Velocidad de Inferencia:** La evaluación completa toma **menos de 0.001 ms (sub-microsegundo)** en un procesador estándar, consumiendo recursos mínimos.

### Métricas de Evaluación (Datos Sintéticos)
Evaluado sobre un conjunto de prueba independiente de **400 muestras sintéticas** (partición 80/20 sobre 2,000 registros sintéticos calibrados según rangos físicos de desastre):
* **Exactitud Global (Accuracy):** **97.50%** (390 de 400 aciertos).
* **F1-Score por Clase:**
  * Incendio: **1.000**
  * Inundación / Lodo: **0.993**
  * Calor Extremo: **0.974**
  * Escombros: **0.969**
  * Normal: **0.944**

> **Aviso de Rigor Metodológico:** La exactitud reportada fue obtenida estrictamente sobre el dataset sintético (`scripts/dataset_emergencias.csv`) para verificar la convergencia del algoritmo inductivo CART. **No representa una validación en escenarios reales de desastre**, donde factores físicos no modelados pueden afectar la clasificación.

* **Benchmark de Inferencia en CPU (Reproducible):**
  Medido mediante `scripts/benchmark_ia.py` (20,000 evaluaciones con calentamiento previo en Python 3.11):
  * Inferencia pura directa en árbol (`_evaluar_arbol`): **0.0003 ms (0.3 µs)**
  * Inferencia con validación y diccionario (`clasificar_urgencia`): **0.0013 ms (1.3 µs)**
  * *Para reproducir la medición en tu equipo:* `python scripts/benchmark_ia.py`

*(El reporte de métricas y la matriz de confusión pueden consultarse en [`complexnet-api/docs/metricas_arbol_decision.txt`](complexnet-api/docs/metricas_arbol_decision.txt) y el informe experimental en [`complexnet-api/docs/informe_experimental_corte3.md`](complexnet-api/docs/informe_experimental_corte3.md)).*

---

## 6. Modo Real y Modo Simulado

Para facilitar el desarrollo y permitir pruebas completas cuando no se cuenta con sensores físicos en cada equipo, el módulo `sensor_emergencia.py` incorpora detección automática:

### Modo Real (Hardware Detectado)
* Al iniciar, el sistema busca puertos seriales disponibles (`COM*` en Windows, `/dev/ttyUSB*` o `/dev/ttyACM*` en Linux).
* Al encontrar la ESP32 enviando tramas JSON válidas, inicia un hilo de lectura continuo a 115200 baudios.
* La telemetría leída se etiqueta con fuente `hardware`.

### Modo Simulado (Fallback Automático)
* Si la ESP32 no está conectada o no se dispone del módulo `pyserial`, el sistema **no se detiene**: cambia de forma transparente al generador de telemetría simulada.
* Permite inyectar escenarios de desastre controlados mediante comandos de consola:
  * `simular incendio`: Genera valores con temperatura alta y aire seco.
  * `simular inundacion`: Genera suelo saturado de agua.
  * `simular escombros`: Genera oscuridad total ($\le 2\text{ lux}$) con suelo seco.
  * `simular calor`: Genera temperatura elevada con humedad media.
  * `simular normal`: Restablece lecturas ambientales estándar.

---

## 7. Instalación y Ejecución

### Opción 1: Pruebas Locales (Un solo computador)
Permite verificar la comunicación, la asignación de tareas y la IA en Windows, Linux o macOS abriendo múltiples terminales.

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/lamaquina27/proyecto_SC.git
   cd proyecto_SC/complexnet-api
   ```
2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt pyserial
   ```
3. **Terminal 1 — Panel de Monitoreo:**
   ```bash
   python applications/monitor.py --local
   ```
4. **Terminal 2 — Nodo Sensor (conecta tu ESP32 o usa simulación):**
   ```bash
   python applications/mensajeria.py --local --nombre nodo-sensor
   ```
5. **Terminal 3 — Nodo Evaluador / Brigada:**
   ```bash
   python applications/mensajeria.py --local --nombre nodo-brigada
   ```

---

### Opción 2: Red Real en Laboratorio (Ubuntu Live USB con `toram`)

En computadores físicos de laboratorio que arrancan desde una memoria USB con Ubuntu 24.04:

1. **Preparar la USB desde Windows:**
   ```powershell
   cd C:\Users\moral\Downloads\proyecto_SC
   powershell -ExecutionPolicy Bypass -File .\preparar_usb.ps1 -Unidad E:
   ```
2. **Iniciar cada computador:**
   * Arrancar el PC desde la USB y presionar `e` en el menú GRUB para añadir el parámetro `toram`.
   * Identificar la ruta donde quedó montada la USB:
     * Si está en el medio de instalación en vivo: `/cdrom/complexnet/arrancar_nodo.sh`
     * Si el sistema de ventanas la montó por etiqueta: `/media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh`
   * En el Computador 1 (con la ESP32 conectada por USB):
     ```bash
     sudo bash /cdrom/complexnet/arrancar_nodo.sh 1
     ```
   * En el Computador 2:
     ```bash
     sudo bash /cdrom/complexnet/arrancar_nodo.sh 2
     ```
   * *(El script copia el proyecto a la memoria RAM `/opt/complexnet`, desmonta la USB para llevarla al siguiente equipo, configura `bat0` en `10.10.0.N` y levanta la consola).*

Para instrucciones exhaustivas de preparación de la memoria USB, consulta [`PREPARAR_USB.md`](PREPARAR_USB.md).

---

## 8. Pruebas y Demostración

Una vez iniciada la consola interactiva `mensajeria.py`, los siguientes comandos permiten demostrar las capacidades del sistema:

### Comandos de Telemetría e Inteligencia Artificial
* `sensor`: Muestra la última lectura capturada de los sensores (temperatura, humedad de aire, humedad de suelo y luminosidad).
* `evaluar`: Toma la lectura actual y la envía a la red; el planificador elige al mejor nodo de cómputo para evaluarla con el árbol CART y devuelve el diagnóstico:
  ```
  ================ DIAGNOSTICO DE EMERGENCIA (IA) ================
  Clasificacion:       NORMAL_ESTABLE (91.3% confianza)
  Accion Recomendada:  Monitoreo perimetral rutinario. Sin riesgo inminente.
  Nodo Evaluador:      ea6fad2e (intentos: ea6fad2e)
  ================================================================
  ```
* `simular escombros` y luego `evaluar`: Diagnostica `POSIBLE_ATRAPADO_ESCOMBROS (100.0% confianza)`.
* `vigilancia 3`: Monitoreo perimetral continuo cada 3 segundos. Si se detecta una emergencia grave, emite una alerta multicast que pinta la advertencia en rojo en `monitor.py`.

### Comandos de Comunicación y Cómputo Distribuido
* `lista`: Lista los vecinos detectados en la malla, su IP y estado.
* `todos <mensaje>`: Envío broadcast a toda la red ad hoc.
* `msg <nodo> <mensaje>`: Mensaje privado unicast por TCP.
* `unir rescate`: Se suscribe al grupo temático `"rescate"`.
* `grupo rescate <alerta>`: Envía mensaje filtrado solo a miembros del grupo.
* `calc (10 + 20) * 2`: Resuelve una expresión matemática delegándola al nodo con mejor $F(i, j)$.
* `estres 15 4`: Genera 4 subprocesos de carga de CPU repartidos entre los nodos activos.

Para un recorrido detallado paso a paso de cada verificación, consulta [`COMO_PROBARLO.md`](COMO_PROBARLO.md).

---

## 9. Resultados Validados y Limitaciones Actuales

Para mantener total transparencia técnica, se diferencian claramente los resultados validados en hardware de las limitaciones del sistema:

### Lo que ha sido comprobado en pruebas físicas:
1. **Lectura física de sensores:** La ESP32-S3 lee de forma continua los 4 sensores (DHT11, sensor capacitivo y BH1750) y los entrega mediante puerto serial al computador conectado.
2. **Intercambiabilidad de hardware:** Conectar físicamente la ESP32 a cualquiera de los dos computadores probados funciona sin requerir reconfiguración de software.
3. **Malla B.A.T.M.A.N. entre dos computadores:** Dos computadores portátiles con Ubuntu se enlazan en modo ad hoc (`bat0`), reconociéndose como vecinos en `batctl meshif bat0 neighbors` con métrica de calidad de enlace $TQ = 255/255$.
4. **Transporte de red bajo estrés:** Prueba de carga con 494 mensajes enviados y 502 recibidos, con 0 descartados y 0 fallos de transporte.
5. **Comportamiento ante luz variable:** Comprobado físicamente con mediciones en oscuridad total, luz ambiente interior (~150-200 lux) y linterna directa (>2000 lux).
6. **Inferencia de IA en sub-milisegundo:** Verificado mediante `time.perf_counter()` con tiempos de ejecución de ~0.0008 ms por inferencia.

### Limitaciones conocidas y aspectos por mejorar:
1. **Detección de escombros basada en luz:** La regla `luz <= 2.75 lux` fue deducida a partir de datos sintéticos donde el enterramiento bajo escombros implica oscuridad. En un entorno físico real, **estar en un cuarto oscuro, de noche o tapar el sensor con la mano dispara esta alerta**. La oscuridad es un indicio de confinamiento, pero no constituye prueba de vida humana atrapada. En versiones futuras debe combinarse con sensores de vibración, micrófonos acústicos o sensores de CO2.
2. **Dependencia de calibración del suelo:** La humedad del suelo depende del tipo de sustrato (arena, tierra negra o escombros). Si los umbrales de referencia `3900` y `1400` varían por salinidad o tipo de terreno, la conversión a porcentaje requerirá recalibración previa.
3. **Topologías de más de 2 nodos físicos:** La arquitectura y el planificador están diseñados para $N$ nodos y han sido validados con 3 nodos en entornos automatizados e integración local. Las pruebas físicas de campo hasta la fecha se realizaron con 2 computadores y 1 baliza ESP32.
4. **Tolerancia a fallos ante apagado abrupto:** La reasignación automática de tareas huérfanas ante la caída de un nodo está implementada y aprobada en las suites de pruebas unitarias (`test_ia_urgencias.py`, `test_tareas.py`); su validación ante el apagado físico repentino de un portátil durante una inferencia en vivo en la malla real sigue en proceso de homologación.

---

## 10. Estructura del Repositorio

```
proyecto_SC/
├── README.md                      # Documento principal del proyecto
├── COMO_PROBARLO.md               # Guía práctica paso a paso de pruebas y comandos
├── PREPARAR_USB.md                # Manual para preparar la USB booteable con toram
├── preparar_usb.ps1               # Script PowerShell para sincronizar la memoria USB
├── arrancar_nodo.sh               # Script de arranque del nodo en Linux / toram
├── setup_adhoc.sh                 # Configuración de interfaces Wi-Fi y batman-adv
│
├── firmware_esp32/                # Código fuente C++ / PlatformIO para la baliza ESP32
│   ├── platformio.ini             # Configuración de placa ESP32-S3 y librerías
│   ├── README.md                  # Guía de conexiones y flasheo
│   └── src/main.cpp               # Firmware que lee los sensores y emite JSON
│
└── complexnet-api/
    ├── README.md                  # Documentación técnica de la biblioteca API en Python
    ├── requirements.txt           # Dependencias básicas (psutil, pytest, pyserial)
    │
    ├── applications/              # Aplicaciones de usuario y demostración
    │   ├── mensajeria.py          # Consola interactiva de brigada y comandos de campo
    │   ├── monitor.py             # Panel de supervisión visual en tiempo real
    │   ├── sensor_emergencia.py   # Lector USB de ESP32 y simulador de telemetría
    │   ├── arbol_decision.py      # Motor de IA: Clasificador de urgencias (CART nativo)
    │   └── operaciones.py         # Operaciones matemáticas seguras y estrés de CPU
    │
    ├── src/                       # Núcleo modular de ComplexNet (Capas 2, 3 y 4)
    │   ├── api/nodo.py            # Fachada principal y ciclo de vida del nodo
    │   ├── communication/         # Sockets UDP/TCP, compresión zlib y enmarcado
    │   ├── discovery/             # Descubrimiento de vecinos y detector de fallos
    │   ├── resources/             # Monitoreo del vector de estado [C, M, B, R, A]
    │   ├── scheduler/             # Planificador distribuido y optimización F(i,j)
    │   ├── tasks/                 # Máquina de estados de tareas y reasignación
    │   └── monitoring/            # Registro distribuido JSONL y relojes de Lamport
    │
    ├── scripts/                   # Herramientas de entrenamiento y benchmark
    │   ├── entrenar_arbol.py      # Algoritmo CART desde cero (Gini e inferencia)
    │   ├── benchmark_ia.py        # Medición reproducible de tiempos de inferencia
    │   └── dataset_emergencias.csv# Dataset con 2,000 muestras para entrenamiento
    │
    ├── tests/                     # Suite de 128 pruebas automatizadas
    │   ├── test_ia_urgencias.py   # Pruebas de la IA distribuida y tolerancia a fallos
    │   ├── test_operaciones.py    # Pruebas de cálculo seguro AST y estrés CPU
    │   ├── test_tareas.py         # Pruebas del planificador y reasignación
    │   ├── test_archivos.py       # Pruebas de envío y compresión zlib
    │   ├── test_comunicacion.py   # Pruebas de transporte y protocolo
    │   └── test_integracion.py    # Pruebas de interacción entre múltiples nodos
    │
    ├── experimentos/              # Scripts y resultados de pruebas de red y estrés
    │   ├── medir.py               # Herramienta de medición de latencia y tráfico
    │   └── graficas.py            # Generador de curvas de desempeño
    │
    └── docs/                      # Documentación complementaria y reportes
        ├── manual_desarrollador.md# Guía para extender la API con nuevas operaciones
        ├── diseno.md              # Registro de 29 decisiones arquitectónicas
        ├── metricas_arbol_decision.txt # Reporte numérico de evaluación del árbol
        └── benchmark_ia.txt       # Resultados del benchmark reproducible en CPU
```

---

## Licencia y Créditos
Desarrollado como proyecto de investigación aplicada en redes inalámbricas descentralizadas y computación en el borde por **Felipe Morales Robelto** y **Juan David Sánchez Vargas**.
