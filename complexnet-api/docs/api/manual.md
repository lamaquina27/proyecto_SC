# Manual técnico: comunicación, descubrimiento, registro y API

ComplexNet API, corte 2. Este manual cubre los paquetes `src/api` (capa 4),
`src/communication`, `src/discovery` y `src/monitoring`. El porqué de cada
decisión está en [`../diseno.md`](../diseno.md).

**Si solo va a escribir una aplicación, lea la sección 0 y nada más.**

## 0. Capa 4: la clase `Nodo`

Es "la API para el programador" del documento del corte 1. Esconde todo lo
de abajo: quien la usa no toca sockets ni servicios.

```python
from src.api import Nodo

with Nodo("nodo-01", servicios=["sensor"]) as nodo:     # unirse a la red
    nodo.al_recibir("ALERTA", lambda m, ip: print(m.payload))
    print(nodo.consultar_estado_red())                   # quién está
    nodo.enviar_mensaje("nodo-02", {"texto": "hola"})    # a uno
    nodo.difundir({"texto": "réplica en 5 min"})         # a todos
    nodo.enviar_a_grupo("rescate", {"zona": "norte"})    # a un grupo
```

### Correspondencia con el documento del corte 1

| Operación de la tabla "Operaciones disponibles en la API" | Método |
|---|---|
| Unirse a la red | `Nodo(...).iniciar()` (o `with Nodo(...) as nodo`) |
| Ver quién está conectado | `consultar_estado_red(incluir_caidos=False)` |
| Mandar una tarea | `enviar_tarea(operacion, datos)` (el `submit()` de la capa 4); `registrar_operacion(nombre, funcion)` para ofrecerla |
| Mandar un mensaje | `enviar_mensaje(destino, datos)`, `difundir(datos)`, `enviar_a_grupo(grupo, datos)` |
| Publicar un servicio | `publicar_servicio(nombre)` |
| Reaccionar a eventos | `al_recibir(tipo, f)`, `cuando_entre(f)`, `cuando_sospeche(f)`, `cuando_salga(f)`, `cuando_reporten(f)`, `cuando_falle(f)` |

| Clase del diagrama UML | Equivalente |
|---|---|
| `Nodo`: `idNodo`, `direccionIP`, `puerto`, `activo` | `node_id`, `ip`, `puerto`, `activo` |
| `Nodo`: `iniciar()`, `detener()`, `obtenerEstado()`, `enviarMensaje()` | `iniciar()`, `detener()`, `obtener_estado()`, `enviar_mensaje()` |
| `API_Desarrollador`: `crearNodo()` | `Nodo(...)` |
| `API_Desarrollador`: `enviarMensaje()`, `crearTarea()` | `enviar_mensaje()`, `enviar_tarea()` |
| `API_Desarrollador`: `consultarRecursos()`, `consultarEstadoRed()` | `consultar_recursos()`, `consultar_estado_red()` |
| `ServicioMensajes`, `ServicioDescubrimiento`, `RegistradorMonitor` | `nodo.mensajes`, `nodo.descubrimiento`, `nodo.registro` |
| `GestorRecursos`, `Recurso` | `nodo.recursos` (sección 9) |
| `PlanificadorDistribuido` | `nodo.planificador` (sección 9) |
| `GestorTareas`, `GestorRecuperacion`, `Tarea` | `nodo.tareas`, `nodo.tareas.recuperacion` (sección 9) |
| `DetectorFallos` | Dentro de `ServicioDescubrimiento` (umbrales y NODE_STATUS) |

### Constructor

```python
Nodo(nombre=None, interfaz="bat0", difusion=None, puerto_udp=5000,
     puerto_tcp=5001, servicios=None, leer_estado=None, carpeta_logs="logs",
     carpeta_id=None, node_id=None, t_hello=5.0, t_sospecha=15.0,
     t_muerte=30.0, max_tareas=2, pesos=None)
```

| Parámetro | Descripción |
|---|---|
| `nombre` | Por defecto, el nombre del equipo. |
| `leer_estado` | Función que mide el vector de recursos. Por defecto `nodo.recursos.medir` (sección 9). Solo se cambia para pruebas. |
| `carpeta_logs` | Dónde escribir el registro; `None` para no escribir. |
| `carpeta_id`, `node_id` | Ver "Identidad" más abajo. |
| `max_tareas` | Cuántas tareas ajenas ejecuta a la vez; el resto espera en cola. |
| `pesos` | Pesos de F(i,j), por ejemplo `{"cpu": 2.0, "carga": 1.5}`. Claves: `cpu`, `memoria`, `ancho_banda`, `confiabilidad`, `carga`. |

### Métodos

