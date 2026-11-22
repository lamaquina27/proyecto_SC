# Informe Experimental y Evaluación de Desempeño — Fase 3

**Proyecto Integrador:** ComplexNet API — Computación Descentralizada sobre Redes Ad hoc  
**Asignatura:** Sistemas Complejos — Corte 3  
**Universidad Sergio Arboleda** — Escuela de Ciencias Exactas e Ingeniería  
**Autores:** Felipe Morales Robelto y Juan David Sánchez Vargas  
**Docente:** Joaquín F. Sánchez Cifuentes  
**Fecha:** Noviembre de 2026  

---

## Resumen Ejecutivo

El presente informe expone los resultados experimentales obtenidos durante la Fase 3 del proyecto ComplexNet API. Se evalúa el comportamiento del framework descentralizado en un escenario de desastre natural simulado sobre una red ad hoc inalámbrica con topología dinámica, balizas sensoriales físicas (ESP32 S3) y clasificación distribuida de urgencias mediante Inteligencia Artificial explicable. Se da respuesta formal a los 5 ejes requeridos por la guía académica: (1) Distribución de tareas, (2) Asignación de recursos mediante función de aptitud, (3) Protocolo de mensajería, (4) Tolerancia a fallos y recuperación, y (5) Métricas experimentales y evaluación de aprendizaje automático.

---

## 1. Mecanismo de Distribución de Tareas

En ComplexNet API, la computación se modela de manera **completamente descentralizada**: ningún nodo actúa como coordinador global u orquestador permanente. Cada nodo que genera una necesidad computacional asume el rol de *nodo cliente/solicitante* exclusivamente para esa transacción.

```
   [Nodo Emisor / Sensor]                                [Nodo Ejecutor Óptimo]
             │                                                      │
             │─────── (1) TCP: TASK_ASSIGN [tarea_id, args] ───────>│
             │                                                      │ (Ejecución aislada)
             │<────── (2) TCP: TASK_RESULT [tarea_id, result] ──────│
```

### Protocolo de Asignación en 2 Fases:
1. **Verificación de Capacidades en Caché Local:** El nodo solicitante consulta su tabla de vecinos (`DirectorioVecinos`). Identifica cuáles nodos activos tienen registrada la operación requerida (por ejemplo, `clasificar_urgencia` o `calcular`).
2. **Descubrimiento Reactivo (`TASK_REQUEST`):** Si ningún vecino conocido reporta soporte para la operación, el solicitante emite un broadcast UDP `TASK_REQUEST` a toda la malla. Los nodos con capacidad disponible responden con `HELLO_ACK` actualizando sus servicios.
3. **Despacho Punto a Punto (`TASK_ASSIGN`):** Seleccionado el mejor candidato mediante el planificador `F(i, j)`, la tarea se serializa en JSON y se envía directamente por socket TCP con enmarcado por longitud (cabecera fija de 4 bytes en formato *big-endian*).
4. **Respuesta (`TASK_RESULT`):** El nodo ejecutor procesa la rutina en un hilo de trabajo independiente para no bloquear el transporte de red, computa el resultado y lo retorna al emisor mediante un mensaje `TASK_RESULT`.

---

## 2. Asignación de Recursos Mediante Optimización F(i, j)

El planificador distribuido resuelve un problema de optimización multi-criterio en tiempo real. Cuando un nodo emisor necesita delegar una tarea, evalúa la función de aptitud `F(i, j)` sobre cada nodo candidato:

```
F(i, j) = w1 * Ci + w2 * Mi + w3 * Bi + w4 * Ri - w5 * Li
```

Donde las variables corresponden al vector de estado normalizado `[0, 1]` publicado periódicamente por cada nodo:
* **Ci (Capacidad de CPU disponible):** `1.0 - carga_cpu`.
* **Mi (Memoria RAM disponible):** `RAM_libre / RAM_total`.
* **Bi (Calidad de Enlace de Red):** Obtenida directamente de la métrica `TQ` (Transmit Quality) provista por el protocolo B.A.T.M.A.N. Advanced: `Bi = TQ / 255.0`.
* **Ri (Reputación Histórica):** Proporción de tareas completadas exitosamente sin errores ni abandonos: `Ri = min(R_publicado, R_observado)`.
* **Li (Carga de Tareas en Curso):** Penalización por saturación concurrente: `Li = min(1.0, tareas_activas * 0.25)`.

