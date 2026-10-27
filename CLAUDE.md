# ComplexNet API

Proyecto integrador de Sistemas Complejos, Universidad Sergio Arboleda.
Felipe Morales Robelto y Juan David Sánchez Vargas.

API de computación descentralizada sobre una red ad hoc con B.A.T.M.A.N.
Advanced. Escenario: comunicación y procesamiento en zonas de desastre
natural, sin internet y sin servidor central.

## Comandos

Todo se corre desde `complexnet-api/`. La aplicación con `--local` funciona
también en Windows (probado con tres nodos), y las pruebas pasan igual en
Windows y en Linux (necesitan `pytest`; en Windows, instalarlo en un venv). En
Windows, `malla.py` no puede leer interfaces (no hay `fcntl`), así que solo
sirve el modo `--local`.

```bash
pip install -r requirements.txt
python3 applications/mensajeria.py            # aplicacion 1 en la malla (bat0)
python3 applications/mensajeria.py --local    # lo mismo sin malla, varias terminales
python3 applications/monitor.py [--local]     # recursos y tareas de cada nodo, en vivo
python3 -m pytest tests -v                    # 125 pruebas, tardan ~7 min
python3 examples/demo_descubrimiento.py nodo-01 lo 127.255.255.255 5001 [grupo1,grupo2]
python3 examples/demo_comunicacion.py nodo-01 lo 127.255.255.255 5001
python3 examples/analizar_logs.py logs
sudo ./setup_adhoc.sh 1                       # solo en las Raspberry Pi
```

Para el laboratorio se usa una sola USB con Ubuntu 24.04 arrancado con
`toram` (pasos en `PREPARAR_USB.md`). `preparar_usb.ps1 -Unidad E:` copia el
proyecto y `paquetes/*.deb` a la USB, y en cada equipo
`sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh N` copia todo
a la RAM, suelta la USB, monta la malla y abre la mensajería. Los `.sh` se
guardan con LF (`.gitattributes`); `paquetes/` y `logs/` no van a git.

El segundo y tercer argumento de los demos (interfaz y difusión) son para
probar sin malla. En los equipos reales se omiten y se usa `bat0`. El puerto
TCP solo hace falta cuando varios nodos corren en el mismo equipo.

## Estructura

```
complexnet-api/
├── src/
│   ├── api/               capa 4: la fachada para el programador
│   │   ├── nodo.py        clase Nodo del UML; junta todos los servicios
│   │   └── identidad.py   node_id persistente en ~/.complexnet (RF01)
│   ├── communication/     capa 2: mueve mensajes, no decide nada
│   │   ├── message.py     envoltura, tipos del corte 1, reloj de Lamport, limite UDP
│   │   ├── transporte.py  UDP en difusión y multicast, TCP enmarcado con reintentos
│   │   ├── archivos.py    FILE_CHUNK y FILE_ACK: archivos en trozos con SHA-256, comprimidos con zlib si vale la pena
│   │   └── malla.py       lee bat0: IP, difusión, MTU y calidad TQ
│   ├── discovery/         capa 3: quién está y cómo está
│   │   ├── vecino.py      una fila de la tabla de vecinos
│   │   ├── servicio.py    HELLO, HEARTBEAT, RESOURCE_UPDATE, NODE_STATUS, umbrales y grupos
│   │   └── directorio.py  node_id -> IP, lo usa solo demo_comunicacion
│   ├── monitoring/
│   │   └── registro.py    eventos en JSONL y métricas
│   ├── resources/
│   │   └── gestor.py      vector [C, M, B, R, A] + carga + almacenamiento
│   ├── scheduler/
│   │   └── planificador.py  F(i,j), argmax, reputación local
│   └── tasks/
│       ├── tarea.py       la tarea y sus estados
│       ├── gestor.py      TASK_REQUEST, TASK_ASSIGN, TASK_RESULT; cola de ejecución
│       └── recuperacion.py  reasignación: caído, no entregada, tiempo agotado
├── applications/
│   ├── mensajeria.py      aplicacion 1, escrita solo con Nodo
│   ├── operaciones.py     calcular (ast, sin eval) y estresar (proceso aparte)
│   └── monitor.py         panel de monitoreo en terminal (observador, no recibe tareas)
├── tests/                 comunicacion, descubrimiento, integracion (3 nodos), api, tareas, archivos, operaciones
├── examples/              demos y analizar_logs.py
└── docs/
    ├── diseno.md          el porqué de cada decisión (14-17 corte 1, 18-22 tareas, 23 archivos, 24-25 monitoreo y operaciones, 26 compresión, 27 difusión calculada)
    ├── entregables_corte2.md  qué falta de cada entregable y de quién es
    └── api/manual.md      manual técnico de cada operación
```