| Método | Devuelve |
|---|---|
| `iniciar()` | El propio nodo. Lanza `OSError` si un puerto está ocupado. |
| `detener(despedirse=True)` | — . Con `False` simula una caída (sin GOODBYE). |
| `obtener_estado()` | Diccionario con `node_id`, `nombre`, `ip`, `puerto`, `activo`, `servicios`, `grupos`, `recursos`, `trafico`. |
| `consultar_estado_red(incluir_caidos=False)` | Lista de vecinos (como `ServicioDescubrimiento.resumen()`), solo ACTIVOS por defecto. |
| `consultar_recursos(destino=None)` | Con destino: el `estado` de ese nodo, o `None`. Sin destino: `{node_id: estado}` de los activos. |
| `buscar(destino)` | El `Vecino`, buscado por `node_id` o por nombre. |
| `enviar_mensaje(destino, datos, tipo="APP_MSG", **opciones)` | `True` si se entregó. Lanza `LookupError` si no conoce el destino. `opciones` pasa a `enviar()` (`timeout`, `reintentos`). |
| `difundir(datos, tipo="APP_MSG")` | Igual que `enviar_a_grupo`: `{"via": "udp", ...}` o, si no cabe, TCP a todos los activos con `entregados` y `fallidos`. |
| `enviar_a_grupo(grupo, datos, tipo="APP_MSG")` | Ver 4.4. |
| `unirse_a_grupo(g)`, `salir_de_grupo(g)` | — |
| `publicar_servicio(nombre)`, `que_ofrezcan(servicios)` | Ver 4.2 y 4.5. |
| `registrar_operacion(nombre, funcion)` | Este nodo sabe hacer `nombre`: lo publica como servicio y ejecuta `funcion(datos)` cuando se lo pidan. |
| `enviar_tarea(operacion, datos=None, requisitos=None, timeout=30.0, intentos=3, prioridad=0)` | El resultado. Bloquea hasta tenerlo. Lanza `TareaFallida` si no se pudo. |
| `enviar_tarea_async(...)` | Igual, pero devuelve un `Future` al instante. `futuro.result()` espera; `futuro.tarea` tiene `ejecutor`, `historial` e `intentos`. |

**Para la aplicación de regresión:** ver el ejemplo en la sección 9.4.

### Identidad (RF01)

El `node_id` se guarda en `~/.complexnet/<nombre>.id` la primera vez y se
reutiliza en cada arranque. Si el nodo se reinicia, los demás lo reconocen
como el mismo y no como un nodo nuevo. `carpeta_id` cambia la carpeta y
`node_id` fuerza uno a mano. Dos nodos con el **mismo nombre en el mismo
equipo** comparten identidad y se ignorarían entre sí: en un mismo equipo,
use nombres distintos.

## 1. Arquitectura en una página

```
   aplicaciones                       applications/mensajeria.py, regresión ...
             │
   ┌─────────▼──────────┐
   │ api: Nodo (capa 4) │  enviar_mensaje(), difundir(), enviar_tarea() ...
   └─────────┬──────────┘
             │  que_ofrezcan(), enviar_a_grupo(), cuando_entre() ...
   ┌─────────▼──────────┐       ┌─────────────────┐
   │ discovery          │◄──────┤ monitoring      │ se engancha a los avisos
   │ ServicioDescubri-  │       │ Registro        │ y escribe logs/<nodo>.jsonl
   │ miento, Vecino     │       └────────▲────────┘
   └─────────┬──────────┘                │
             │ difundir(), multidifundir(), al_recibir()
   ┌─────────▼──────────┐                │
   │ communication      │────────────────┘
   │ ServicioMensajes   │  UDP en difusión (corto)  ·  TCP enmarcado (largo)
   └─────────┬──────────┘
             │ bat0  (batman-adv enruta)
```

Cada nodo corre un `ServicioMensajes`, un `ServicioDescubrimiento` encima y,
opcionalmente, un `Registro` observando a los dos. No hay servidor central:
cada nodo arma su propia tabla de vecinos con lo que le llega.

### Puertos

| Uso | Protocolo | Puerto por defecto |
|---|---|---|
| Difusión y multicast | UDP | 5000 |
| Mensajes directos | TCP | 5001 |

En la malla real todos los nodos usan los mismos puertos. Solo cuando varios
nodos corren en el mismo equipo hace falta un puerto TCP distinto por nodo.
El puerto UDP se comparte gracias a `SO_REUSEADDR`.

## 2. Formato del mensaje

Todos los mensajes, sin importar el tipo, tienen la misma envoltura JSON:

```json
{
  "message_id": "3f9a1c02",
  "type": "HEARTBEAT",
  "sender": "a1b2c3d4",
  "receiver": null,
  "group": null,
  "timestamp": 1790000000.12,
  "seq": 42,
  "lamport": 107,
  "payload": { }
}
```

