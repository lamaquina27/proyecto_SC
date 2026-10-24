# Decisiones de diseño de la capa de comunicación, descubrimiento y registro

Por convención, el código de `src/` no lleva comentarios: el porqué de cada
decisión está aquí. Las decisiones 1 a 6 vienen del documento del corte 1 y
no se cambian sin actualizarlo primero. Las demás se tomaron en el corte 2.

## Decisiones del corte 1

### 1. La difusión va a la dirección de la malla, atada a bat0

La difusión se manda a la dirección de difusión de `bat0` (por ejemplo
`10.10.0.255`), que `malla.difusion_de()` le pregunta al sistema operativo.
Nunca se usa `255.255.255.255`, porque ese broadcast general sale por
cualquier interfaz (la Ethernet, la eth0 de un contenedor) y puede no entrar a
la malla. Por la misma razón, los sockets se atan a `bat0` con
`SO_BINDTODEVICE`.

**Pendiente de decidir:** hoy, si no se encuentra la difusión de bat0, el
código cae a `255.255.255.255` (`transporte.py`, constructor). Además, si
`SO_BINDTODEVICE` falla por falta de permisos, se sigue sin avisar. Ambas
cosas contradicen esta decisión. La propuesta es que en `bat0` el nodo se
niegue a arrancar y en `lo` siga como hoy. No se ha cambiado porque toca una
decisión ya sustentada.

### 2. Datagramas UDP de máximo 1400 bytes

batman-adv le agrega su cabecera a cada trama, y por eso `bat0` queda con
menos MTU que la interfaz física de abajo. Un datagrama que se pasa se
fragmenta, y basta con que se pierda un fragmento para perder el datagrama
entero. Lo que no cabe se manda por TCP.

Desde el corte 2 el límite también se lee del MTU real (ver la decisión 9).

### 3. Enmarcado TCP con la longitud en 4 bytes

TCP entrega un flujo de bytes, no mensajes separados. Si no se marca dónde
termina cada mensaje, dos mensajes seguidos llegan pegados o uno llega
partido, y el JSON no se puede leer. En una malla de varios saltos los
paquetes llegan partidos con más frecuencia. Por eso cada mensaje va precedido
de su longitud en 4 bytes (big-endian) y el receptor lee exactamente esa
cantidad (`_leer_exacto`). Un mensaje que anuncie más de 4 MB se descarta, para
que un encabezado dañado no llene la memoria.

### 4. Dos umbrales de fallo: 15 s y 30 s

En una malla Wi-Fi la señal se degrada con frecuencia. Si se declarara muerto
a un nodo al primer silencio, el planificador reasignaría tareas de un nodo que
solo se demoró. Por eso hay dos pasos:

- 15 s sin noticias: **SOSPECHOSO**. No recibe tareas nuevas, pero se le
  espera.
- 30 s sin noticias: **INACTIVO**. Se avisa a `cuando_salga`.

Si un SOSPECHOSO vuelve a hablar, pasa a ACTIVO **sin** avisar a
`cuando_entre`, porque nunca salió. Solo un INACTIVO que vuelve cuenta como
entrada nueva.

### 5. La IP del vecino se toma del paquete

La IP de un vecino es la dirección de origen del paquete que llegó, no lo que
diga el mensaje. Así el sistema funciona aunque el otro nodo tenga mal
configurada su propia IP, y un mensaje no puede hacerse pasar por otra
dirección.

### 6. Los HEARTBEAT se cuentan, no se escriben

Con un latido cada 5 s por nodo, escribir cada uno llenaría el archivo en
minutos y taparía los eventos importantes. `Registro.observar()` los cuenta
en `heartbeat_recibidos` y el total queda en la línea de `metricas` que se
escribe al cerrar.

## Decisiones del corte 2

### 7. Multicast a nivel de aplicación

El enunciado pide unicast, multicast y broadcast. El multicast se implementó
como **grupos con nombre** sobre lo que ya existía, y no con multicast IP
(direcciones `224.x.x.x` e IGMP).

- Un nodo se une a un grupo con `unirse("rescate")`. Sus grupos viajan en cada
  HEARTBEAT, así que los demás saben quién es miembro.
- **Mensaje corto:** una sola difusión UDP con el campo `group`. Cada nodo que
  no pertenece al grupo lo descarta al recibirlo, igual que ya se descartaban
  los mensajes con otro `receiver`.
- **Mensaje largo:** un envío TCP a cada miembro activo conocido, en paralelo.

