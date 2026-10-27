# Una sola USB para los tres nodos

La idea: la USB tiene Ubuntu, el código y los programas que faltan. Cada
computador arranca desde ella con la opción **`toram`**, que copia Linux
entero a la memoria RAM. Cuando el script termina de copiar el proyecto, la
USB queda libre y se lleva al siguiente computador. Al final, los tres
equipos corren desde su propia RAM, sin USB y **sin internet**.

```
 USB ──> PC 1 (toram, copia, "ya la puedes sacar") ──> PC 2 ──> PC 3
          sigue corriendo en RAM                      ...      ...
```

**Lo importante de toram:** todo lo que pasa en esos computadores vive en la
RAM. Si uno se reinicia o se apaga, se pierde y hay que volver a arrancarlo
desde la USB. Los registros se guardan al final (paso 12).

---

## Parte A. En casa, una sola vez

### 1. Lo que necesitas

- Una USB de **16 GB o más**, mejor si es USB 3: el arranque es más rápido.
  **Se va a borrar.**
- El ISO de **Ubuntu 24.04 LTS Desktop** (64 bits), de ubuntu.com/download.
  Tiene que ser 24.04: los paquetes de la carpeta `paquetes/` son de esa
  versión.
- **Rufus** (rufus.ie), para Windows.
- Computadores con **8 GB de RAM o más**. Con toram, Ubuntu ocupa en RAM más
  o menos lo que pesa el ISO (unos 6 GB). Con 4 GB no alcanza.

### 2. Grabar Ubuntu en la USB con Rufus

1. Abre Rufus y escoge la USB en **Dispositivo**.
2. En **Elección de arranque**, escoge el ISO de Ubuntu.
3. **Esquema de partición:** GPT. **Sistema destino:** UEFI.
4. **Etiqueta de volumen:** escribe `COMPLEXNET`, en mayúsculas y sin
   espacios. Es importante: los comandos de abajo usan ese nombre.
5. **Sistema de archivos:** FAT32.
6. Dale a **Empezar**. Si pregunta el modo, escoge **"Escribir en modo
   Imagen ISO (Recomendado)"**, no el modo DD. Así la USB se sigue pudiendo
   abrir y escribir desde Windows.

### 3. Los paquetes que Ubuntu en vivo no trae

Ubuntu en vivo no trae `batctl`, y sin internet no se puede instalar allá. Ya
están descargados en la carpeta `paquetes/` del proyecto:

```
batctl, iw, libnl-3-200, libnl-genl-3-200, python3-psutil   (Ubuntu 24.04, amd64)
```

Esa carpeta no se sube a GitHub. Si la necesita tu compañero, o si la
borraste, se vuelve a bajar desde WSL:

```bash
cd /mnt/d/jdsan/Desktop/visual/proyecto_SC
mkdir -p paquetes && cd paquetes
sudo apt update
apt download batctl iw libnl-3-200 libnl-genl-3-200 python3-psutil
```

### 4. Copiar el proyecto a la USB

En PowerShell, desde la carpeta del proyecto (cambia `E:` por la letra de tu
USB):

```powershell
powershell -ExecutionPolicy Bypass -File preparar_usb.ps1 -Unidad E:
```

