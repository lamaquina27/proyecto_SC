# Estado de los entregables del corte 2

Cruce entre lo que pide el corte 2, lo que prometió el documento del corte 1 y
lo que hay en el repositorio. Actualizado el 2026-10-01.

Leyenda: ✅ hecho y probado · 🟡 parcial · ❌ no existe todavía

**Reparto:** Juan hace todo el núcleo y la aplicación de mensajería. El
compañero hace la aplicación de regresión lineal sobre `Nodo` (ejemplo de
partida en `docs/api/manual.md` §9.4). La aplicación de sensores de
movimiento queda para después. El panel de monitoreo está en terminal:
`applications/monitor.py` (manual §11).

## 1. Los 13 entregables

| # | Entregable | Estado | Dónde está | Qué falta |
|---|---|---|---|---|
| 1 | Código fuente del núcleo funcional | ✅ | `src/`: api, communication, discovery, monitoring, resources, scheduler, tasks | — |
| 2 | Red de al menos tres nodos | 🟡 | `setup_adhoc.sh`; probado con 3 nodos en loopback (Linux y Windows) | Montarla en las Pi y grabarla (manual §8, prueba A–B–C) |
| 3 | Descubrimiento automático de nodos | ✅ | HELLO, HELLO_ACK, HEARTBEAT, TASK_REQUEST | — |
| 4 | Registro y consulta de recursos | ✅ | `GestorRecursos` (vector [C, M, B, R, A] + carga + almacenamiento), RESOURCE_UPDATE, `consultar_recursos()` | — |
| 5 | Envío de mensajes | ✅ | Unicast, multicast y broadcast; `applications/mensajeria.py` | — |
| 6 | Asignación de tareas | ✅ | `PlanificadorDistribuido` (F(i,j) y argmax), `GestorTareas` (TASK_ASSIGN, TASK_RESULT) | — |
| 7 | Detección de nodo inactivo | ✅ | Umbrales 15 s / 30 s y NODE_STATUS | — |
| 8 | Reasignación básica de tareas | ✅ | `GestorRecuperacion`: nodo caído, no entregada, tiempo agotado | — |
| 9 | Registro de eventos | ✅ | `monitoring/registro.py` (incluye eventos de tareas), `examples/analizar_logs.py` | — |
| 10 | Pruebas unitarias y de integración | ✅ | `tests/`: 72 pruebas | La regresión necesita las suyas |
| 11 | Manual técnico | ✅ | `docs/api/manual.md` | La sección de la aplicación de regresión |
| 12 | Video demostrativo | ❌ | Guion en `COMO_PROBARLO.md` | Grabarlo en las Pi |
| 13 | Presentación y sustentación | ❌ | Justificaciones en `docs/diseno.md` | Prepararla |

## 2. Requisitos del documento del corte 1

| Req. | Nombre | Estado | Cómo se cumple |
|---|---|---|---|
| RF01 | Identificación de nodos | ✅ | `node_id` persistente (decisión 16) |
| RF02 | Descubrimiento | ✅ | HELLO, HELLO_ACK, HEARTBEAT |
| RF03 | Comunicación entre nodos | ✅ | UDP en difusión y TCP enmarcado, sin servidor |
| RF04 | Registro de recursos | ✅ | `GestorRecursos.medir()` y `registrar_recurso()` (decisión 18) |
| RF05 | Difusión de mensajes | ✅ | `difundir`, `enviar_a_grupo` |
| RF06 | Consulta del estado | ✅ | `consultar_estado_red()`, `consultar_recursos()`, `obtener_estado()` |
| RF07 | Gestión de tareas | ✅ | Crear, enviar, ejecutar, monitorear (eventos y `pendientes()`) y finalizar |
| RF08 | Asignación de tareas | ✅ | Paso 1 `que_ofrezcan` + filtro de disponibilidad; paso 2 argmax F (decisión 19) |
| RF09 | Detección de fallos | ✅ | Dos umbrales y NODE_STATUS |
| RF10 | Actualización de la red | ✅ | Entradas, salidas, reingresos y reinicios con la misma identidad |
| RF11 | Reasignación de tareas | ✅ | Decisión 21 |
| RF12 | Registro de eventos | ✅ | JSONL con Lamport y métricas |
| RNF01 | Descentralización | ✅ | Cada nodo planifica sus propias tareas; NODE_STATUS no da órdenes |
| RNF02 | Tolerancia a fallos | ✅ | La red y las tareas sobreviven a la caída de un nodo |
| RNF03 | Escalabilidad | ✅ | Un nodo nuevo entra sin tocar a los demás |
| RNF04 | Adaptabilidad | ✅ | Reingreso, umbrales, refutación, reputación |
| RNF05 | Bajo consumo | ✅ | Un HEARTBEAT y un RESOURCE_UPDATE de ~250 bytes cada 5 s |
| RNF06 | Modularidad | ✅ | Un paquete por servicio; la fachada aparte |
| RNF07 | Portabilidad | ✅ | Raspberry Pi y Linux con `bat0`; Windows y WSL con `--local` |
| RNF08 | Disponibilidad | ✅ | Igual que RNF02 |
| RNF09 | Observabilidad | ✅ | Registro, `stats`, `analizar_logs.py` |
| RNF10 | Interoperabilidad | ✅ | JSON con envoltura común, documentada en el manual |

## 3. Diferencias con el corte 1 que hay que saber explicar

| Qué dice el corte 1 | Qué se hizo | Dónde está la justificación |
|---|---|---|
| Envoltura con 6 campos | Además `seq`, `lamport` y `group` | Lamport ya estaba prometido; `group` es el multicast |
| "Detector de fallos" como componente aparte | Vive dentro del descubrimiento, que ya ve cada latido | Decisiones 4 y 15 |
| `pesoLatencia` en el UML | Se usa la carga L, como en la fórmula | Decisión 19 |
| F(i,j) sin A | A se usa como filtro (RF08 pide tener en cuenta la disponibilidad) | Decisión 19 |
| Ri "confiabilidad o reputación" | mín(lo publicado, lo visto por el solicitante) | Decisión 19 |
| TASK_REQUEST "solicita a la red" | Se difunde solo cuando no se conoce a nadie que la ofrezca | Decisión 20 |

## 4. Prueba de concepto del corte 1

Hecha. `tests/test_tareas.py::test_prueba_de_concepto_del_corte_1`: el nodo 1
pide `suma 10 + 20`, el nodo 2 la ejecuta y devuelve 30 por TASK_RESULT. La
detección de la caída del nodo 2 está en `tests/test_integracion.py`, y la
reasignación cuando se cae a mitad de una tarea en
`tests/test_tareas.py::test_se_cae_el_ejecutor_y_se_reasigna`. En vivo:
comando `calc 10 + 20` de `applications/mensajeria.py`, y para una tarea
que dure, `estres 20` con el monitor abierto.

## 5. Qué falta

**Juan**: montar la red en las Pi, la prueba A–B–C y el video.

**Compañero**: la aplicación de regresión, sus pruebas y su sección del
manual. Todo lo que necesita está en `Nodo`: `registrar_operacion`,
`enviar_tarea_async` y el ejemplo del manual §9.4.

**Juntos**: el video y la presentación.