¿Por qué no multicast IP? batman-adv, en una malla pequeña, termina
inundando el tráfico multicast casi igual que un broadcast. Tampoco
ahorraría tráfico, y en cambio exige configurar rutas e IGMP en cada Pi. Con
3 a 10 nodos, filtrar la difusión da el mismo resultado con menos piezas.

Una ventaja extra: el camino UDP no depende del descubrimiento. Un miembro
recién llegado, que el emisor todavía no conoce, igual recibe el mensaje.

### 8. Un envío TCP fallido avisa y reintenta

Antes, un fallo de TCP solo imprimía el error. Ahora `enviar()` reintenta dos
veces, esperando 0,5 s y luego 1 s, porque en una malla Wi-Fi muchos fallos
son momentáneos. Si igual falla:

- devuelve `None`, como antes;
- suma 1 a `fallos_envio`;
- avisa a cada función registrada con `cuando_falle(funcion)`. El registro la
  usa para escribir un evento `fallo_envio`.

Reintentar tiene un riesgo: que el mensaje llegue dos veces si el primer
intento sí llegó pero el emisor no se enteró. Por eso el receptor recuerda los
últimos 1024 `(sender, message_id)` y descarta los repetidos (contador
`duplicados`). Un reintento reutiliza el mismo mensaje y, por tanto, el mismo
`message_id`.

### 9. El límite UDP se lee del MTU de bat0

`limite_udp(mtu)` calcula `mín(1400, MTU − 28)`. Los 28 bytes son las
cabeceras IP (20) y UDP (8). Si bat0 reporta 1500, el límite sigue en 1400 y
la decisión 2 se cumple. Si alguna Pi queda con un MTU menor, el límite baja
solo. Si no se puede leer el MTU (Windows, interfaz que no existe), se usa
1400.

### 10. El latido nunca se detiene

Antes, si el HEARTBEAT no cabía en un datagrama (por ejemplo porque el estado
creció), la excepción mataba el hilo del latido. El nodo seguía vivo pero
callado, y a los 30 s los vecinos lo daban por muerto.

Desde la decisión 14 el estado ya no viaja en el HEARTBEAT, así que el
latido es pequeño. Aun así, si no cabe se manda solo con nombre y puerto, lo
mínimo para seguir vivo. Si el que no cabe es el RESOURCE_UPDATE, se avisa
una vez y se omite: los demás no ven el estado, pero el nodo sigue ACTIVO.
Cualquier otro error dentro del ciclo se imprime y el ciclo sigue.

### 11. Tiempos con reloj monotónico

Los silencios se miden con `time.monotonic()`, no con `time.time()`. La
Raspberry Pi no tiene reloj con batería y sin internet no hay NTP, así que la
hora del sistema puede saltar. Con `time.time()` un salto de 30 s haría que
todos los vecinos pasaran a INACTIVO a la vez. `monotonic()` solo avanza.

`time.time()` se sigue usando en el `timestamp` de los mensajes y en el
registro, porque ahí sí interesa la hora legible. El orden entre nodos lo da
el reloj de Lamport, que aparece en cada línea del registro.

### 12. El registro depende del descubrimiento, no al revés

`monitoring/` se engancha a los avisos que ya exponen las otras dos capas
(`al_recibir`, `cuando_falle`, `cuando_entre`, `cuando_sospeche`,
`cuando_salga`). Ni `communication/` ni `discovery/` saben que existe, así que
se pueden probar sin él.

### 13. Un nodo que no puede abrir sus puertos no arranca

Antes, si el puerto TCP estaba ocupado, el hilo de escucha imprimía el error
y terminaba, pero el nodo seguía anunciándose con ese puerto. Los demás le
mandaban mensajes directos que le llegaban al otro programa dueño del puerto,
y nadie se enteraba. Lo descubrió la prueba de la aplicación con tres nodos
que arrancaban a la vez en un mismo equipo. Ahora `iniciar()` espera a que
los dos sockets estén abiertos y, si alguno falla, lanza `OSError`.

En Windows hay una diferencia: ahí `SO_REUSEADDR` permite que dos programas
escuchen en el mismo puerto TCP, así que el error nunca saltaba. Por eso, en
Windows el socket TCP usa `SO_EXCLUSIVEADDRUSE`. El UDP sigue con
`SO_REUSEADDR` en todos los sistemas, porque ahí sí se quiere que varios
nodos del mismo equipo compartan el puerto y reciban la difusión.

## Alineación con el documento del corte 1