| Campo | Significado |
|---|---|
| `message_id` | 8 caracteres hex al azar. Sirve para detectar duplicados. |
| `type` | Tipo de mensaje. El receptor elige el manejador según este campo. |
| `sender` | `node_id` de quien lo envía. |
| `receiver` | `node_id` del destinatario, o `null` si es para todos. |
| `group` | Nombre del grupo (multicast), o `null`. |
| `timestamp` | Hora de envío según el emisor. Solo informativa, porque los relojes no están sincronizados. |
| `seq` | Contador del emisor. Si baja, el emisor se reinició. |
| `lamport` | Reloj lógico de Lamport. Da el orden causal entre nodos. |
| `payload` | Contenido libre (objeto JSON). |

Un nodo **acepta** un mensaje solo si se cumplen las tres condiciones:
`receiver` es nulo o es él; `group` es nulo o es uno de sus grupos; y no lo
había recibido ya (mismo `sender` y `message_id`). Si no, lo descarta y suma
1 a `descartados` o a `duplicados`.

Por TCP, cada mensaje va precedido de su longitud en 4 bytes (big-endian).
El máximo es 4 MB. Por UDP, el mensaje completo debe caber en `max_udp` bytes
(ver 3.1).

### Tipos de mensaje

Los de la tabla "Tipos de mensajes" del documento del corte 1, más GOODBYE.
Todos están definidos como constantes en `src.communication`.

| Tipo | Servicio | Quién lo manda | Payload |
|---|---|---|---|
| `HELLO` | Descubrimiento | Un nodo al arrancar, 3 veces | `nombre`, `puerto_tcp`, `servicios`, `grupos` |
| `HELLO_ACK` | Descubrimiento | Quien recibe un HELLO (y enseguida manda su RESOURCE_UPDATE) | igual que HELLO |
| `RESOURCE_UPDATE` | Recursos | Todos, cada `t_recursos` s (por defecto igual a `t_hello`), y al responder un HELLO | `nombre`, `puerto_tcp`, `estado` |
| `HEARTBEAT` | Detección de fallos | Todos, cada `t_hello` s | igual que HELLO (sin servicios ni grupos si no cabe) |
| `NODE_STATUS` | Detección de fallos | Quien ve cambiar el estado de un vecino | `node_id`, `nombre`, `status`, `anterior` |
| `GOODBYE` | Descubrimiento | Un nodo que se apaga en orden | `nombre` |
| `TASK_REQUEST`, `TASK_ASSIGN`, `TASK_RESULT` | Tareas | Definidos, los usa la parte de tareas | — |
| `ANUNCIO`, `PING`, `PONG`, `APP_MSG` | Demos y aplicaciones | — | libre |

Las aplicaciones pueden inventar tipos nuevos sin tocar el protocolo.

## 3. `communication.ServicioMensajes`

```python
from src.communication import ServicioMensajes

m = ServicioMensajes(node_id, interfaz="bat0", puerto_udp=5000,
                     puerto_tcp=5001, difusion=None)
m.iniciar()
...
m.detener()
```

| Parámetro | Descripción |
|---|---|
| `node_id` | Identificador único del nodo (texto). |
| `interfaz` | Interfaz de la malla. `"lo"` para pruebas locales. |
| `puerto_udp`, `puerto_tcp` | Puertos de escucha. |
| `difusion` | Dirección de difusión. Si es `None`, se lee de la interfaz. |

Atributos útiles: `ip`, `difusion`, `mtu`, `max_udp`, `reloj`, `seq`.

### 3.1 Broadcast: `difundir(tipo, payload=None)`

Manda un mensaje por UDP a todos los nodos de la malla.

- **Devuelve** el `Mensaje` enviado, o `None` si el sistema operativo
  rechazó el envío. En ese caso también avisa a `cuando_falle`.
- **Lanza** `MensajeMuyGrande` si el mensaje pasa de `max_udp` bytes.
  `max_udp = mín(1400, MTU(bat0) − 28)`. En ese caso hay que usar
  `enviar()`.
- **No garantiza la entrega.** Sirve para avisos cortos y frecuentes: si se
  pierde uno, llega el siguiente.

### 3.2 Multicast: `multidifundir(grupo, tipo, payload=None)`

Igual que `difundir`, pero solo lo aceptan los nodos que están en `grupo`.
Viaja en una sola difusión UDP y los demás nodos lo descartan al recibirlo.
Tiene los mismos límites y excepciones que `difundir`.

Si el mensaje puede ser grande, conviene usar
`ServicioDescubrimiento.enviar_a_grupo()` (sección 4.4), que elige solo entre
UDP y TCP.