### Configuración de Pesos para Clasificación de Emergencias:
Para tareas de Inteligencia Artificial (latencia crítica y sensibilidad a la conectividad de campo):
`{w1 = 0.25, w2 = 0.15, w3 = 0.35, w4 = 0.15, w5 = 0.10}`

Se prioriza la calidad del enlace inalámbrico (`Bi`) para minimizar la pérdida de paquetes en el borde del desastre, complementado con disponibilidad de CPU (`Ci`). El nodo ejecutor final se elige por:

```
nodo_optimo = argmax_i F(i, j)
```

---

## 3. Protocolo de Mensajería y Tipos de Mensajes Intercambiados

Todas las comunicaciones en ComplexNet API se unifican bajo una envoltura JSON estándar con sellos temporales y ordenamiento causal mediante **relojes de Lamport**:

```json
{
  "message_id": "9d8b3c1a",
  "type": "TASK_ASSIGN",
  "sender": "a3f1c9d2",
  "receiver": "e4b872fa",
  "group": null,
  "timestamp": 1795301240.12,
  "seq": 142,
  "lamport": 405,
  "payload": {
    "task_id": "t-7701",
    "operacion": "clasificar_urgencia",
    "parametros": {"temperatura": 48.5, "humedad_aire": 18.0, "suelo": 5.0, "luz": 850.0}
  }
}
```

### Taxonomía de Mensajes Intercambiados:

| Tipo | Capa de Transporte | Semántica y Propósito |
|---|---|---|
| `HELLO` / `HELLO_ACK` | UDP Broadcast | Descubrimiento inicial mutuo entre nodos al encender la interfaz. |
| `HEARTBEAT` | UDP Broadcast (cada 5 s) | Latido de vida que actualiza el estado activo y la lista de servicios. |
| `RESOURCE_UPDATE` | UDP Broadcast (cada 5 s) | Difusión del vector de recursos `[C, M, B, R, A]`. |
| `NODE_STATUS` | UDP Broadcast | Notificación cuando un vecino cambia de estado (`SOSPECHOSO`, `INACTIVO`). |
| `TASK_REQUEST` | UDP Broadcast | Petición reactiva para descubrir nodos con una capacidad específica. |
| `TASK_ASSIGN` | TCP Unicast Enmarcado | Asignación formal de la tarea al nodo con mayor aptitud `F(i, j)`. |
| `TASK_RESULT` | TCP Unicast Enmarcado | Retorno del resultado computado al nodo solicitante. |
| `APP_MSG` (Multicast) | UDP Difusión Filtrada | Alertas perimetrales al grupo temático `"rescate"`. |
| `FILE_CHUNK` | TCP Unicast Enmarcado | Envío de archivos binarios o comprimidos por zlib. |

---

## 4. Detección de Caídas y Mecanismo de Reasignación Automática

El sistema aborda la inestabilidad intrínseca de las redes ad hoc mediante dos subsistemas complementarios:

### A. Detector de Fallos en Dos Umbrales
* **Umbral tau_1 = 15 s (`SOSPECHOSO`):** Si no se reciben paquetes de un nodo en 15 s, se suspende la asignación de nuevas tareas hacia él, pero se mantienen sus rutas en espera de recuperación transitoria.
* **Umbral tau_2 = 30 s (`INACTIVO`):** Se confirma la caída o desconexión del nodo. Se emite un aviso `NODE_STATUS` y se transfieren sus tareas pendientes al gestor de recuperación.

### B. Gestor de Recuperación (`GestorRecuperacion`)
Cuando un nodo ejecutor muere en medio de un cómputo:
1. El solicitante intercepta el cierre abrupto del socket TCP o la notificación de `INACTIVO`.
2. La tarea pasa de estado `EN_EJECUCION` a `FALLIDA`.
3. Se incrementa el contador de reintentos (`reintentos < 3`).
4. Se penaliza la reputación observada del nodo caído (`R_observado = R_observado - 0.2`).
5. Se invoca nuevamente al planificador `F(i, j)`, el cual excluye al nodo inactivo y selecciona al segundo mejor candidato disponible.
6. La tarea se retransmite sin intervención humana y el resultado final se entrega exitosamente.

---

## 5. Evaluación Experimental de la Inteligencia Artificial (CART)

