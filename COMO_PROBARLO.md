# Cómo comprobar que funciona

Hay tres cosas distintas que comprobar, y conviene no confundirlas:

1. **Que la malla existe.** Eso lo hace batman-adv, no nuestro código.
2. **Que nuestro código habla por la malla.** Esto sí es nuestro.
3. **Que los mensajes de verdad están viajando.** La prueba que no se puede
   falsear.

---

## Nivel 1 — Que la malla existe

Antes de correr una sola línea de Python, la malla tiene que estar montada.
En cada equipo:

```bash
sudo ./setup_adhoc.sh 1        # en el segundo: 2, en el tercero: 3
```

Y después estas cuatro comprobaciones:

```bash
ip -brief addr show bat0      # debe mostrar bat0 con su IP, por ejemplo 10.10.0.1
batctl neighbors              # los vecinos que este equipo escucha directamente
batctl originators            # TODOS los nodos alcanzables, con su siguiente salto
ping -c 3 10.10.0.3           # llegar hasta el nodo más lejano
```

**La diferencia entre las dos tablas es lo importante.** `neighbors` muestra
solo a quien se escucha directamente. `originators` muestra a todos, incluso
los que están a tres saltos, cada uno con su métrica TQ y su siguiente salto.
Ningún nodo conoce la ruta completa: solo sabe "para llegar allá, pásaselo a
este". Eso es lo que hay que señalar en la sustentación cuando se hable de
comportamiento emergente.

Para ver el camino salto a salto:

```bash
batctl traceroute $(ssh nodo3 cat /sys/class/net/bat0/address)
```

---

## Nivel 2 — Que nuestro código habla por la malla

**Lo más rápido es la aplicación de mensajería**, que lo arranca todo con un
solo comando. En cada equipo, desde `complexnet-api/`:

```bash
python3 applications/mensajeria.py
```

Sin malla, en un solo computador, abra tres terminales y en cada una:

```bash
python3 applications/mensajeria.py --local
```

Tiene los mismos comandos que los demos (`lista`, `todos`, `msg`, `grupo`,
`unir`, `ping`, `stats`) y además deja el registro en `logs/`. Los demos de
abajo siguen sirviendo para mostrar cada capa por separado.

En cada equipo:

```bash
python3 examples/demo_descubrimiento.py nodo-01
```

A los pocos segundos cada nodo empieza a imprimir su tabla de vecinos. Esto
es una salida real con dos nodos:

```
nodo-01 (ca4eaaeb) en lo
  ip: 10.10.0.1   difusión: 10.10.0.255

  >> entró nodo-02 en 10.10.0.2

[nodo-01] conozco 1 nodo(s)
   nombre      estado      ip              cpu    mem    visto   servicios
   nodo-02     ACTIVO      10.10.0.2       1.0    0.939  2.7s    sensor_movimiento
```

Y el de mensajería, que es interactivo:

```bash
python3 examples/demo_comunicacion.py nodo-01
```

Sesión real, con los comandos escritos y lo que responde:

```
nodo-01 (8e539057) escuchando en lo
  ip: 10.10.0.1   difusión: 10.10.0.255
  puertos: UDP 5000 · TCP 5001

  >> apareció nodo-02 en 10.10.0.2

lista
  nodo-02      10.10.0.2        visto hace 4.7 s

todos hola a toda la malla
  enviado a toda la malla

msg nodo-02 esto va directo por TCP
  enviado a nodo-02

ping nodo-02
  >> respuesta de nodo-02: 3.5 ms

stats
  enviados: 7
  recibidos: 4
  descartados: 0
  bytes_enviados: 1243
  bytes_recibidos: 1593
  fallos_envio: 0
```

Al mismo tiempo, en la terminal del otro equipo:

```
  >> apareció nodo-01 en 10.10.0.1
  >> nodo-01 (a todos): hola a toda la malla
  >> nodo-01 (directo): esto va directo por TCP
```

