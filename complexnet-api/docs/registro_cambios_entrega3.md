# Registro de Cambios y Plan de Implementación - Entrega 3 (Corte 3)
**Proyecto:** ComplexNet API - Framework para Computación Descentralizada sobre Redes Ad hoc  
**Escenario:** Comunicación y Procesamiento en Zonas de Desastre y Emergencias  
**Autores:** Felipe Morales Robelto y Juan David Sánchez Vargas  
**Fecha de Registro:** 2026-11-20  

---

## 1. Estado Actual del Sistema (Lo que se tiene)

### 1.1 Núcleo de Red y Servicios (`src/`)
* **Capa 1 (Ad hoc):** Interfaz `bat0` gestionada mediante B.A.T.M.A.N. Advanced en Linux / Wi-Fi IBSS. Modo `--local` en loopback (`127.255.255.255`) para pruebas en Windows o máquinas sin tarjeta ad hoc.
* **Capa 2 (Comunicación):** 
  * Transporte UDP para mensajes frecuentes y anuncios de red (control de MTU < 1400 bytes).
  * Transporte TCP con enmarcado por longitud (4 bytes iniciales) y reintentos para tareas y mensajes grandes.
  * Transferencia de archivos en trozos con hash SHA-256 y compresión zlib adaptativa.
* **Capa 3 (Servicios Distribuidos):**
  * Descubrimiento de nodos (`HELLO`, `HELLO_ACK`, `HEARTBEAT`).
  * Vigilancia de fallos con dos umbrales: 15 s (`SOSPECHOSO`) y 30 s (`INACTIVO`).
  * Anuncio y actualización periódica del vector de recursos: $S_i(t) = [C_i, M_i, B_i, R_i, A_i]$.
  * Planificador distribuido basado en la función de aptitud:
    $$F(i, j) = w_1 C_i + w_2 M_i + w_3 B_i + w_4 R_i - w_5 L_i$$
  * Gestor de tareas con colas y reasignación automática ante caídas de nodos ejecutores (`GestorRecuperacion`).
* **Capa 4 (API de Alto Nivel):** Fachada `Nodo` que abstrae el manejo de sockets, puertos y protocolos hacia aplicaciones descentralizadas.

### 1.2 Aplicaciones Existentes (`applications/`)
* `mensajeria.py`: Chat descentralizado por terminal, soporte de grupos multicast, transferencia de archivos y ejecución de tareas distribuidas (`calc`, `estres`).
* `operaciones.py`: Intérprete matemático seguro con `ast` (`calcular`) y generador de estrés de CPU con procesos (`estresar`).
* `monitor.py`: Panel en vivo de estado de nodos, tareas en curso y recursos en consola.

### 1.3 Estado del Hardware ESP32 (`Planta_Inteligente/`)
* Microcontrolador ESP32 S3 con 4 sensores conectados:
  * DHT11: Temperatura y Humedad del aire (Pin GPIO 4).
  * Sensor de Humedad de suelo: Lectura analógica ADC (Pin GPIO 5).
  * GY-302 (BH1750): Intensidad lumínica por I2C (SDA Pin 8, SCL Pin 9).
* Salida actual: Imprime texto plano con encabezados y etiquetas humanas por Serial a 115200 baudios.

---

## 2. Diagnóstico de lo que Falta para la Entrega 3 (Según Rúbrica Oficial)

1. **Aplicación de Inteligencia Artificial (Aplicación 3):**
   * Se requiere integrar un modelo formal de IA. La rúbrica autoriza: *Regresión Lineal, Regresión Logística, SVM, Árbol de Decisión o MLP*.
   * Debe justificar los 5 puntos: distribución de datos/tareas, asignación con $F(i,j)$, mensajes intercambiados, tolerancia a fallos y métricas.
2. **Aplicación de Monitoreo Distribuido (Aplicación 1):**
   * Monitoreo de variables físicas en red descentralizada y sistema distribuido de alertas.
3. **Métricas Experimentales:**
   * Pruebas de latencia, precisión del modelo, tiempo de asignación, uso de recursos y tiempo de recuperación ante desconexión de nodo evaluador.
