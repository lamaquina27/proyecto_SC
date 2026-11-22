# ComplexNet API — Manual de Arquitectura y Desarrollo

ComplexNet API es un framework modular en Python diseñado para computación distribuida y servicios descentralizados sobre redes ad hoc inalámbricas (B.A.T.M.A.N. Advanced / Wi-Fi IBSS), con soporte para balizas sensoriales físicas (ESP32) e inferencia de Inteligencia Artificial explicable en el borde.

---

## 1. Módulos y Responsabilidades del Núcleo (`src/`)

El núcleo del sistema está desacoplado en 7 paquetes especializados sin dependencias circulares:

```
src/
├── api/             # Fachada de integración y ciclo de vida del nodo
├── communication/   # Transporte de red UDP/TCP, compresión y enmarcado
├── discovery/       # Protocolos de presencia y detección de fallos
├── monitoring/      # Registro estructurado de eventos y relojes de Lamport
├── resources/       # Monitoreo de recursos y vector de estado del sistema
├── scheduler/       # Planificador distribuido y función de aptitud F(i,j)
└── tasks/           # Despacho de tareas, seguimiento y recuperación por caídas
```

### Detalle por Módulo

| Módulo | Clases Principales | Responsabilidad Técnica |
|---|---|---|
| `api/` | `Nodo`, `Identidad` | Provee la interfaz pública de alto nivel para aplicaciones. Gestiona el ciclo de vida de los servicios de fondo y mantiene la persistencia del identificador único de nodo (`node_id`) entre reinicios. |
| `communication/` | `EmisorMensajes`, `ReceptorMensajes`, `MallaBATMAN`, `GestorArchivos` | Gestiona sockets UDP para presencia y difusión (respetando MTU < 1400 bytes). Implementa sockets TCP con enmarcado por longitud de 4 bytes en formato big-endian para tareas y archivos binarios con compresión adaptativa `zlib`. |
| `discovery/` | `GestorDescubrimiento`, `DirectorioVecinos`, `DetectorFallos` | Emite y procesa mensajes `HEARTBEAT` cada 5 segundos. Mantiene la tabla de vecinos activos y aplica el detector de fallos en dos umbrales: 15 s (`SOSPECHOSO`) y 30 s (`INACTIVO`). |
| `resources/` | `GestorRecursos` | Mide periódicamente la carga de CPU, uso de RAM (vía `psutil`), calidad del enlace inalámbrico (`TQ/255` desde B.A.T.M.A.N.) y disponibilidad del nodo para construir el vector normalizado `[C, M, B, R, A]`. |
| `scheduler/` | `PlanificadorDistribuido` | Resuelve la asignación descentralizada de tareas calculando la función de aptitud `F(i, j)` y seleccionando al candidato óptimo mediante `argmax_i F(i, j)`. |
| `tasks/` | `GestorTareas`, `GestorRecuperacion`, `Tarea` | Administra la máquina de estados de las tareas (`CREADA`, `ENVIADA`, `EN_EJECUCION`, `COMPLETADA`, `FALLIDA`). Detecta abortos de conexión y reasigna automáticamente tareas huérfanas a nodos alternativos. |
| `monitoring/` | `RegistroEventos`, `RelojLamport` | Registra trazas de auditoría en formato JSONL y mantiene la sincronización de causalidad de eventos mediante relojes lógicos de Lamport, prescindiendo de servidores NTP. |

---

## 2. Ciclo de Vida y Protocolo de Mensajería

Todos los paquetes que viajan por la red utilizan una envoltura JSON unificada:

```json
{
  "message_id": "a1f4c2e8",
  "type": "TASK_ASSIGN",
  "sender": "nodo-01",
  "receiver": "nodo-02",
  "group": null,
  "timestamp": 1795304120.55,
  "seq": 48,
  "lamport": 112,
  "payload": {
    "task_id": "t-104",
    "operacion": "clasificar_urgencia",
    "parametros": {"temperatura": 42.0, "humedad_aire": 19.5, "suelo": 12.0, "luz": 800.0}
  }
}
```