Las decisiones 14 a 17 hacen que el código siga lo que prometió el documento
del corte 1 (tabla "Tipos de mensajes", tabla "Operaciones disponibles en la
API", diagrama de arquitectura y UML).

### 14. HEARTBEAT y RESOURCE_UPDATE van separados

Como en la tabla de tipos del corte 1: el HEARTBEAT (detección de fallos)
solo dice "sigo vivo" y el RESOURCE_UPDATE (recursos) lleva el vector de
estado. Los dos salen cada 5 s por defecto, pero el de recursos tiene su
propio intervalo (`t_recursos`) y se puede forzar con `publicar_recursos()`,
por ejemplo cuando cambia la carga.

Separarlos cuesta un datagrama más cada 5 s, pero tiene dos ventajas. El
latido queda pequeño, así que nunca deja de caber (decisión 10). Y la parte
de recursos puede publicar más o menos seguido sin tocar la detección de
fallos.

Cualquier mensaje de un vecino cuenta como señal de vida, no solo el
HEARTBEAT.

### 15. NODE_STATUS informa, no ordena

El corte 1 dice que NODE_STATUS "informa cambios en el estado de un nodo". Se
manda cada vez que la vigilancia de un nodo cambia el estado de un vecino.
Hay tres reglas:

1. **Quien lo recibe no cambia su tabla.** Cada nodo decide quién está vivo
   con lo que él mismo oye. Si se obedecieran los reportes, un solo nodo con
   mala señal haría que toda la red sacara a alguien que sigue vivo, y en
   una malla Wi-Fi eso pasaría seguido. Es la misma razón de los dos
   umbrales (decisión 4).
2. **Sí se avisa y se registra** (`cuando_reporten`, evento
   `reporte_estado`). La recuperación de tareas puede prepararse antes de
   que su propio umbral se cumpla.
3. **Si el reporte es sobre uno mismo**, se responde de inmediato con un
   HEARTBEAT. Una sospecha falsa se corrige en milisegundos en vez de
   esperar al siguiente latido. Es la misma idea de la "refutación" de los
   protocolos de membresía como SWIM.

Con N nodos, cada cambio genera hasta N−1 reportes. Como solo se mandan
cuando algo cambia, el costo es bajo.

### 16. El identificador sobrevive a los reinicios (RF01)

El RF01 pide un identificador único "para poder reconocerlo dentro de la
red". Antes se generaba uno nuevo en cada arranque: un nodo que se reiniciaba
aparecía como un nodo nuevo y el viejo quedaba INACTIVO, y la parte de
recuperación lo habría tratado como una caída de verdad. Ahora el `node_id`
se guarda en `~/.complexnet/<nombre>.id` y se reutiliza. Un reinicio se
sigue detectando porque `seq` vuelve a empezar (el estado guardado del vecino
se limpia).

### 17. La capa 4 es una fachada, no una capa nueva de lógica

`src.api.Nodo` no agrega comportamiento: junta `ServicioMensajes`,
`ServicioDescubrimiento` y `Registro` y expone las operaciones del corte 1
con los nombres del UML. Así cumple lo de "esconder todo lo de abajo" sin
duplicar código. "Mandar una tarea" (`enviar_tarea`, el `submit()` del
diagrama) se delega en `GestorTareas` (decisiones 18 a 22). La aplicación de
regresión solo usa `Nodo`.

## Recursos, planificador y tareas

### 18. El vector de estado completo y cómo se mide

`GestorRecursos.medir()` publica, todo entre 0 y 1:

| Variable | Clave | Cómo se mide |
|---|---|---|
| Ci | `cpu` | 1 − uso de CPU (psutil; si no hay, carga promedio / núcleos; si tampoco, 0.5) |
| Mi | `memoria` | Memoria disponible / total (psutil o `/proc/meminfo`) |
| Bi | `ancho_banda` | Promedio del TQ de batman-adv / 255 (1.0 si no hay `batctl`) |
| Ri | `confiabilidad` | Tareas que el nodo terminó bien: (éxitos + 1) / (total + 2) |
| Ai | `disponibilidad` | Batería / 100 si funciona con batería; 1.0 si está conectado o no hay sensor |
| Li | `carga` | Tareas en curso / capacidad (`max_tareas`, por defecto 2) |
| — | `almacenamiento` | Disco libre / total (RF04 lo nombra) |
| — | `capacidad` | `max_tareas`, para que el planificador pueda estimar la carga |

El "+1 / +2" de la confiabilidad (suavizado de Laplace) hace que un nodo sin
historia empiece en 0.5, neutral, y no en 0 ni en 1. Un solo fallo no lo
hunde y un solo éxito no lo vuelve perfecto.

Cuando no se puede medir algo, se usa 0.5 (neutral) en lugar de fallar.

### 19. Cómo se aplica F(i, j)

F(i,j) = w1·C + w2·M + w3·B + w4·R − w5·L, con todos los pesos en 1.0 por
defecto (configurables con `Nodo(pesos={...})`). Tres detalles:

1. **A es un filtro, no un término.** La fórmula del corte 1 no incluye A,
   pero el RF08 pide tener en cuenta la disponibilidad. Un nodo con A < 0.2
   (casi sin batería) no es candidato: si se le asigna una tarea, lo más
   probable es que se apague a la mitad.
2. **R = mín(lo que el nodo dice, lo que yo he visto).** Cada solicitante
   lleva su propia cuenta de cuántas veces le cumplió o le falló cada
   vecino. Un nodo que se cayó no puede reportar su propio fallo, así que
   la experiencia propia es más confiable que la publicada. *Para la
   sustentación:* "si yo vi que me falló, no le creo cuando dice que es
   confiable".
3. **L incluye lo que ya le mandé.** El RESOURCE_UPDATE llega cada 5 s.
   Sin este ajuste, cuatro tareas lanzadas a la vez caerían en el mismo
   nodo porque todavía no publicó su carga nueva. Por eso
   L = mín(1, carga publicada + tareas que le asigné y no han vuelto /
   capacidad).

El UML lista `pesoLatencia`, pero la fórmula del modelo matemático usa la
carga L. Se siguió la fórmula, que es la que está sustentada.

### 20. El flujo de una tarea

Sigue el del corte 1: Aplicación → API → Task Manager → Distributed
Scheduler → Nodo seleccionado → Ejecución → Resultado.

1. `nodo.enviar_tarea("suma", [10, 20])` crea una `Tarea`. Los requisitos son,
   por defecto, el nombre de la operación.
2. **Paso 1:** `que_ofrezcan(requisitos)` deja solo a los vecinos ACTIVOS
   que saben hacerla. **Paso 2:** el planificador escoge i* = argmax F.
3. **TASK_ASSIGN** por TCP al escogido.
4. El ejecutor la pone en su cola (hasta `max_tareas` a la vez), publica su
   carga nueva y, al terminar, devuelve **TASK_RESULT** por TCP.
5. `enviar_tarea` devuelve el resultado. La aplicación no sabe quién lo
   ejecutó, como pide el corte 1. Si quiere saberlo, `enviar_tarea_async`
   da un `Future` con la tarea, el ejecutor y el historial.

**TASK_REQUEST** ("solicita a la red la ejecución de una tarea") se usa
cuando el solicitante no conoce a nadie que la ofrezca. Por ejemplo, un nodo
recién llegado, o un servicio que se acaba de publicar y todavía no viajó en
un latido. Se difunde con los requisitos; quien sabe hacerla se anuncia de
inmediato (HEARTBEAT + RESOURCE_UPDATE), y el solicitante vuelve a escoger
después de 1 s. Si sigue sin haber nadie y el propio nodo sabe hacerla, la
ejecuta él mismo. Si no, la tarea falla con un mensaje claro.

Una operación se publica con `nodo.registrar_operacion(nombre, funcion)`.
`funcion(datos)` recibe y devuelve JSON.

### 21. Reasignación (RF11)

`GestorRecuperacion` (el "Recovery Manager" del corte 1) reasigna una tarea
en tres casos:

| Caso | Cuándo se detecta | Motivo en el registro |
|---|---|---|
| El ejecutor se cae | `cuando_salga`: INACTIVO (30 s) o GOODBYE | `nodo_caido` |
| No se le pudo entregar | Falla el TCP del TASK_ASSIGN | `no_entregada` |
| Se demora más de `timeout` | Revisión cada 0,5 s | `tiempo_agotado` |

En los tres casos el nodo queda excluido para esa tarea, baja su reputación
y se escoge al siguiente por F. Hay un máximo de `intentos` (3 por defecto).

Un SOSPECHOSO **no** dispara la reasignación, por la misma razón de la
decisión 4: declarar muerto a alguien que solo se demoró sale caro. Para
tareas urgentes, el `timeout` de la tarea es el que manda.

Hay dos casos que **no** se reasignan:
- **Error dentro de la función** (por ejemplo, división por cero): se
  repetiría igual en cualquier nodo. La tarea falla con el error.
- **"No sé hacer eso"**: el ejecutor no tiene la operación. Se reasigna sin
  bajarle la reputación.

### 22. El primer resultado válido gana

Si una tarea se reasignó por tiempo y el primer ejecutor termina después,
llegan dos resultados. Se acepta el primero que llegue y el otro se ignora.
Como la operación da lo mismo en cualquier nodo, da igual cuál gane, y así
nunca se espera de más. Esto supone que las operaciones no tienen efectos
secundarios (calcular, no escribir en un archivo), lo cual se cumple para la
suma y para la regresión.

## Envío de archivos

### 23. Archivos en trozos sobre el TCP enmarcado, con huella al final

En una zona de desastre se necesita pasar fotos de daños, mapas y listas de
personas entre nodos. Un archivo no cabe en un datagrama (decisión 2) y puede
pasar del máximo de 4 MB de un mensaje TCP, así que se parte en trozos de
256 KB que viajan como mensajes `FILE_CHUNK` normales.

- **Reusar el TCP enmarcado** (decisión 3) en vez de abrir un canal binario
  aparte: cada trozo hereda los reintentos y el aviso de fallo (decisión 8)
  sin código nuevo. El costo es base64, un 33 % más de bytes, que se acepta
  a cambio de no tener dos protocolos.
- **Cada trozo lleva su posición.** Cada conexión TCP se atiende en su propio
  hilo, así que dos trozos seguidos pueden procesarse en otro orden. El
  receptor escribe en la posición y no le importa el orden.
- **Va a disco, no a memoria.** Una Raspberry Pi no debe guardar un video
  entero en RAM mientras llega.
- **SHA-256 y confirmación (`FILE_ACK`).** Que cada trozo llegue no prueba
  que el archivo esté completo y sano. El receptor compara la huella y
  responde; quien envía solo da el archivo por entregado con esa respuesta.
- **Sin reanudación.** Si el destino se cae a la mitad, se vuelve a enviar
  desde cero, y lo que quedó a medias se borra a los 120 s. Reanudar pediría
  que el receptor recuerde transferencias entre reinicios; se deja para
  cuando haya archivos tan grandes que lo justifiquen.
- **El nombre lo limpia el receptor.** Solo se toma la parte final, para que
  un nombre como `../../algo` no escriba fuera de la carpeta, y nunca se pisa
  un archivo que ya estaba.

## Monitoreo

### 24. Las tareas en curso viajan en el RESOURCE_UPDATE

Para ver en vivo qué ejecuta cada nodo, el estado que ya se difunde
(decisión 18) suma `hechas`, `fallidas`, `en_cola` y la lista `tareas`:
`[tarea_id, operacion, solicitante, estado, segundos]`.

- **Sin un tipo de mensaje nuevo.** El ejecutor ya publica su
  `RESOURCE_UPDATE` al recibir y al terminar cada tarea (para que la carga Li
  se vea enseguida), así que la lista llega justo cuando cambia, sin tráfico
  extra. También se publica cuando una tarea que esperaba en cola empieza a
  correr.
- **Máximo 6 tareas en la lista.** El `RESOURCE_UPDATE` tiene que caber en un
  datagrama (decisión 2). Seis entradas son unos 300 bytes. Con más, el total
  sigue saliendo en la carga y en `en_cola`.
- **El monitor es un observador.** `applications/monitor.py` entra a la red
  como un nodo sin operaciones: el planificador solo escoge entre quienes
  ofrecen la operación (decisión 20), así que nunca recibe tareas. No hace
  falta un servidor central: cualquier equipo de la malla puede abrir un
  monitor y ve lo mismo que los demás.
- **"Recibió" y "terminó" se deducen** comparando cada lista con la anterior
  del mismo nodo, por el `tarea_id`. Si se pierde un datagrama, el cambio se
  ve con el siguiente `RESOURCE_UPDATE` (a lo sumo 5 s después).

### 25. Las operaciones de la mensajería: `calcular` y `estresar`

La suma del corte 1 se reemplazó por `calcular`, que acepta cualquier
expresión matemática (la suma es un caso). Se interpreta con `ast` y una lista
cerrada de operadores y funciones: con `eval`, cualquier nodo de la malla
podría ejecutar código en otro.

`estresar` existe para la demostración: hace visible en el monitor lo que le
cuesta a cada nodo una tarea repartida. Corre en un proceso aparte porque en
un mismo proceso de Python dos hilos no ocupan dos núcleos a la vez (GIL): con
hilos, `max_tareas = 2` se vería como un solo núcleo ocupado. El número de
procesos lo sigue limitando `max_tareas`, porque cada trabajador de la cola
espera a su proceso.

El tiempo máximo de cada parte es `seg · (partes + 1) + 15` s. Así una parte
que espera en la cola de un nodo ocupado no se reasigna por tiempo
(decisión 21) antes de empezar.