## Convenciones del proyecto

- Todo el código y los nombres en español, sin tildes dentro del código.
- Sin comentarios ni docstrings en los archivos de `src/`. Las decisiones de
  diseño se documentan en `docs/`, no en el código.
- Cada carpeta de `src/` es un paquete con su `__init__.py` que exporta lo
  público.
- Las pruebas corren sobre loopback, nunca requieren la malla.

## Decisiones que no se cambian

Estas están justificadas en el documento del corte 1 y sustentadas ante el
profesor. Si hay que cambiarlas, primero se actualiza el documento.

1. **La difusión va a la dirección de la malla**, nunca a 255.255.255.255, y
   el socket se ata a `bat0` con `SO_BINDTODEVICE`. Sin eso los mensajes
   salen por otra interfaz y no entran a la malla.
2. **Los datagramas UDP se mantienen bajo 1400 bytes.** batman-adv agrega su
   cabecera a cada trama. Lo que no cabe va por TCP.
3. **Cada mensaje TCP lleva su longitud en 4 bytes al inicio.** TCP es un
   flujo, no mensajes. Sin eso dos mensajes seguidos llegan pegados.
4. **Dos umbrales de fallo, no uno.** 15 s SOSPECHOSO, 30 s INACTIVO. En una
   malla Wi-Fi la señal se degrada seguido y declarar muerto a alguien que
   solo se demoró sale caro.
5. **La IP del vecino se toma de dónde llegó el paquete**, no del payload.
6. **Los HEARTBEAT no se escriben como líneas de log**, solo se cuentan. Si no,
   el archivo se vuelve ilegible en minutos.

## Reparto del trabajo

**Juan:** todo `src/` (api, communication, discovery, monitoring,
resources, scheduler, tasks) y la aplicación 1, `applications/mensajeria.py`.
No hay módulo `failure_detection/` aparte: la detección vive en el
descubrimiento (decisiones 4 y 15).

**El compañero:** solo la aplicación 2, regresión lineal, escrita sobre
`Nodo` (`registrar_operacion` y `enviar_tarea_async`; ejemplo en
`docs/api/manual.md` §9.4). No tocar sus archivos sin avisarle.

**Aplicación 3** (sensores de movimiento): todavía no se empieza. El panel
de monitoreo existe en terminal (`applications/monitor.py`, manual §11).

La frontera con la aplicación de regresión es la clase `Nodo`: no debe
necesitar nada de las capas de abajo.

## Modelo matemático

Definido en el corte 1 e implementado en `resources/` y `scheduler/`:

```
G(t) = (V(t), E(t))                          red como grafo dinámico
Si(t) = [Ci, Mi, Bi, Ri, Ai]                 estado del nodo, todo entre 0 y 1
F(i,j) = w1·Ci + w2·Mi + w3·Bi + w4·Ri − w5·Li
i* = argmax F(i,j)
```

`Bi` sale del TQ de batman-adv dividido entre 255. `Ai` filtra candidatos
(< 0.2 no recibe tareas), `Ri` es el mínimo entre lo publicado y la
reputación vista por el solicitante, y `Li` suma lo ya asignado sin respuesta
(decisión 19).

## Pendiente

- Decidir si la decisión 1 se hace cumplir: hoy, si no hay difusión de bat0,
  cae a 255.255.255.255, y si `SO_BINDTODEVICE` falla, sigue sin avisar.
  Primero hay que actualizar el documento del corte 1.
- `HELLO_ACK` se responde en difusión; con muchos nodos convendría unicast.
- Prueba de topología real en las Pi (A–B–C en línea), en `docs/api/manual.md` §8.
- Video y presentación. Estado de cada entregable en `docs/entregables_corte2.md`.