### Tipos de Mensajes Soportados:
* `HEARTBEAT` (UDP Broadcast): Latido emitido cada 5 segundos con la lista de servicios y grupos del nodo.
* `RESOURCE_UPDATE` (UDP Broadcast): Emisión periódica del vector de estado `[C, M, B, R, A]`.
* `TASK_REQUEST` (UDP Broadcast): Búsqueda reactiva de nodos que ofrezcan una operación no encontrada en la caché local.
* `NODE_STATUS` (UDP Broadcast): Aviso de transición de estado de un vecino (`SOSPECHOSO` o `INACTIVO`).
* `APP_MSG` (UDP Broadcast / Multicast): Mensajes de texto generales o filtrados por grupos temáticos (p. ej. `"rescate"`).
* `TASK_ASSIGN` / `TASK_RESULT` (TCP Unicast): Envío y retorno de tareas de cómputo distribuidas.
* `FILE_CHUNK` (TCP Unicast): Transferencia fragmentada de archivos con suma de comprobación SHA-256.

---

## 3. Cómo Crear una Nueva Aplicación con la API

Integrar un nuevo servicio o algoritmo distribuido sobre ComplexNet requiere únicamente interactuar con la clase `Nodo`:

```python
import time
from src.api.nodo import Nodo

# 1. Instanciar el nodo
# En red real usa interfaz="bat0"; en pruebas en un solo equipo usa interfaz="lo" o el flag --local
nodo = Nodo(nombre="brigada-alfa", interfaz="bat0", puerto_tcp=5001)

# 2. Definir y registrar operaciones computacionales
def procesar_imagen_termica(matriz):
    # Algoritmo de procesamiento local
    max_temp = max(matriz)
    return {"max_temperatura": max_temp, "alerta": max_temp > 60.0}

nodo.registrar_operacion("termografia", procesar_imagen_termica)

# 3. Arrancar los servicios en segundo plano
nodo.iniciar()

try:
    # 4. Suscribirse a un grupo temático de emergencias
    nodo.unirse_a_grupo("rescate")

    # 5. Enviar un mensaje de aviso al grupo
    nodo.enviar_a_grupo("rescate", {"estado": "Unidad en posición"})

    # 6. Delegar una tarea a la red (el planificador elegirá automáticamente al mejor nodo)
    tarea_id = nodo.enviar_tarea_async(
        operacion="termografia",
        parametros={"matriz": [24.0, 25.5, 62.0, 23.8]}
    )
    print(f"Tarea enviada con ID: {tarea_id}")

    # 7. Esperar y consultar el resultado
    while True:
        resultado = nodo.obtener_resultado(tarea_id)
        if resultado is not None:
            print("Resultado recibido de la red:", resultado)
            break
        time.sleep(0.5)

finally:
    # Detener el nodo y notificar salida ordenada a la red
    nodo.detener()
```

---

## 4. Aplicaciones Incluidas en `applications/`

| Archivo | Rol | Descripción |
|---|---|---|
| `mensajeria.py` | Consola Principal | Interfaz CLI interactiva para brigadistas. Permite enviar mensajes directos, difundir alertas por grupo, transferir archivos, repartir tareas matemáticas, estresar núcleos y solicitar diagnósticos de emergencia. |
| `monitor.py` | Panel de Control | Monitor en vivo para terminal que visualiza los nodos conectados, sus vectores de recursos `[C, M, B, R, A]`, las tareas activas y las alertas críticas recibidas en el canal `"rescate"`. |
| `sensor_emergencia.py` | Pasarela de Borde | Administra la conexión serial con la ESP32 física a 115200 baudios, calibra la lectura del sensor de suelo capacitivo y activa automáticamente el modo simulador con fallbacks si no hay hardware conectado. |
| `arbol_decision.py` | Motor de IA | Implementación nativa del clasificador de urgencias mediante Árbol de Decisión CART. Opera sin dependencias externas en sub-milisegundos evaluando temperatura, humedad de aire, suelo y luminosidad. |
| `operaciones.py` | Tareas de Cómputo | Tareas matemáticas distribuidas analizadas de forma segura mediante el árbol de sintaxis abstracta (`ast`, sin `eval`) y tareas sintéticas de estrés de CPU para pruebas de balanceo. |

---

## 5. Ejecución de la Suite de Pruebas

El proyecto cuenta con **128 pruebas automatizadas** que garantizan la integridad de todos los módulos:

```bash
# Ejecutar todas las pruebas unitarias y de integración
python -m pytest tests/ -v

# Probar la inferencia de Inteligencia Artificial y tolerancia a fallos
python -m pytest tests/test_ia_urgencias.py -v

# Probar el planificador y la reasignación de tareas ante caídas
python -m pytest tests/test_tareas.py -v

# Probar la transferencia y compresión de archivos
python -m pytest tests/test_archivos.py -v
```