### 3.3 Unicast: `enviar(ip, puerto, tipo, receiver=None, payload=None, timeout=5.0, reintentos=2, grupo=None)`

Manda un mensaje a un nodo por TCP. Llega completo y en orden, sin límite
práctico de tamaño (hasta 4 MB).

- Si la conexión falla, **reintenta** `reintentos` veces, esperando 0,5 s
  × número de intento.
- **Devuelve** el `Mensaje` si se entregó al TCP del otro lado, o `None` si
  fallaron todos los intentos.
- Cuando falla del todo, suma 1 a `fallos_envio` y llama a cada función
  registrada con `cuando_falle`. Si no hay ninguna, imprime el error.
- En el peor caso bloquea `(reintentos + 1) × timeout` segundos más las
  esperas (unos 16,5 s con los valores por defecto). Si eso es mucho para
  quien llama, hay que bajar `timeout` o `reintentos`.
- Un reintento que llegue repetido se descarta en el receptor por su
  `message_id`.

Conviene pasar siempre `receiver` con el `node_id` del destino. Si la IP ya
pertenece a otro nodo (por ejemplo después de un reinicio), ese nodo descarta
el mensaje en lugar de procesarlo por error.

### 3.4 Varios destinos: `enviar_a_varios(destinos, tipo, payload=None, grupo=None, timeout=5.0, reintentos=2)`

`destinos` es una lista de tuplas `(node_id, ip, puerto_tcp)`. Hace un
`enviar()` a cada destino en paralelo (hasta 8 a la vez).

**Devuelve** `{"entregados": [node_id, ...], "fallidos": [node_id, ...]}`.

### 3.5 Grupos

| Método | Descripción |
|---|---|
| `unirse(grupo)` | Empieza a aceptar mensajes de `grupo`. |
| `abandonar(grupo)` | Deja de aceptarlos. |
| `mis_grupos()` | Lista ordenada de los grupos propios. |

Si el nodo tiene descubrimiento, conviene usar los métodos del mismo nombre de
`ServicioDescubrimiento`, que además hacen que los grupos se anuncien en el
HEARTBEAT.

### 3.6 Recibir: `al_recibir(tipo, funcion)`

Registra `funcion(mensaje, ip_origen)` para los mensajes de ese tipo. Puede
haber varias funciones por tipo. `ip_origen` es la IP de donde llegó el
paquete (decisión 5). Si una función lanza una excepción, se imprime y las
demás se siguen llamando.

**Ojo:** las funciones se ejecutan en el hilo de recepción. Si una tarda
mucho, retrasa los mensajes que vienen detrás. El trabajo largo debe
hacerse en un hilo aparte.

### 3.7 Fallos: `cuando_falle(funcion)`

Registra `funcion(mensaje, ip, puerto, error)`. Se llama cuando un `enviar()`
agota los reintentos o cuando el sistema operativo rechaza una difusión.

### 3.8 Métricas: `metricas()`

Devuelve una copia del diccionario de contadores:

| Clave | Qué cuenta |
|---|---|
| `enviados` | Mensajes que salieron (UDP + TCP) |
| `recibidos` | Mensajes aceptados y repartidos |
| `descartados` | No eran para este nodo, venían mal formados o eran muy grandes |
| `duplicados` | Ya se habían recibido (mismo `message_id`) |
| `bytes_enviados`, `bytes_recibidos` | Tráfico, incluyendo la cabecera TCP |
| `fallos_envio` | Envíos que fallaron del todo |
| `reintentos` | Reintentos TCP hechos |

### 3.9 Ciclo de vida

`iniciar()` abre los sockets de escucha y devuelve el propio servicio. Si no
puede abrir el puerto UDP o el TCP (por ejemplo, porque otro nodo del mismo
equipo ya lo tiene), cierra todo y **lanza `OSError`** diciendo qué puerto
falló. Antes seguía funcionando a medias, sin TCP, sin que nadie se enterara.
`detener()` cierra los tres sockets y espera a los hilos, para que un
reinicio inmediato no choque con "Address already in use".

### 3.10 `communication.malla`

Funciones sueltas para consultar la interfaz. Todas devuelven `None` (o una
lista vacía) si no se puede averiguar, en lugar de fallar.

| Función | Devuelve |
|---|---|
| `ip_de(interfaz)` | IP de la interfaz |
| `difusion_de(interfaz)` | Dirección de difusión |
| `mtu_de(interfaz)` | MTU |
| `existe(interfaz)` | `True` si la interfaz tiene IP |
| `vecinos_batman()` | `[{"mac", "tq", "calidad"}]` según `batctl neighbors`, donde `calidad = TQ/255` es la variable Bi del modelo |
| `calidad_promedio()` | Promedio de `calidad`, o 1.0 si no hay datos |
| `resumen(interfaz)` | Todo lo anterior en un diccionario |

