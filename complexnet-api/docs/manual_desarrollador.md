# Manual del desarrollador

**Cómo hacer tu propia aplicación sobre ComplexNet, desde cero.**

Este manual es para quien quiere *usar* ComplexNet para construir algo: un
chat, una app de sensores, un sistema de alertas. No necesitas saber de redes
ni de sockets. Si quieres entender cómo funciona por dentro, eso está en el
[manual técnico](api/manual.md) y en las [decisiones de diseño](diseno.md).

Todos los ejemplos de este manual se probaron y funcionan tal cual.

---

## Índice

1. [Las ideas básicas](#1-las-ideas-básicas)
2. [Preparar el computador](#2-preparar-el-computador)
3. [Tu primera aplicación: "hola, red"](#3-tu-primera-aplicación-hola-red)
4. [Recibir mensajes](#4-recibir-mensajes)
5. [Las tres formas de mandar un mensaje](#5-las-tres-formas-de-mandar-un-mensaje)
6. [Saber quién está y cómo está](#6-saber-quién-está-y-cómo-está)
7. [Enterarte cuando alguien entra o se cae](#7-enterarte-cuando-alguien-entra-o-se-cae)
8. [Mandar archivos](#8-mandar-archivos)
9. [Repartir trabajo: las tareas](#9-repartir-trabajo-las-tareas)
10. [Receta completa: una aplicación de sensores](#10-receta-completa-una-aplicación-de-sensores)
11. [Probar con varios nodos en un solo computador](#11-probar-con-varios-nodos-en-un-solo-computador)
12. [Llevarlo a la red real](#12-llevarlo-a-la-red-real)
13. [Errores comunes](#13-errores-comunes)
14. [Resumen de la API](#14-resumen-de-la-api)

---

## 1. Las ideas básicas

Con cinco palabras entiendes todo lo demás:

| Palabra | Qué es | Comparación |
|---|---|---|
| **Nodo** | Cada programa que se une a la red. Normalmente uno por computador | Una persona con un walkie-talkie |
| **Mensaje** | Un paquete de datos que un nodo le manda a otro (o a varios) | Lo que se dice por el walkie-talkie |
| **Tipo** | Un nombre que le pones a cada mensaje para saber qué es (`"ALERTA"`, `"LECTURA"`...) | El tema de la conversación |
| **Grupo** | Un conjunto de nodos con nombre; los mensajes al grupo solo les llegan a ellos | Un canal del walkie-talkie |
| **Tarea** | Un trabajo que un nodo le pide a la red; lo hace el nodo que esté mejor | Pedirle un favor al que esté más desocupado |

Y una regla de oro: **en ComplexNet no hay servidor**. Cada nodo es igual a
los demás. Si un nodo se apaga, los demás siguen.

Todo lo que necesitas está en una sola clase: **`Nodo`**.

---

## 2. Preparar el computador

Necesitas **Python 3.10 o más nuevo**. Para probar no necesitas Linux ni la
red en malla: todo funciona en un solo computador (Windows, Linux o macOS).

```bash
git clone https://github.com/lamaquina27/proyecto_SC.git
cd proyecto_SC/complexnet-api
pip install -r requirements.txt
```

Tus aplicaciones van en la carpeta `complexnet-api/applications/` y se corren
desde `complexnet-api/`. Al principio de cada aplicación pon estas líneas,
para que Python encuentre la API:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.api import Nodo
```

---

## 3. Tu primera aplicación: "hola, red"

Crea `applications/hola.py`:

```python
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.api import Nodo

LOCAL = dict(interfaz="lo", difusion="127.255.255.255")   # para probar en un solo PC

nombre = sys.argv[1]
puerto = int(sys.argv[2])

with Nodo(nombre, puerto_tcp=puerto, **LOCAL) as nodo:
    nodo.al_recibir("SALUDO", lambda m, ip: print(f"{m.payload['de']} dice: {m.payload['texto']}"))

    time.sleep(3)                                          # dar tiempo a que se encuentren
    nodo.difundir({"de": nombre, "texto": "hola, red"}, tipo="SALUDO")

    time.sleep(5)
```

Ábrelo en dos terminales al mismo tiempo:

```bash
python applications/hola.py ana 5101
python applications/hola.py beto 5102
```

Cada uno muestra el saludo del otro. Lo que pasó:

| Línea | Qué hace |
|---|---|
| `Nodo(nombre, puerto_tcp=..., **LOCAL)` | Crea el nodo. `LOCAL` hace que use la red interna del computador en vez de la malla |
| `with ... as nodo:` | **Se une a la red** al entrar y **se despide** al salir (los demás se enteran) |
| `al_recibir("SALUDO", ...)` | "Cuando llegue un mensaje de tipo `SALUDO`, llama a esta función" |
| `difundir(datos, tipo=...)` | Manda el mensaje **a todos** los nodos |

> **¿Por qué el puerto?** Cuando varios nodos corren en el mismo computador,
> cada uno necesita su propio puerto TCP. En la red real, cada nodo está en
> su propio equipo y no hace falta: se usa el 5001.

---

## 4. Recibir mensajes

Registras una función por cada tipo de mensaje que te interesa:

```python
def al_llegar_alerta(mensaje, ip):
    print("alerta de", mensaje.sender, ":", mensaje.payload)

nodo.al_recibir("ALERTA", al_llegar_alerta)
```

La función recibe dos cosas:

| | Qué es |
|---|---|
| `mensaje.payload` | **Tus datos**: lo que mandó el otro nodo (un diccionario, una lista, un texto, un número) |
| `mensaje.sender` | El identificador del nodo que lo mandó (sirve para responderle) |
| `mensaje.type` | El tipo (`"ALERTA"`) |
| `mensaje.group` | El grupo, si se mandó a un grupo |
| `ip` | La dirección del nodo que lo mandó |

**Los datos tienen que ser JSON:** diccionarios, listas, textos, números,
`True`/`False` y `None`. Nada de objetos propios: conviértelos a diccionario
antes de mandarlos.

**Importante:** la función se ejecuta mientras el nodo recibe otros mensajes.
Si vas a hacer algo que tarde (guardar mucho en disco, calcular algo pesado),
hazlo en un hilo aparte para no frenar la recepción.

---

## 5. Las tres formas de mandar un mensaje

```python
nodo.enviar_mensaje("beto", {"texto": "hola beto"}, tipo="CHAT")   # a uno
nodo.enviar_a_grupo("rescate", {"zona": "norte"}, tipo="ALERTA")   # a un grupo
nodo.difundir({"texto": "evacuar"}, tipo="ALERTA")                 # a todos
```

| | A quién | Cómo viaja | Confirmación |
|---|---|---|---|
| `enviar_mensaje(destino, datos)` | Un nodo (por nombre o identificador) | TCP, con reintentos | Devuelve `True` si llegó |
| `enviar_a_grupo(grupo, datos)` | Los del grupo | UDP; si es grande, TCP a cada miembro | Sin confirmación por UDP |
| `difundir(datos)` | Todos | UDP; si es grande, TCP a cada uno | Sin confirmación por UDP |

**Grupos:** un nodo entra a un grupo con `nodo.unirse_a_grupo("rescate")` y
sale con `nodo.salir_de_grupo("rescate")`. Solo recibe los mensajes de los
grupos donde está.

**¿Mensaje pequeño o grande?** No te preocupes: si el mensaje no cabe en un
paquete UDP (unos 1400 bytes), ComplexNet lo manda por TCP solo.

Si `enviar_mensaje` no conoce al destino, lanza `LookupError`. Si lo conoce
pero no pudo entregarlo (después de reintentar), devuelve `False`.

---

## 6. Saber quién está y cómo está

```python
for vecino in nodo.consultar_estado_red():
    print(vecino["nombre"], vecino["ip"], vecino["status"])

print(nodo.consultar_recursos("beto"))   # {'cpu': 0.82, 'memoria': 0.61, ...}
print(nodo.obtener_estado())             # el estado de este mismo nodo
```

Cada nodo publica cada 5 segundos su **estado**, con valores de 0 (mal) a 1
(bien):

| Clave | Qué significa |
|---|---|
| `cpu` | Qué tan desocupado está el procesador |
| `memoria` | Cuánta memoria libre le queda |
| `ancho_banda` | Qué tan buena es su conexión con los vecinos |
| `confiabilidad` | Qué tanto ha cumplido las tareas que le dieron |
| `disponibilidad` | Batería (1 si está enchufado) |
| `carga` | Qué tan ocupado está con tareas |

---

## 7. Enterarte cuando alguien entra o se cae

```python
nodo.cuando_entre(lambda vecino: print("llegó", vecino.nombre))
nodo.cuando_sospeche(lambda node_id: print("no responde hace 15 s:", node_id))
nodo.cuando_salga(lambda node_id: print("se fue o se cayó:", node_id))
```

| Aviso | Cuándo |
|---|---|
| `cuando_entre` | Llega un nodo nuevo, o vuelve uno que se había caído |
| `cuando_sospeche` | Un nodo lleva 15 s sin dar señales |
| `cuando_salga` | Lleva 30 s sin señales, o se despidió |

---

## 8. Mandar archivos

```python
r = nodo.enviar_archivo("beto", "datos/censo.csv")
if r["entregado"]:
    print("llegó en", r["segundos"], "s")
else:
    print("no llegó:", r["error"])
```

Del otro lado, el archivo queda en la carpeta `recibidos/` y te puedes
enterar así:

```python
nodo.cuando_llegue_archivo(lambda info: print("llegó", info["nombre"], "a", info["ruta"]))
```

ComplexNet se encarga de todo: lo parte en pedazos, lo **comprime** si vale la
pena (un CSV de 1 MB puede viajar en 50 KB), comprueba que llegó sano y no
pisa archivos con el mismo nombre.

---

## 9. Repartir trabajo: las tareas

Una **tarea** es un trabajo que le pides a la red. ComplexNet escoge el nodo
que esté en mejores condiciones, se lo manda, espera el resultado y, si ese
nodo se cae a la mitad, se lo pasa a otro.

Son dos pasos.

**Paso 1. Los nodos que saben hacer el trabajo lo registran:**

```python
def promedio(numeros):
    return sum(numeros) / len(numeros)

nodo.registrar_operacion("promedio", promedio)
```

La función recibe los datos y devuelve el resultado. Los dos tienen que ser
JSON.

**Paso 2. Cualquier nodo pide el trabajo:**

```python
resultado = nodo.enviar_tarea("promedio", [20.5, 21.0, 22.3])
print(resultado)   # 21.266...
```

`enviar_tarea` espera hasta tener el resultado. Para mandar **muchas tareas a
la vez** y que se repartan entre varios nodos, usa la versión `_async`:

```python
futuros = [nodo.enviar_tarea_async("promedio", grupo) for grupo in grupos_de_datos]
resultados = [f.result() for f in futuros]       # espera a que terminen todas
```

Si la tarea no se puede hacer (nadie la sabe hacer, o la función dio un
error), `enviar_tarea` lanza `TareaFallida` con la explicación:

```python
from src.api import TareaFallida

try:
    nodo.enviar_tarea("promedio", [])
except TareaFallida as e:
    print("falló:", e)      # ZeroDivisionError: division by zero
```

**Opciones útiles:**

| Opción | Para qué | Por defecto |
|---|---|---|
| `timeout=10` | Si en 10 s no responde, se le pasa a otro nodo | 30 s |
| `intentos=5` | Cuántos nodos probar como máximo | 3 |

> El nodo que pide la tarea **no la hace él mismo** si hay otros que sepan
> hacerla: así el trabajo se reparte. Solo la hace él si está solo en la red.

---

## 10. Receta completa: una aplicación de sensores

Una aplicación que lee temperatura, presión y humedad, comparte cada lectura
con el grupo `sensores`, guarda todo en un CSV y deja que cualquier nodo pida
un resumen.

Crea `applications/sensores_ejemplo.py`:

```python
import csv
import os
import random
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.api import Nodo

LOCAL = dict(interfaz="lo", difusion="127.255.255.255")
CADA = 2.0                                       # segundos entre lecturas


def leer_sensor():
    # Aqui va la lectura real (por ejemplo, un BME280 por I2C).
    # Mientras tanto, valores simulados:
    return {"temperatura": round(random.gauss(23, 1.5), 2),
            "presion": round(random.gauss(1012, 3), 1),
            "humedad": round(random.gauss(65, 5), 1)}


def resumen(lecturas):
    # Se ejecuta en el nodo que escoja la red
    campos = ("temperatura", "presion", "humedad")
    return {c: {"min": min(l[c] for l in lecturas),
                "max": max(l[c] for l in lecturas),
                "promedio": round(sum(l[c] for l in lecturas) / len(lecturas), 2)}
            for c in campos}


nombre = sys.argv[1]
puerto = int(sys.argv[2])
archivo = f"lecturas-{nombre}.csv"
historial = []

with Nodo(nombre, puerto_tcp=puerto, **LOCAL) as nodo:
    nodo.unirse_a_grupo("sensores")
    nodo.registrar_operacion("resumen_sensores", resumen)
    nodo.al_recibir("LECTURA", lambda m, ip: print(
        f"  {m.payload['nodo']}: {m.payload['temperatura']} C, "
        f"{m.payload['presion']} hPa, {m.payload['humedad']} %"))

    def medir():
        with open(archivo, "a", newline="") as f:
            escritor = csv.writer(f)
            while nodo.activo:
                lectura = leer_sensor()
                lectura["nodo"] = nombre
                lectura["hora"] = datetime.now().isoformat(timespec="seconds")
                historial.append(lectura)
                escritor.writerow([lectura["hora"], lectura["temperatura"],
                                   lectura["presion"], lectura["humedad"]])
                f.flush()
                nodo.enviar_a_grupo("sensores", lectura, tipo="LECTURA")
                time.sleep(CADA)

    threading.Thread(target=medir, daemon=True).start()

    time.sleep(12)
    print("resumen calculado por la red:", nodo.enviar_tarea("resumen_sensores", historial))
```

Ábrelo en dos o tres terminales (`sensores_ejemplo.py nodo-1 5101`,
`sensores_ejemplo.py nodo-2 5102`...). Cada nodo ve las lecturas de los demás,
guarda las suyas en un CSV, y al final le pide a la red un resumen, que calcula
otro nodo.

Con lo que ya viste, puedes extenderlo:

- **Mandar el historial a otro nodo:** `nodo.enviar_archivo("nodo-2", archivo)`. El CSV viaja comprimido.
- **Alertas:** si la temperatura pasa de un límite,
  `nodo.difundir({...}, tipo="ALERTA")` para que todos se enteren.
- **Que otro nodo procese:** cualquier cálculo pesado (una predicción, una
  regresión) se registra con `registrar_operacion` y se pide con
  `enviar_tarea`, como el resumen.

---

## 11. Probar con varios nodos en un solo computador

Para probar no necesitas varios equipos. Abre varias terminales y en cada nodo
usa:

- `interfaz="lo"` y `difusion="127.255.255.255"` (la red interna del computador);
- un `puerto_tcp` distinto para cada uno (5101, 5102, 5103...);
- un nombre distinto para cada uno.

Puedes ver todo en vivo con el monitor, en otra terminal:

```bash
python applications/monitor.py --local
```

Para pruebas automáticas, mira cómo están hechas las de `tests/`: crean
varios nodos dentro de una misma prueba con `Nodo(...)`, esperan un par de
segundos a que se encuentren y comprueban el resultado.

---

## 12. Llevarlo a la red real

En la red real (equipos con Linux y la malla montada con `setup_adhoc.sh`) solo
cambian dos cosas:

1. **Quita `**LOCAL` y el puerto:** `Nodo("nodo-1")` usa `bat0`, la interfaz
   de la malla, y el puerto 5001.
2. **Córrelo con `sudo`**, para que el nodo pueda atarse a la interfaz de la
   malla.

Una forma cómoda de tener las dos versiones es una opción `--local`, como hace
`applications/mensajeria.py`:

```python
if "--local" in sys.argv:
    nodo = Nodo(nombre, interfaz="lo", difusion="127.255.255.255", puerto_tcp=puerto)
else:
    nodo = Nodo(nombre)
```

---

## 13. Errores comunes

| Lo que pasa | Por qué | Qué hacer |
|---|---|---|
| `OSError: no se pudo abrir el puerto TCP 5101` | Otro nodo ya usa ese puerto en este computador | Usa otro `puerto_tcp` |
| `LookupError: no conozco al nodo beto` | Todavía no se encontraron, o el nombre está mal | Espera 2 o 3 segundos después de arrancar; revisa el nombre con `consultar_estado_red()` |
| `TareaFallida: ningun nodo activo ofrece X` | Ningún nodo registró la operación `X` | Revisa que el nombre sea igual en `registrar_operacion` y en `enviar_tarea` |
| `TypeError ... is not JSON serializable` | Mandaste algo que no es JSON (un objeto, un `set`, una fecha) | Conviértelo: `list(conjunto)`, `fecha.isoformat()`, `vars(objeto)` |
| Los nodos no se ven en la red real | La malla no está montada, o falta `sudo` | Revisa `ip addr show bat0` y `sudo batctl n` |
| Mi función no recibe nada | El tipo no coincide (mayúsculas cuentan) | Usa el mismo `tipo=` al mandar y en `al_recibir` |

---

## 14. Resumen de la API

Todo está en la clase `Nodo` (`from src.api import Nodo`).

| Para | Usa |
|---|---|
| Crear y unirse | `Nodo(nombre)` y `iniciar()`, o `with Nodo(nombre) as nodo:` |
| Salir | `detener()` (se despide; con `despedirse=False` simula una caída) |
| Mandar a uno | `enviar_mensaje(destino, datos, tipo="...")` |
| Mandar a un grupo | `enviar_a_grupo(grupo, datos, tipo="...")` |
| Mandar a todos | `difundir(datos, tipo="...")` |
| Grupos | `unirse_a_grupo(g)`, `salir_de_grupo(g)` |
| Recibir | `al_recibir(tipo, funcion(mensaje, ip))` |
| Quién está | `consultar_estado_red()`, `buscar(nombre)` |
| Cómo están | `consultar_recursos(destino)`, `obtener_estado()` |
| Archivos | `enviar_archivo(destino, ruta)`, `cuando_llegue_archivo(funcion(info))` |
| Ofrecer un trabajo | `registrar_operacion(nombre, funcion(datos))` |
| Pedir un trabajo | `enviar_tarea(operacion, datos)`, `enviar_tarea_async(...)` |
| Avisos | `cuando_entre`, `cuando_sospeche`, `cuando_salga`, `cuando_falle` |

Opciones de `Nodo(...)` que podrías necesitar:

| Opción | Para qué | Por defecto |
|---|---|---|
| `interfaz`, `difusion` | Red a usar (`"lo"` y `"127.255.255.255"` para probar) | `bat0` |
| `puerto_tcp` | Puerto propio | 5001 |
| `servicios` | Lista de cosas que sabe hacer (además de las operaciones) | `[]` |
| `carpeta_logs` | Dónde guardar el registro de eventos (`None` para no guardar) | `logs` |
| `carpeta_archivos` | Dónde guardar los archivos recibidos | `recibidos` |
| `max_tareas` | Cuántas tareas ajenas hace a la vez | 2 |

El detalle de cada método, parámetro y mensaje está en el
[manual técnico](api/manual.md).
