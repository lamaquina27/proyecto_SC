# ComplexNet API — Núcleo y Aplicaciones

Biblioteca y framework en Python para computación distribuida y servicios descentralizados sobre redes ad hoc inalámbricas (B.A.T.M.A.N. Advanced / Wi-Fi IBSS), con soporte para nodos móviles, balizas sensoriales IoT (ESP32) e inferencia distribuida de Inteligencia Artificial.

---

## 1. Arquitectura del Núcleo (`src/`)

El código del núcleo implementa una arquitectura modular desacoplada en capas:

```
src/
├── api/             # Fachada principal (Nodo) y persistencia de identidad (node_id)
├── communication/   # Transporte UDP (difusión/presencia) y TCP (tareas y archivos)
├── discovery/       # Protocolo HELLO/HEARTBEAT y detector de fallos en 2 umbrales
├── monitoring/      # Registro distribuido JSONL y sincronización lógica de Lamport
├── resources/       # Monitoreo del vector de estado [CPU, RAM, Bandwidth, Rep, Avail]
├── scheduler/       # Planificador distribuido: argmax F(i, j)
└── tasks/           # Máquina de estados de tareas y recuperación por caídas
```

### Flujo de Datos y Eventos
1. **Descubrimiento Continuo:** Cada nodo anuncia su presencia cada 5 s vía datagramas UDP broadcast (`HEARTBEAT`). Si un nodo deja de emitir latidos, pasa a estado `SOSPECHOSO` a los 15 s y a `INACTIVO` a los 30 s.
2. **Telemetría de Recursos:** Los nodos publican su vector normalizado $S_i = [C_i, M_i, B_i, R_i, A_i]$ cada 5 s vía `RESOURCE_UPDATE`.
3. **Planificación Descentralizada:** Cuando una aplicación solicita ejecutar una tarea, el planificador local calcula la función de aptitud $F(i,j)$ sobre todos los nodos activos y selecciona al nodo óptimo $i^* = \arg\max_i F(i,j)$.
4. **Ejecución y Resiliencia:** La tarea se transmite por TCP enmarcado. Si el nodo asignado colapsa antes de enviar el resultado, el `GestorRecuperacion` detecta la caída y reasigna automáticamente la tarea al segundo mejor nodo.

---

## 2. Aplicaciones Descentralizadas (`applications/`)

| Archivo | Rol | Descripción |
|---|---|---|
| `mensajeria.py` | Consola Principal | Interfaz interactiva de brigada: mensajería directa/grupos, envío de archivos comprimidos, cálculo distribuido, estrés de red y evaluación de emergencias. |
| `monitor.py` | Supervisión Visual | Monitor en tiempo real para terminal que muestra el estado de los nodos, uso de recursos, tareas activas y alertas críticas del canal `"rescate"`. |
| `arbol_decision.py` | Motor de IA | Árbol de decisión CART nativo en Python. Clasifica condiciones de emergencia en sub-milisegundos con 97.5% de exactitud y cero dependencias externas. |
| `sensor_emergencia.py` | Puente Hardware / Edge | Lee telemetría física por USB desde una placa ESP32 (DHT11, sensor capacitivo de suelo, GY-302) o genera telemetría simulada en nodos sin hardware. |
| `operaciones.py` | Tareas de Cómputo | Tareas matemáticas distribuidas seguras (mediante AST) y tareas de estrés computacional. |

---

## 3. Instalación y Requisitos

El núcleo de ComplexNet está diseñado para funcionar en entornos de emergencia, priorizando la ausencia de dependencias pesadas:

```bash
# Dependencias base
pip install -r requirements.txt

# Para soporte de lectura física con ESP32 por USB (opcional en nodos sin sensor):
pip install pyserial
```

### Contenido de `requirements.txt`:
* `psutil>=5.9.0` (lectura de métricas de CPU y memoria del sistema operativo)
* `pytest>=7.0.0` (suite de pruebas unitarias y de integración)

*(Nota: El clasificador de Inteligencia Artificial **no requiere** `scikit-learn` ni `numpy` en tiempo de ejecución; se implementó de forma nativa para permitir arranque instantáneo en memorias USB `toram`).*

---

## 4. Uso Rápido de la API en Python

Crear un nuevo servicio o integrar un nodo en ComplexNet requiere solo unas pocas líneas de código:

```python
from src.api.nodo import Nodo

# 1. Instanciar el nodo
nodo = Nodo(nombre="brigada-01", interfaz="bat0", puerto_tcp=5001)

# 2. Registrar una operación que este nodo sabe resolver
def mi_algoritmo(x, y):
    return {"resultado": x ** y}

nodo.registrar_operacion("potencia", mi_algoritmo)

# 3. Arrancar servicios de red (descubrimiento, scheduler, sockets)
nodo.iniciar()

# 4. Enviar una tarea a la red (el planificador elegirá el mejor nodo automáticamente)
tarea_id = nodo.enviar_tarea_async("potencia", {"x": 2, "y": 10})

# 5. Unirse a un grupo temático de mensajería
nodo.unirse_a_grupo("rescate")
nodo.enviar_a_grupo("rescate", {"alerta": "Brigada en posición"})
```

---

## 5. Pruebas Automatizadas

La suite incluye 128 pruebas que validan desde el protocolo de serialización y la compresión zlib hasta la tolerancia a fallos y la inferencia de IA:

```bash
# Ejecutar todas las pruebas
pytest tests/ -v

# Probar específicamente el módulo de Inteligencia Artificial distribuida
pytest tests/test_ia_urgencias.py -v

# Probar la reasignación automática de tareas ante caída de nodos
pytest tests/test_tareas.py -k "se_cae_el_ejecutor" -v
```