Fíjese que el mensaje dice **a todos** o **directo** según por dónde llegó.
El primero viajó por UDP en difusión y el segundo por TCP punto a punto.

### Multicast: mandar solo a un grupo

En nodo-02 escriba `unir rescate`. En nodo-03 no escriba nada. Después, en
nodo-01:

```
grupo rescate hay heridos en la zona norte
  enviado al grupo rescate
```

En nodo-02 aparece `>> nodo-01 (grupo rescate): hay heridos...`. En nodo-03
no aparece nada, y en su `stats` sube `descartados`: el datagrama sí le
llegó, pero lo descartó porque no es del grupo. Eso es lo que hay que
explicar: es una sola difusión y cada nodo filtra.

### Si varios nodos corren en el mismo equipo

Hay que darles puertos TCP distintos, porque no pueden compartirlo:

```bash
python3 examples/demo_comunicacion.py nodo-01 lo 127.255.255.255 5001
python3 examples/demo_comunicacion.py nodo-02 lo 127.255.255.255 5002
python3 examples/demo_comunicacion.py nodo-03 lo 127.255.255.255 5003
```

En equipos distintos no hace falta: cada uno usa el 5001.

---

## Nivel 3 — Ver los mensajes viajando

Esta es la comprobación que no se puede fingir. En un equipo, mientras los
otros hablan:

```bash
sudo tcpdump -i bat0 -A -n udp port 5000
```

Los mensajes salen en texto plano, porque van en JSON. Uno real se ve así:

```json
{"message_id":"b971b455","type":"HEARTBEAT","sender":"a3f1c9d2",
 "receiver":null,"group":null,"timestamp":1790787256.94,"seq":87,
 "lamport":312,"payload":{"nombre":"nodo-01","puerto_tcp":5001,
 "servicios":["sensor_movimiento"],"grupos":["rescate"]}}

{"message_id":"c08a11f2","type":"RESOURCE_UPDATE","sender":"a3f1c9d2",
 "receiver":null,"group":null,"timestamp":1790787256.95,"seq":88,
 "lamport":313,"payload":{"nombre":"nodo-01","puerto_tcp":5001,
 "estado":{"cpu":0.72,"memoria":0.55,"ancho_banda":0.81,"carga":0.25}}}
```

Son los dos mensajes de la tabla de tipos del corte 1. El HEARTBEAT dice
"sigo vivo" y qué sabe hacer el nodo; el RESOURCE_UPDATE lleva el vector de
estado. Ahí se ve todo de un vistazo: el tipo, quién lo mandó, el contador de
secuencia y el reloj de Lamport. `receiver` en `null` significa que va para
todos, y `group` es el grupo en un multicast.

Si apaga un nodo de golpe, a los 15 s verá pasar un `NODE_STATUS` de cada
vecino, con `"status":"SOSPECHOSO"`, y otro a los 30 s con `"INACTIVO"`.

Para los mensajes directos:

```bash
sudo tcpdump -i bat0 -A -n tcp port 5001
```

Para verlo con interfaz gráfica, Wireshark sobre `bat0` con el filtro
`udp.port == 5000 || tcp.port == 5001`. Eso queda muy bien en el video.

---

## La prueba que de verdad demuestra que funciona

Todo lo anterior se podría lograr con una red normal. Lo que demuestra que la
malla está haciendo su trabajo es esto:

**Ponga los tres equipos de modo que el 1 y el 3 no se escuchen entre sí.**
En el laboratorio de contenedores ya quedan así. Con Raspberry Pi, basta con
alejarlos o tapar uno con algo.

Compruébelo:

```bash
# en el nodo 1
batctl neighbors     # debe aparecer SOLO el nodo 2
batctl originators   # deben aparecer el 2 Y el 3
```

Si el 3 no está en `neighbors` pero sí en `originators`, es porque batman
encontró la ruta por el 2.

Ahora mande un mensaje del 1 al 3 y déjelo corriendo. Mientras tanto, en el
**nodo 2**, que no es ni origen ni destino:

```bash
sudo tcpdump -i bat0 -n
```

Va a ver pasar tráfico que no es suyo: está reenviando. Eso es el salto
intermedio funcionando, y no hay forma de simularlo.

Y el remate: **apague el nodo 2**. El mensaje del 1 al 3 deja de llegar,
porque se cayó el único puente. Vuelva a prenderlo y la comunicación se
restablece sola, sin que nadie configure nada.

---

## Checklist para el video

| Qué mostrar | Cómo se ve que funcionó |
|---|---|
| La malla se armó sola | `batctl originators` con los tres nodos |
| Hay ruta de varios saltos | `neighbors` tiene menos nodos que `originators` |
| El descubrimiento funciona | La tabla de vecinos llenándose sola |
| Mensajes a todos | El mismo texto apareciendo en dos terminales |
| Mensaje directo | Llega solo al destinatario |
| Multicast | `grupo rescate ...` llega al que hizo `unir rescate` y no al otro |
| Latencia medida | El `ping` con los milisegundos |
| Los mensajes existen | tcpdump con el JSON en pantalla |
| Salida ordenada | Ctrl+C en un nodo: desaparece al momento |
| Caída de golpe | Cerrar la terminal: SOSPECHOSO a los 15 s, INACTIVO a los 30 |
| Se recupera solo | Volver a prenderlo y verlo reintegrarse |
| Recursos | `recursos`: el vector [C, M, B, R, A] de cada nodo |
| Asignación de tareas | `calc 10 + 20`: responde 30 y dice qué nodo la ejecutó |
| Reparto y costo | `estres 15` con `applications/monitor.py` abierto: cada nodo recibe una parte y se ve su CPU bajar |
| Reasignación | Ver abajo |

### La reasignación en vivo

Es la prueba más fuerte, porque junta tareas, planificador, detección de
fallos y recuperación. La caída tiene que ocurrir con la tarea en curso, y
`estres` da el tiempo: desde el nodo 1, `estres 60 2`, y con el monitor ver
qué nodo ejecuta una parte. Cerrar de golpe esa terminal: a los 30 s el
monitor lo marca caído, la recuperación reasigna su parte y el `estres`
termina igual, diciendo quién hizo cada parte. También se puede correr la
prueba automática, que hace exactamente eso, y mostrar su registro:

```bash
python3 -m pytest tests/test_tareas.py -k "se_cae_el_ejecutor" -v
```

O con la regresión de tu compañero, que tarda más: lanzarla, apagar de golpe
el nodo que está ejecutando un pedazo y mostrar que el resultado llega igual.
En `analizar_logs.py` debe aparecer
`REASIGNA tarea ...: nodo_caido (estaba en nodo-X)`.

Las últimas tres son las que más pesan en la nota, porque son la evidencia de
tolerancia a fallos.

Al terminar, junte en una carpeta los `logs/*.jsonl` de los tres equipos y
corra `python3 examples/analizar_logs.py logs`. Muestra una línea de tiempo
común y cuánto tardó cada nodo en pasar de SOSPECHOSO a INACTIVO. Es la
evidencia escrita de lo que se vio en el video.

---

## Qué hacer si algo no funciona

| Síntoma | Causa probable |
|---|---|
| `bat0` no existe | Falta `sudo modprobe batman-adv` |
| `batctl originators` vacío | Todavía no convergen los OGM; espere 10 segundos |
| Los nodos no se ven, pero `ping` entre ellos sí funciona | La difusión está saliendo por otra interfaz. Revise que el tercer argumento sea la difusión de la malla, `10.10.0.255` |
| `Address already in use` | Otro nodo ya tomó ese puerto TCP en el mismo equipo. Use el cuarto argumento |
| Un nodo se ve a sí mismo en la lista | No debería pasar: el código descarta sus propios mensajes por `sender` |
| Llegan mensajes cortados | Es el enmarcado de TCP. Revise que se esté usando `enviar()` y no un socket suelto |