4. **Operación en Entornos Reales (Memorias USB `toram` sin IDEs):**
   * Los nodos corren en Linux desde una memoria USB booteable en RAM. No hay VS Code ni PlatformIO instalados en los PCs del laboratorio.
   * Solo existe 1 placa ESP32 física, por lo que los nodos sin hardware deben contar con valores base y capacidad de simular escenarios de desastre para la sustentación.

---

## 3. Plan de Cambios y Nuevos Componentes (Por lo que se va a cambiar)

```
[ ESP32 S3 ] (Hardware Físico)
     |
     | Línea JSON por Serial (115200 baudios)
     v
[ applications/sensor_emergencia.py ]
   ├── Modo Físico: Lee USB (/dev/ttyUSB0 o /dev/ttyACM0 o COM)
   └── Modo Simulado: Telemetría base + inyección de emergencias (incendio, inundación, derrumbe)
     |
     v
[ applications/mensajeria.py / Nodo ]
   ├── Publica servicio: "sensor_emergencia" y "ia_urgencias"
   ├── Tarea Distribuida: "clasificar_urgencia"
   └── Grupo Multicast: "rescate"
     |
     v (Planificador F(i,j))
[ applications/arbol_decision.py ] (Aplicación de IA)
   ├── Entrada: [temperatura, humedad_aire, humedad_suelo, luz]
   ├── Motor: Árbol de Decisión en Python puro (cero dependencias pesadas en RAM)
   └── Salidas de Diagnóstico:
         * NORMAL_ESTABLE
         * ALERTA_INCENDIO
         * ALERTA_INUNDACION_LODO
         * POSIBLE_ATRAPADO_ESCOMBROS
         * ALERTA_CALOR_EXTREMO
```

### Tabla Resumen de Cambios por Archivo

| Paso | Archivo Afectado | Tipo | Descripción del Cambio |
|:---:|---|:---:|---|
| **1** | `Planta_Inteligente/src/main.cpp` | Modificación | Cambiar la salida serial humana a un string JSON compacto y continuo cada 2 segundos. |
| **2** | `scripts/entrenar_arbol.py` | Nuevo | Genera el dataset de desastres, entrena con `scikit-learn`, obtiene métricas (matriz de confusión, accuracy) y exporta las reglas. |
| **3** | `complexnet-api/applications/arbol_decision.py` | Nuevo | Contiene el Árbol de Decisión en funciones nativas de Python sin dependencias pesadas para inferencia en tiempo real. |
| **4** | `complexnet-api/applications/sensor_emergencia.py` | Nuevo | Módulo puente para leer la ESP32 física por puerto serie y fallback simulador para nodos sin hardware. |
| **5** | `complexnet-api/applications/mensajeria.py` | Modificación | Registrar la operación `clasificar_urgencia`, comandos `telemetria`, `evaluar`, `vigilancia` y `simular`. |
| **6** | `complexnet-api/applications/monitor.py` | Modificación | Sección visual para reflejar telemetría de sensores y alertas críticas activas en vivo. |
| **7** | `complexnet-api/tests/test_ia_urgencias.py` | Nuevo | Pruebas automatizadas de clasificación de IA, despacho distribuido y reasignación ante caída de nodo. |
| **8** | `complexnet-api/docs/api/manual.md` y reporte | Modificación | Documentación técnica de la API y resultados experimentales para el informe final. |

---

## 4. Respaldo del Código Original de ESP32 (`main.cpp`)

Antes de realizar el Paso 1, este era el bucle de impresión en `main.cpp`:

```cpp
// CODIGO ORIGINAL (RESPALDO):
Serial.println();
Serial.println("========== LECTURAS ==========");
if (isnan(temperatura) || isnan(humedadAire)) {
  Serial.println("DHT11: ERROR DE LECTURA");
} else {
  Serial.print("Temperatura: ");
  Serial.print(temperatura);
  Serial.println(" °C");
  Serial.print("Humedad ambiental: ");
  Serial.print(humedadAire);
  Serial.println(" %");
}
Serial.print("Humedad tierra (ADC): ");
Serial.println(humedadTierra);
if (luz < 0) {
  Serial.println("GY-302: ERROR DE LECTURA");
} else {
  Serial.print("Intensidad de luz: ");
  Serial.print(luz);
  Serial.println(" lux");
}
Serial.println("==============================");
delay(2000);
```