## 4. `discovery.ServicioDescubrimiento`

```python
from src.discovery import ServicioDescubrimiento

d = ServicioDescubrimiento(mensajes, node_id, "nodo-01",
                           leer_estado=funcion_que_devuelve_un_dict,
                           servicios=["sensor", "camara"],
                           t_hello=5.0, t_sospecha=15.0, t_muerte=30.0)
d.iniciar()
...
d.detener()
```

| Parámetro | Descripción |
|---|---|
| `mensajes` | El `ServicioMensajes` del nodo. |
| `nombre` | Nombre legible del nodo. |
| `leer_estado` | Función sin argumentos que devuelve el vector de recursos (sección 9.1). Se llama en cada RESOURCE_UPDATE. |
| `servicios` | Lo que el nodo sabe hacer. |
| `t_hello` | Segundos entre latidos. |
| `t_sospecha`, `t_muerte` | Umbrales de fallo (decisión 4). |
| `t_recursos` | Segundos entre RESOURCE_UPDATE. Por defecto, igual a `t_hello`. |

### 4.1 Cómo funciona

Es el flujo de la prueba de concepto del corte 1:

1. Al arrancar, el nodo manda 3 `HELLO`. Cada nodo que lo oye responde con
   `HELLO_ACK` y su `RESOURCE_UPDATE`, así que el nuevo conoce a todos, y su
   estado, en menos de un segundo.
2. Cada `t_hello` s, todos mandan `HEARTBEAT` ("sigo vivo") con su nombre,
   puerto, servicios y grupos.
3. Cada `t_recursos` s, todos mandan `RESOURCE_UPDATE` con su vector de
   estado. `publicar_recursos()` lo manda en el momento, por ejemplo cuando
   cambia la carga al recibir una tarea.
4. Cualquier mensaje de un vecino (no solo el HEARTBEAT) cuenta como señal
   de vida.
5. Cada segundo, un hilo de vigilancia revisa hace cuánto habló cada vecino
   y lo mueve de estado. Cada cambio se anuncia con `NODE_STATUS` (4.7):

```
            silencio > t_sospecha        silencio > t_muerte
  ACTIVO ─────────────────────► SOSPECHOSO ─────────────────► INACTIVO
    ▲  ▲       (cuando_sospeche)     │        (cuando_salga)       │
    │  └─────── vuelve a hablar ─────┘  (sin aviso)                │
    └────────────────── vuelve a hablar (cuando_entre) ────────────┘

  GOODBYE: se borra de la tabla al instante (cuando_salga)
```

### 4.2 Consultas

| Método | Devuelve |
|---|---|
| `que_ofrezcan(servicios)` | Vecinos ACTIVOS que ofrecen **todos** los servicios pedidos. Es el paso 1 del planificador. |
| `miembros(grupo)` | Vecinos ACTIVOS que están en `grupo`. |
| `activos()` | Vecinos ACTIVOS. |
| `todos()` | Todos, incluidos SOSPECHOSOS e INACTIVOS. |
| `buscar(node_id)`, `por_nombre(nombre)` | Un `Vecino`, o `None`. |
| `resumen()` | Lista de diccionarios, lista para mostrar o convertir a JSON. |

Cada `Vecino` tiene: `node_id`, `nombre`, `ip`, `puerto_tcp`, `servicios`,
`grupos`, `estado` (el vector de recursos), `status` y `silencio()`.

### 4.3 Avisos

| Método | Firma de la función | Cuándo se llama |
|---|---|---|
| `cuando_entre(f)` | `f(vecino)` | Aparece un nodo nuevo o vuelve uno INACTIVO |
| `cuando_sospeche(f)` | `f(node_id)` | Un ACTIVO pasa a SOSPECHOSO |
| `cuando_salga(f)` | `f(node_id)` | Pasa a INACTIVO o manda GOODBYE |
| `cuando_reporten(f)` | `f(node_id, status, quien)` | Llega un `NODE_STATUS` de otro nodo (4.7) |

### 4.4 Enviar a un grupo: `enviar_a_grupo(grupo, tipo, payload=None)`

Elige solo el camino:

- Si el mensaje cabe en UDP, hace `multidifundir` y devuelve
  `{"via": "udp", "mensaje": m}`.
- Si no cabe, hace `enviar_a_varios` a los `miembros(grupo)` y devuelve
  `{"via": "tcp", "entregados": [...], "fallidos": [...]}`.

Diferencia importante: por UDP le llega a cualquier miembro, aunque el
emisor todavía no lo haya descubierto. Por TCP solo le llega a los miembros
que el emisor ya ve como ACTIVOS.