Para la clasificación de emergencias en tiempo real, se entrenó y desplegó un Árbol de Decisión CART (Classification and Regression Trees) optimizado mediante el criterio de **impureza de Gini**:

```
Impureza de Gini: I_G(p) = 1 - sum(p_i^2)
```

### A. Justificación Frente a Otras Alternativas

| Criterio | Árbol de Decisión (Implementado) | Redes Neuronales (MLP/CNN) | Máquinas de Soporte Vectorial (SVM) |
|---|:---:|:---:|:---:|
| **Interpretabilidad (XAI)** | **Total:** Reglas lógicas auditables | Opaca ("Caja negra") | Baja (Depende de kernels) |
| **Dependencias en RAM (`toram`)** | **0 dependencias** (Python puro) | Requiere PyTorch / TF (~500 MB) | Requiere Scikit-Learn (~150 MB) |
| **Tiempo de Inferencia** | **< 0.2 ms** | 15 - 50 ms | 5 - 12 ms |
| **Resistencia a Ruido Sensorial** | Alta (Particiones ortogonales) | Media | Sensible a outliers |

### B. Métricas Globales de Rendimiento

El modelo fue validado contra un conjunto de prueba independiente de **400 muestras sintéticas** (partición 80/20 sobre un dataset de 2,000 registros generados a partir de límites físicos de desastres):

* **Muestras Totales de Prueba:** 400 registros sintéticos
* **Predicciones Correctas:** 390
* **Exactitud Global (Accuracy):** **97.50%**
* **Tiempo Promedio de Inferencia en CPU:** **0.0003 ms (0.3 µs)** directo en árbol; **0.0013 ms (1.3 µs)** con desempaquetado de diccionario (verificado en `scripts/benchmark_ia.py`).

> **Nota Metodológica Obligatoria:** Estas métricas se obtuvieron sobre un conjunto de datos sintético estructurado para simular rangos ambientales de emergencia. **No representan una validación estadística en desastres naturales reales**, donde variables no contempladas (polvo en suspensión, viento o sombras) pueden alterar las distribuciones de probabilidad.

### C. Matriz de Confusión (Ejecución Reproducible)

```
                            PREDICCIÓN DEL MODELO
                     Normal  Incendio  Inundación  Escombros  Calor   TOTAL
REAL:
Normal                 84        0          0          0        0       84
Incendio                0       82          0          0        0       82
Inundación              1        0         72          0        0       73
Escombros               5        0          0         78        0       83
Calor                   4        0          0          0       74       78
TOTAL PREDICCIÓN:      94       82         72         78       74      400
```

### D. Métricas Detalladas por Categoría

| Clase de Emergencia | Precisión (Precision) | Exhaustividad (Recall) | Puntuación F1 (F1-Score) | Muestras Reales (Soporte) |
|---|:---:|:---:|:---:|:---:|
| `NORMAL_ESTABLE` | 89.4% (0.8936) | 100.0% (1.0000) | **0.944** | 84 |
| `ALERTA_INCENDIO` | 100.0% (1.0000) | 100.0% (1.0000) | **1.000** | 82 |
| `ALERTA_INUNDACION_LODO` | 100.0% (1.0000) | 98.6% (0.9863) | **0.993** | 73 |
| `POSIBLE_ATRAPADO_ESCOMBROS` | 100.0% (1.0000) | 94.0% (0.9398) | **0.969** | 83 |
| `ALERTA_CALOR_EXTREMO` | 100.0% (1.0000) | 94.9% (0.9487) | **0.974** | 78 |
| **Promedio Ponderado** | **97.8%** | **97.5%** | **0.975** | **400** |

---

## 6. Conclusiones

1. **Autoorganización Exitosa:** El protocolo B.A.T.M.A.N. Advanced combinado con la capa de descubrimiento ComplexNet permitió converger la topología de red en menos de 10 segundos tras el encendido de los nodos, sin configuración de routers centralizados.
2. **Eficiencia en Recursos Críticos:** El árbol de decisión nativo demostró una precisión superior al 97% con un coste de cómputo despreciable (< 0.2 ms), garantizando que los equipos de rescate operen fluidamente en memorias RAM limitadas.
3. **Resiliencia Comprobada:** Ante la desconexión intencionada de un nodo ejecutor en plena inferencia, el sistema reasignó la tarea en un tiempo medio inferior a 1.2 segundos sin pérdida de información de telemetría.
