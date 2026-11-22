# Estado de los Entregables — Corte 3 (Fase Final)

Cruce formal entre los requerimientos establecidos en el syllabus del curso (**Sistemas Complejos**, Universidad Sergio Arboleda), las especificaciones de entrega de la Fase 3 y los artefactos implementados en el repositorio.

**Integrantes:** Felipe Morales Robelto y Juan David Sánchez Vargas  
**Docente:** Joaquín F. Sánchez Cifuentes  
**Fecha:** Noviembre de 2026  
**Leyenda:** ✅ Implementado, verificado y documentado · 🟡 En proceso · ❌ Pendiente

---

## 1. Matriz de Cumplimiento de Entregables Oficiales (Fase 3)

| # | Requerimiento / Entregable Oficial | Estado | Archivos / Componentes en el Repositorio | Evidencia y Validación |
|---|---|:---:|---|---|
| **1** | **Núcleo Distribuido y Descentralizado Completo** | ✅ | `src/api/`, `src/communication/`, `src/discovery/`, `src/monitoring/`, `src/resources/`, `src/scheduler/`, `src/tasks/` | Arquitectura por capas sin nodo maestro ni punto único de falla (SPOF). |
| **2** | **Despliegue sobre Red Ad hoc Inalámbrica** | ✅ | `setup_adhoc.sh`, `arrancar_nodo.sh`, `PREPARAR_USB.md` | Red mallada operando con protocolo B.A.T.M.A.N. Advanced (`bat0`) en modo IBSS, con imagen booteable en RAM (`toram`). |
| **3** | **Descubrimiento y Tolerancia a Fallos** | ✅ | `src/discovery/detector_fallos.py`, `src/tasks/gestor_recuperacion.py` | Detección en 2 etapas: 15 s (`SOSPECHOSO`), 30 s (`INACTIVO`). Reasignación automática de tareas huérfanas. |
| **4** | **Planificador Distribuido por Función de Aptitud** | ✅ | `src/scheduler/planificador.py` | Optimización multi-criterio `F(i, j) = w1*Ci + w2*Mi + w3*Bi + w4*Ri - w5*Li`. Selección por `argmax_i F(i, j)`. |
| **5** | **Aplicación 1: Monitoreo Ambiental y Alertas** | ✅ | `applications/sensor_emergencia.py`, `applications/monitor.py`, `Planta_Inteligente/src/main.cpp` | Lectura física USB de microcontrolador ESP32 S3 (DHT11, sensor capacitivo de suelo, GY-302 BH1750). Alertas automáticas por grupo multicast `"rescate"`. |
| **6** | **Aplicación 2: Cómputo Colaborativo y Balanceo** | ✅ | `applications/operaciones.py`, `applications/mensajeria.py` | Tarea matemática distribuida segura (`calc` vía análisis AST) y partición de carga de CPU/memoria (`estres`). |
| **7** | **Aplicación 3: Inteligencia Artificial Distribuida** | ✅ | `applications/arbol_decision.py`, `scripts/entrenar_arbol.py`, `scripts/dataset_emergencias.csv` | Clasificador de emergencias con Árbol de Decisión CART nativo (impureza de Gini). Exactitud: **97.5%**, tiempo de inferencia: `< 0.2 ms`. |
| **8** | **Pruebas Automatizadas Unitarias y de Integración** | ✅ | `tests/` (8 suites de prueba: `test_ia_urgencias.py`, `test_tareas.py`, `test_integracion.py`, etc.) | **100% de pruebas aprobadas** (128+ tests unitarios y de estrés distribuido). |
| **9** | **Manual Técnico y Arquitectura de Software** | ✅ | `complexnet-api/README.md`, `docs/api/manual.md`, `docs/diseno.md` | Documentación detallada de interfaces, envoltura de paquetes, protocolos y 27 decisiones de diseño arquitectónico. |
| **10** | **Informe Experimental y Científico** | ✅ | `docs/informe_experimental_corte3.md`, `docs/metricas_arbol_decision.txt` | Análisis formal respondiendo a las 5 preguntas del syllabus (distribución, recursos, mensajes, tolerancia a fallos, métricas cuantitativas). |

---

## 2. Cobertura de las 3 Aplicaciones Descentralizadas Exigidas

```
                                 [ COMPLEXNET API ]
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌──────────────────────┐   ┌───────────────────────────┐   ┌──────────────────────────────┐
│     APLICACIÓN 1     │   │       APLICACIÓN 2        │   │         APLICACIÓN 3         │
│ Monitoreo Ambiental  │   │  Procesamiento en Lote y  │   │ Inteligencia Artificial CART │
│  y Alertas de Campo  │   │    Cómputo Colaborativo   │   │  Clasificador de Urgencias   │
├──────────────────────┤   ├───────────────────────────┤   ├──────────────────────────────┤
│ • Hardware ESP32 S3  │   │ • Distribución de tareas  │   │ • Árbol de decisión nativo   │
│ • Temp/Hum (DHT11)   │   │   matemáticas seguras AST │   │ • Inferencia sub-milisegundo │
│ • Suelo capacitivo   │   │ • Estrés sintético de CPU │   │ • Cero librerías pesadas     │
│ • Luz Lux (BH1750)   │   │   repartido en la malla   │   │ • 5 tipos de diagnóstico     │
│ • Multicast "rescate"│   │ • Balanceo por F(i,j)     │   │ • Tolerante a caída de nodo  │
└──────────────────────┘   └───────────────────────────┘   └──────────────────────────────┘
```

---

## 3. Justificación de Decisiones Técnicas Clave

### A. ¿Por qué un Árbol de Decisión CART en lugar de Redes Neuronales o SVM?
1. **Explicabilidad en Misiones Críticas (XAI):** Ante el colapso de una estructura, una brigada de rescate no puede confiar en un modelo opaco ("caja negra"). El árbol de decisión permite inspeccionar visual y lógicamente cada umbral de decisión (p. ej., `Luz <= 2.75 lux y Suelo <= 35% -> Escombros`).
2. **Entorno de Ejecución Efímero (`toram`):** Las máquinas de rescate arrancan desde memorias USB cargadas en RAM sin acceso a repositorios de internet. Un modelo CART nativo no requiere `scikit-learn`, `torch` ni `tensorflow`, pesando menos de 10 KB de código puro en Python estándar.
3. **Determinismo y Rendimiento:** La inferencia toma ~0.15 ms (0.3 µs en pruebas de micro-benchmark), permitiendo evaluar cientos de sensores por segundo sin penalizar la CPU de los nodos.

### B. ¿Por qué la ESP32 es una extensión y no un nodo BATMAN completo?
La ESP32 carece de potencia y soporte de kernel para ejecutar el módulo Linux de capa 2 `batman-adv.ko`. Tratar de emular la malla en el microcontrolador introduce fragilidad y saturación de memoria. Integrar la ESP32 como baliza sensorial conectada vía puerto serie USB (`pyserial` o puente `/dev/ttyUSB0`) a un nodo de campo garantiza un acoplamiento limpio: el nodo Linux actúa como pasarela distribuyendo la telemetría a la red ad hoc.

---

## 4. Registro de Trazabilidad y Verificación

* **Prueba unitaria de la IA distribuida:** `pytest tests/test_ia_urgencias.py`
* **Prueba de reasignación ante muerte del ejecutor:** `pytest tests/test_tareas.py -k "se_cae_el_ejecutor"`
* **Prueba de compresión adaptativa zlib:** `pytest tests/test_archivos.py`
* **Prueba de consistencia de mensajes JSONL y Lamport:** `pytest tests/test_comunicacion.py`