### 4.5 Publicar

| Método | Efecto |
|---|---|
| `publicar_servicio(nombre)` | Agrega un servicio; sale en el siguiente latido. |
| `unirse(grupo)`, `abandonar(grupo)` | Cambia los grupos del nodo; salen en el siguiente latido. |

### 4.6 Apagar: `detener(despedirse=True)`

Con `despedirse=True` manda un `GOODBYE` y los demás lo sacan de la tabla al
instante. Con `False` simula una caída (se usa en las pruebas): los demás lo
detectan por los umbrales. Un descubrimiento detenido ignora todo lo que
llegue, aunque `ServicioMensajes` siga abierto.

### 4.7 `NODE_STATUS`: informar los cambios de estado

Cuando la vigilancia de un nodo cambia el estado de un vecino (ACTIVO →
SOSPECHOSO, → INACTIVO, o de vuelta a ACTIVO), lo anuncia por difusión:

```json
{"node_id": "b2c3d4e5", "nombre": "nodo-02",
 "status": "SOSPECHOSO", "anterior": "ACTIVO"}
```

Quien lo recibe:

- **No cambia su propia tabla.** El reporte es información, no una orden.
  Cada nodo decide con lo que él mismo oye. Así, un nodo con mala señal no
  puede hacer que toda la red saque a alguien que sigue vivo.
- Avisa a `cuando_reporten(node_id, status, quien)` y el registro lo escribe
  como `reporte_estado`. Sirve, por ejemplo, para que la recuperación de
  tareas se prepare antes de que su propio umbral se cumpla.
- **Si el reporte habla de él mismo** y dice que no está ACTIVO, responde de
  inmediato con un `HEARTBEAT`: "sigo vivo". Así se corrige la sospecha sin
  esperar al siguiente latido.

## 5. `monitoring.Registro`

```python
from src.monitoring import Registro

r = Registro(node_id, "nodo-01", carpeta="logs")
r.observar(mensajes, descubrimiento)
...
r.cerrar(mensajes)
```

Escribe `logs/<nombre>.jsonl`, un evento JSON por línea. Cada línea lleva
`t` (hora del nodo), `nodo`, `node_id`, `evento`, `lamport` y los datos del
evento.

| Evento | Datos |
|---|---|
| `vecino_entra` | `vecino`, `vecino_id`, `ip`, `servicios` |
| `vecino_sospechoso` | `vecino`, `vecino_id` |
| `vecino_sale` | `vecino`, `vecino_id` |
| `reporte_estado` | `vecino`, `vecino_id`, `status`, `reporta` (un `NODE_STATUS` recibido) |
| `fallo_envio` | `mensaje` (tipo), `destino`, `puerto`, `receiver`, `grupo`, `error` |
| `metricas` | `contadores` y `trafico` (lo de `mensajes.metricas()`) |

Los HEARTBEAT y los RESOURCE_UPDATE **no** se escriben: se cuentan en
`heartbeat_recibidos` y `recursos_recibidos` (decisión 6).

| Método | Descripción |
|---|---|
| `observar(mensajes, descubrimiento=None)` | Se engancha a los avisos de las dos capas. |
| `evento(tipo, **datos)` | Escribe un evento propio. |
| `contar(nombre, cuanto=1)` | Suma a un contador sin escribir línea. |
| `metricas()` | Copia de los contadores. |
| `volcar(mensajes=None)` | Escribe una línea `metricas`. |
| `cerrar(mensajes=None)` | `volcar` y cierra el archivo. |

Para resumir los registros de todos los nodos:

```bash
python3 examples/analizar_logs.py logs
```

Muestra los eventos por nodo, una línea de tiempo común, cuánto tardó cada
nodo en pasar de SOSPECHOSO a INACTIVO y las últimas métricas.

## 6. Ejemplo completo

```python
from src.communication import ServicioMensajes
from src.discovery import ServicioDescubrimiento
from src.monitoring import Registro

m = ServicioMensajes("a1b2c3d4")                       # bat0 por defecto
d = ServicioDescubrimiento(m, "a1b2c3d4", "nodo-01",
                           leer_estado=lambda: {"cpu": 0.8},
                           servicios=["sensor"])
r = Registro("a1b2c3d4", "nodo-01")
r.observar(m, d)

m.al_recibir("ALERTA", lambda msg, ip: print("alerta:", msg.payload))
m.iniciar()
d.iniciar()
d.unirse("rescate")

m.difundir("ALERTA", {"texto": "réplica en 5 min"})             # broadcast
d.enviar_a_grupo("rescate", "ALERTA", {"zona": "norte"})        # multicast
for v in d.que_ofrezcan(["camara"]):                            # unicast
    m.enviar(v.ip, v.puerto_tcp, "TAREA", v.node_id, {"foto": True})
```