El script deja en la USB la carpeta `complexnet\`, con el código, los dos
scripts de Linux y los paquetes. Al final te dice si falta algo. **Vuelve a
correrlo cada vez que cambie el código**: solo actualiza lo que cambió.

### 5. Ensayo general con un computador (no te lo saltes)

Haz la Parte B completa, del paso 6 al 10, con un solo computador. Si llegas
a ver el mensaje `abriendo la mensajeria como nodo-1`, la USB está bien.
Además, el ensayo te dice dos cosas que solo se saben probando:

- si ese computador tiene RAM suficiente para toram;
- si su tarjeta Wi-Fi soporta el modo ad hoc. Si no lo soporta, el script lo
  dice clarito.

Si puedes, haz el ensayo en los mismos computadores del laboratorio.

---

## Parte B. En el laboratorio, en cada computador

Repite los pasos 6 a 10 en cada computador, con el número de nodo 1, 2 y 3.

### 6. Arrancar desde la USB

1. Conecta la USB y prende el computador.
2. Apenas prenda, presiona la tecla del **menú de arranque**. Depende de la
   marca:

   | Marca | Tecla |
   |---|---|
   | HP | F9 (o Esc y luego F9) |
   | Dell | F12 |
   | Lenovo | F12 (o el botón Novo) |
   | Asus | F8 o Esc |
   | Acer | F12 |
   | Otras | Esc, F11 o F12 |

3. Escoge la USB. Si sale dos veces, escoge la que dice **UEFI**.

### 7. Agregar `toram` (el paso clave)

1. Sale un menú negro con **"Try or Install Ubuntu"**. Antes de que arranque
   solo, presiona la tecla **`e`**.
2. Aparece un texto. Busca la línea que empieza con **`linux`**. Termina más
   o menos así:
   ```
   linux   /casper/vmlinuz  --- quiet splash
   ```
3. Lleva el cursor con las flechas al final de esa línea, después de
   `splash`, y escribe un espacio y `toram`:
   ```
   linux   /casper/vmlinuz  --- quiet splash toram
   ```
4. Presiona **Ctrl + X** (o F10) para arrancar.
5. **Espera.** Copiar Ubuntu a la RAM tarda de 2 a 6 minutos según la USB, y
   puede parecer que no hace nada.

Si te equivocas escribiendo, presiona Esc y vuelve a presionar `e`.

### 8. Entrar al escritorio

1. Cuando aparezca el instalador de Ubuntu, escoge el idioma y luego
   **"Probar Ubuntu"**. Si no aparece esa opción, cierra la ventana del
   instalador.
2. **No te conectes a ninguna red Wi-Fi.** La tarjeta la va a usar la malla.

### 9. Correr el script

1. Abre **Archivos** (el ícono de la carpeta) y haz clic en **COMPLEXNET** en
   la columna izquierda. Eso "monta" la USB.
2. Abre una terminal con **Ctrl + Alt + T** y escribe (cambia el `1` por el
   número de este nodo):
   ```bash
   sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 1
   ```
   Para que este nodo entre de una vez a un grupo:
   ```bash
   sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 1 --grupos rescate
   ```

El script hace todo solo, y en cada paso dice qué está haciendo:

| Paso | Qué hace |
|---|---|
| Copiar | Copia el proyecto a `/opt/complexnet`, que está en la RAM |
| Soltar la USB | La desmonta y dice **"YA LA PUEDES SACAR"** |
| Programas | Instala desde la USB lo que falte: `batctl`, `iw`, `psutil` |
| batman-adv | Carga el módulo del kernel |
| Tarjeta | Busca la Wi-Fi sola y revisa que soporte el modo ad hoc |
| Malla | Le quita la tarjeta a NetworkManager y corre `setup_adhoc.sh` (IP `10.10.0.N`) |
| Aplicación | Abre la mensajería como `nodo-N` |

Si el equipo tiene dos tarjetas Wi-Fi, di cuál usar:
`sudo bash .../arrancar_nodo.sh 1 wlp2s0` (las ves con `iw dev`).

### 10. Sacar la USB y seguir con el siguiente

Cuando aparezca **"YA LA PUEDES SACAR"**, saca la USB y ve al siguiente
computador (paso 6, con el número 2, y luego el 3). El primer computador
sigue funcionando solo.

---

## Parte C. Probar y cerrar

### 11. Comprobar que la malla funciona

Cuando los tres estén arriba, en cualquiera de ellos:

```
lista          debe mostrar a los otros dos como ACTIVO
recursos       el estado de cada uno
calc 10 + 20   debe dar 30 y decir qué nodo la hizo
todos hola     debe aparecer en las otras dos pantallas
```

Si cerraste la aplicación, se vuelve a abrir sin la USB:

```bash
sudo bash /opt/complexnet/arrancar_nodo.sh 1
```

La malla no se vuelve a montar: el script ve que ya está y abre directo la
aplicación.

Para ver la malla por dentro, en otra terminal: `sudo batctl n` (vecinos
directos) y `sudo batctl o` (todos los nodos alcanzables).

### 12. Guardar los registros antes de apagar

Todo está en la RAM: si apagas sin guardar, se pierde la evidencia. En cada
computador:

1. Escribe `salir` en la aplicación. Así escribe las métricas finales.
2. Conecta la USB y haz clic en COMPLEXNET en **Archivos**.
3. En la terminal:
   ```bash
   sudo mkdir -p /media/ubuntu/COMPLEXNET/logs
   sudo cp /opt/complexnet/complexnet-api/logs/*.jsonl /media/ubuntu/COMPLEXNET/logs/
   sync
   ```
4. Expulsa la USB desde **Archivos** antes de sacarla.

Como cada archivo se llama como su nodo (`nodo-1.jsonl`, `nodo-2.jsonl`...),
los de los tres equipos quedan juntos en la misma carpeta. Después, en tu
computador:

```bash
python complexnet-api/examples/analizar_logs.py E:/logs
```

---

## Si algo falla

| Qué pasa | Qué hacer |
|---|---|
| El computador no arranca desde la USB | Revisa la tecla del menú de arranque (paso 6) y escoge la opción UEFI. Ubuntu funciona con Secure Boot activado. |
| Con toram se queda en negro o se reinicia | Le falta RAM (necesita unos 8 GB). En ese equipo arranca sin `toram`, pero entonces **la USB no se puede sacar** de ahí. El script te avisa. |
| `la tarjeta ... NO soporta el modo ad hoc (IBSS)` | Ese computador no puede entrar a la malla con su Wi-Fi. Usa otro computador, o una tarjeta Wi-Fi USB que soporte IBSS; las de chip Atheros AR9271 son conocidas por soportarlo. |
| `este Linux no trae batman-adv` | Mira la versión del kernel con `uname -r`. En WSL, `apt download linux-modules-extra-<esa versión>`, ponlo en `paquetes/` y vuelve a correr `preparar_usb.ps1`. El script lo instala solo. |
| `falta batctl` | La carpeta `paquetes/` no llegó a la USB. Vuelve a correr `preparar_usb.ps1` y revisa que no diga "faltan". |
| `setup_adhoc.sh` falla con "Device or resource busy" | NetworkManager sigue usando la tarjeta. Corre `sudo systemctl stop NetworkManager` y vuelve a correr el script. |
| Los nodos no se ven entre sí | En cada uno: `iw dev` debe decir `type IBSS` y `ssid complexnet`. `sudo batctl n` debe mostrar vecinos. Acerca los equipos. Revisa `rfkill list`: la Wi-Fi no puede estar bloqueada. |
| `no encuentro complexnet-api/` | La USB no está montada, o la ruta cambió. Mira el nombre real con `ls /media/ubuntu/`. |
| Un computador se reinició | Todo vivía en la RAM. Repite desde el paso 6 con el mismo número de nodo. |

---

## Para la sustentación

*"Los tres nodos corren desde la memoria RAM, sin disco y sin internet: una
sola USB lleva el sistema, el código y las dependencias. Eso es justamente
el escenario del proyecto: equipos que llegan a una zona sin infraestructura
y arman la red solos."*