## 7. Aplicación 1: `applications/mensajeria.py`

Es la capa 4 en uso: está escrita solo con `Nodo` (sección 0), sin tocar
sockets ni servicios. Un solo comando arranca el nodo y abre una consola:

```bash
python3 applications/mensajeria.py                     # en la Pi, sobre bat0
python3 applications/mensajeria.py --local             # sin malla, en varias terminales
python3 applications/mensajeria.py --grupos rescate    # entra a un grupo al arrancar
```

| Comando | Método de `Nodo` que usa |
|---|---|
| `lista` | `consultar_estado_red(incluir_caidos=True)` |
| `recursos` | `consultar_recursos()` |
| `yo` | `obtener_estado()` |
| `todos <texto>` | `difundir()` (broadcast) |
| `msg <nodo> <texto>` | `enviar_mensaje()` (unicast TCP) |
| `grupo <grupo> <texto>` | `enviar_a_grupo()` (multicast) |
| `unir` / `dejar <grupo>` | `unirse_a_grupo()` / `salir_de_grupo()` |
| `ping <nodo>` | `enviar_mensaje(..., tipo=PING)` y respuesta `PONG` |
| `red` | `malla.resumen()` |
| `stats` | `mensajes.metricas()` |

Comportamiento:

- Sin `--local`, si `bat0` no existe **no arranca** y explica qué hacer. Así
  nunca se cae en silencio a otra interfaz.
- Con `--local`, si el puerto TCP está ocupado prueba el siguiente (5001,
  5002, ...). Por eso se pueden abrir varias terminales sin pensar en
  puertos.
- El nombre por defecto es el del equipo (`hostname`); con `--local` se le
  agrega el puerto (`equipo-5002`) para que no se repita.
- `msg`, `ping` y `grupo` se envían en segundo plano: la consola no se
  congela mientras se reintenta un envío.
- `salir` o Ctrl+C mandan `GOODBYE` y escriben las métricas en el registro.

## 8. Pruebas

```bash
pip install -r requirements.txt
python3 -m pytest tests -v
```

Corren sobre loopback (`lo` y `127.255.255.255`), así que no necesitan la
malla. Se verifican en **Linux** (o WSL). En Windows, `malla.py` no puede
leer interfaces porque no existe `fcntl`, pero la aplicación con `--local`
funciona igual. Son 72 y
tardan unos 6 minutos, porque varias esperan a que se cumplan los umbrales de
fallo.

| Archivo | Qué prueba |
|---|---|
| `test_comunicacion.py` | Formato, Lamport, límite UDP, difusión, TCP enmarcado, duplicados, fallos y reintentos, multicast |
| `test_descubrimiento.py` | Descubrimiento, servicios, umbrales, reingreso, latido gigante, grupos, `enviar_a_grupo` |
| `test_integracion.py` | Tres nodos completos con registro: se cae el del medio, los otros dos lo detectan (y se lo reportan por NODE_STATUS) y siguen hablando, vuelve y se reintegra |
| `test_api.py` | La clase `Nodo`: identidad persistente, consultas, envíos, servicios y el vector de estado |
| `test_tareas.py` | F(i,j), recursos, la prueba de concepto `suma 10 + 20 = 30`, elección por aptitud, TASK_REQUEST, reparto en paralelo y las tres formas de reasignar |

**Limitación de la prueba de integración:** en loopback los tres nodos se
oyen directamente, así que "el del medio" lo es por su papel (el único con
`camara`), no por la topología. La prueba de topología hay que hacerla en las
Pi:

1. Ubicar A, B y C en línea, de modo que A no alcance a C sin pasar por B
   (`batctl o` en A debe mostrar a C con B como siguiente salto).
2. Correr `demo_descubrimiento.py` en los tres.
3. Desconectar B de la corriente.
4. Resultado esperado: A y C marcan a B como SOSPECHOSO a los ~15 s e INACTIVO
   a los ~30 s. **A y C también se pierden entre sí**, porque no hay otro
   camino. Si hay un cuarto nodo D en alcance de ambos, batman-adv reenruta
   por D y A–C siguen ACTIVOS.
5. `analizar_logs.py` sobre los logs de los tres nodos da la evidencia.

## 9. Recursos, planificador y tareas

El porqué de cada regla está en `diseno.md`, decisiones 18 a 22.

### 9.1 `resources.GestorRecursos` (`nodo.recursos`)

`medir()` devuelve el vector de estado que viaja en el RESOURCE_UPDATE:

```json
{"cpu": 0.82, "memoria": 0.61, "ancho_banda": 0.94, "confiabilidad": 0.75,
 "disponibilidad": 1.0, "carga": 0.5, "almacenamiento": 0.40, "capacidad": 2}
```

| Clave | Variable del modelo | Significado |
|---|---|---|
| `cpu` | Ci | CPU libre |
| `memoria` | Mi | Memoria libre |
| `ancho_banda` | Bi | TQ promedio de batman-adv / 255 |
| `confiabilidad` | Ri | Tareas terminadas bien (suavizado de Laplace) |
| `disponibilidad` | Ai | Batería, o 1.0 si está conectado |
| `carga` | Li | Tareas en curso / capacidad |
| `almacenamiento` | — | Disco libre (RF04) |
| `capacidad` | — | `max_tareas` |

| Método | Descripción |
|---|---|
| `registrar_recurso(nombre, tipo, capacidad=1.0)` | Un recurso físico (una cámara, un sensor). Sale en `medir()["recursos"]`. |
| `actualizar_recurso(nombre, disponible=None, capacidad=None)` | Cambia su estado. |
| `obtener_recursos()` | La lista de recursos registrados. |
| `carga()`, `confiabilidad()` | Los valores propios. |

### 9.2 `scheduler.PlanificadorDistribuido` (`nodo.planificador`)

| Método | Descripción |
|---|---|
| `calcular_aptitud(vecino)` | F = w1·C + w2·M + w3·B + w4·R − w5·L |
| `variables(vecino)` | Las seis variables que usa, ya ajustadas: R = mín(publicada, reputación propia), L incluye lo asignado sin respuesta |
| `seleccionar_nodo(vecinos, excluir=())` | `(vecino, F)` del mejor, o `(None, None)`. Descarta los de A < 0.2. |
| `reputacion(node_id)` | (éxitos + 1) / (éxitos + fallos + 2) según lo que este nodo ha visto |
| `pesos` | Diccionario de pesos, modificable |

### 9.3 `tasks.GestorTareas` (`nodo.tareas`)

Lo normal es usarlo desde `Nodo` (`registrar_operacion`, `enviar_tarea`,
`enviar_tarea_async`). Para inspeccionar:

| Método / atributo | Descripción |
|---|---|
| `pendientes()` | Las tareas que este nodo mandó y siguen sin resultado |
| `recuperacion.reintentos` | Cuántas reasignaciones hizo la recuperación |
| `registrar_operacion(nombre, funcion)` | Ver sección 0 |

Mensajes que usa:

| Tipo | Va por | Payload |
|---|---|---|
| `TASK_REQUEST` | UDP, difusión | `tarea_id`, `requisitos` |
| `TASK_ASSIGN` | TCP, al escogido | `tarea_id`, `operacion`, `datos`, `requisitos`, `prioridad`, `intento`, `puerto_tcp` |
| `TASK_RESULT` | TCP, al solicitante | `tarea_id`, `ok`, `resultado` o `error` y `codigo`, `duracion` |

Eventos del registro: `tarea_creada`, `tarea_solicitada`, `tarea_asignada`
(con la F), `tarea_recibida` (en el ejecutor), `tarea_reasignada` (con el
motivo), `tarea_completada` y `tarea_fallida`.

### 9.4 Ejemplo: regresión lineal distribuida

La recta y = a·x + b por mínimos cuadrados solo necesita cinco sumas: n, Σx,
Σy, Σxy y Σx². Cada pedazo de datos se puede sumar en un nodo distinto, y al
final se juntan. Es un buen caso para repartir.

```python
from src.api import Nodo

def sumas_parciales(puntos):                 # corre en el nodo que la reciba
    n = len(puntos)
    sx = sum(x for x, _ in puntos)
    sy = sum(y for _, y in puntos)
    sxy = sum(x * y for x, y in puntos)
    sxx = sum(x * x for x, _ in puntos)
    return [n, sx, sy, sxy, sxx]

with Nodo("nodo-01") as nodo:
    nodo.registrar_operacion("sumas_regresion", sumas_parciales)

    puntos = [[x, 2 * x + 1] for x in range(1000)]
    pedazos = [puntos[i:i + 250] for i in range(0, len(puntos), 250)]
    futuros = [nodo.enviar_tarea_async("sumas_regresion", p) for p in pedazos]

    n, sx, sy, sxy, sxx = map(sum, zip(*(f.result() for f in futuros)))
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    b = (sy - a * sx) / n
    print(f"y = {a:.3f}x + {b:.3f}")          # y = 2.000x + 1.000
```

Todos los nodos que corran la aplicación registran la operación, así que
cualquiera puede ejecutar un pedazo. El planificador reparte los pedazos según
F(i,j), y si un nodo se cae a la mitad, su pedazo se reasigna solo.
