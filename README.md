<p align="center">
  <img src="complexnet-api/LOGO.jpg" alt="ComplexNet API" width="360">
</p>

# ComplexNet API

**Computadores que se organizan solos para comunicarse y trabajar juntos
cuando no hay internet.**

Proyecto integrador de **Sistemas Complejos** — Universidad Sergio Arboleda.
Felipe Morales Robelto y Juan David Sánchez Vargas.

---

## ¿Qué problema resuelve?

Cuando ocurre un desastre natural (un terremoto, una inundación, un
deslizamiento) lo primero que se cae es la comunicación: las antenas de
celular, la luz y el internet. Justo cuando los rescatistas más necesitan
coordinarse.

ComplexNet permite que un grupo de computadores pequeños (portátiles o
Raspberry Pi) que estén en la zona:

- **se encuentren solos**, sin que nadie los configure;
- **se manden mensajes y archivos**, sin internet y sin un servidor central;
- **se repartan el trabajo**: cada tarea la hace el equipo que esté en mejores
  condiciones;
- **sigan funcionando cuando uno se apaga**: los demás lo detectan y retoman
  su trabajo.

No hay un "jefe": todos los equipos siguen las mismas reglas sencillas y, de
todos juntos, sale una red organizada. En Sistemas Complejos eso se llama
**comportamiento emergente**.

## ¿Cómo funciona? (en un minuto)

```
  Aplicaciones        mensajería · sensores · IA de predicción · monitor
        │
  API (clase Nodo)    lo único que necesita conocer quien programa una aplicación
        │
  Servicios           descubrimiento · recursos · planificador · tareas ·
        │             recuperación · registro de eventos
  Comunicación        mensajes cortos por UDP, mensajes largos y archivos por TCP
        │
  B.A.T.M.A.N.        protocolo de Linux que lleva los mensajes de equipo en
        │             equipo, aunque haya que pasar por otros (red "en malla")
  Wi-Fi ad hoc        las tarjetas Wi-Fi se hablan directamente, sin router
```

1. Cada equipo pone su tarjeta Wi-Fi en **modo ad hoc**: las tarjetas se
   hablan directamente, como walkie-talkies, sin router.
2. **B.A.T.M.A.N.** encuentra el camino entre equipos aunque estén lejos y
   haya que pasar por otro.
3. Cada nodo **anuncia** cada 5 segundos que está vivo y **cómo se siente**
   (CPU, memoria, batería, calidad de la señal).
4. Si un nodo se calla 15 s queda **sospechoso**, y a los 30 s se da por
   **caído**.
5. Para repartir una tarea, cada nodo calcula un **puntaje** para sus vecinos
   y escoge al mejor:

   ```
   F = CPU libre + memoria libre + calidad de señal + confiabilidad − carga
   ```

6. Si el que estaba haciendo la tarea se cae, la tarea **se reasigna sola**.

## ¿Qué se puede hacer con él?

| Aplicación | Qué hace | Estado |
|---|---|---|
| **Mensajería** | Mensajes a uno, a un grupo o a todos; archivos (comprimidos cuando conviene); cálculos y pruebas de carga repartidos en la red | ✅ Lista |
| **Sensores** | Lectura de temperatura, presión y humedad; cada nodo guarda, comparte y procesa sus datos | 🔨 En desarrollo |
| **IA de predicción** | Con los datos de los sensores, predice cambios y detecta valores anormales (alertas de incendio o tormenta) | 📋 Planeada |
| **Monitor** | Muestra en vivo los recursos y las tareas de cada nodo | ✅ Listo |

## Probarlo en 2 minutos (en un solo computador)

Necesitas **Python 3.10 o más nuevo**. Funciona en Windows, Linux y macOS.

```bash
git clone https://github.com/lamaquina27/proyecto_SC.git
cd proyecto_SC/complexnet-api
pip install -r requirements.txt
```

Abre **tres terminales** y en cada una escribe:

```bash
python applications/mensajeria.py --local
```

En unos segundos cada terminal muestra `>> entro ...`: los nodos se
encontraron solos. Prueba en cualquiera:

```
lista                        ver quién está conectado
todos hola a todos           mensaje a todos
msg <nombre> hola            mensaje a uno (el nombre sale en "lista")
calc (10 + 20) * 2           una cuenta que hace el mejor nodo de la red
archivo <nombre> notas.txt   mandar un archivo
salir
```

En una cuarta terminal puedes abrir el monitor:

```bash
python applications/monitor.py --local
```

## Usarlo de verdad (varios equipos, sin internet)

Con equipos que tengan Linux y una tarjeta Wi-Fi que soporte el modo ad hoc:

```bash
sudo ./setup_adhoc.sh 1                          # en el equipo 1 (2, 3... en los demás)
cd complexnet-api
sudo python3 applications/mensajeria.py
```

Para el laboratorio se usa **una sola USB** con Ubuntu que se carga en la
memoria de cada equipo. El paso a paso está en
[`PREPARAR_USB.md`](PREPARAR_USB.md).

## Documentación

| Documento | Para quién | Qué tiene |
|---|---|---|
| [Manual del desarrollador](complexnet-api/docs/manual_desarrollador.md) | Quien quiere **hacer su propia aplicación** | Paso a paso con ejemplos, desde cero |
| [Manual técnico](complexnet-api/docs/api/manual.md) | Quien quiere **entender o modificar** el sistema | Cada operación, mensaje y parámetro |
| [Decisiones de diseño](complexnet-api/docs/diseno.md) | Quien pregunta **por qué** se hizo así | 29 decisiones justificadas |
| [Informe experimental](complexnet-api/docs/informe_experimental.md) | Quien quiere **ver los números** | Latencia, escalabilidad y tolerancia a fallos |
| [Cómo probarlo](COMO_PROBARLO.md) | Quien va a **demostrarlo** | Comprobaciones y guion del video |
| [Preparar la USB](PREPARAR_USB.md) | Quien va a **montar el laboratorio** | Ubuntu en RAM, paso a paso |

## Cómo está organizado el repositorio

```
proyecto_SC/
├── README.md                 este archivo
├── setup_adhoc.sh            monta la red en malla en un equipo Linux
├── arrancar_nodo.sh          prepara un equipo desde la USB y abre la mensajería
├── preparar_usb.ps1          copia el proyecto a la USB (desde Windows)
├── PREPARAR_USB.md · COMO_PROBARLO.md
└── complexnet-api/
    ├── src/                  el núcleo (la API)
    │   ├── api/              la clase Nodo: la puerta de entrada
    │   ├── communication/    mensajes, archivos y la interfaz de la malla
    │   ├── discovery/        quién está, cómo está y quién se cayó
    │   ├── resources/        mide CPU, memoria, señal, batería y carga
    │   ├── scheduler/        escoge el mejor nodo para cada tarea
    │   ├── tasks/            manda, ejecuta y reasigna tareas
    │   └── monitoring/       registro de eventos
    ├── applications/         las aplicaciones (mensajería, monitor...)
    ├── tests/                125 pruebas automáticas
    ├── experimentos/         mediciones de latencia, escalabilidad y fallos
    ├── examples/             demos pequeños y análisis de registros
    └── docs/                 manuales, decisiones e informe
```

## Pruebas

```bash
cd complexnet-api
python -m pytest tests -v        # 125 pruebas, unos 7 minutos
```

Todas corren en un solo computador; no necesitan la red real.

## Mediciones

```bash
cd complexnet-api
python experimentos/medir.py todo          # en un computador, ~10 min
sudo python3 experimentos/medir.py malla   # en la red real
python experimentos/graficas.py            # gráficas (necesita matplotlib)
```

Los resultados y su análisis están en el
[informe experimental](complexnet-api/docs/informe_experimental.md).

## Modelo matemático

La red se modela como un grafo que cambia con el tiempo, y cada nodo como un
vector de estado:

```
G(t) = (V(t), E(t))                    nodos y enlaces en el instante t
S_i(t) = [C_i, M_i, B_i, R_i, A_i]     CPU, memoria, ancho de banda, confiabilidad, disponibilidad
F(i,j) = w1·C + w2·M + w3·B + w4·R − w5·L
i* = argmax F(i,j)                     el nodo con mayor puntaje recibe la tarea j
```

El detalle está en las [decisiones de diseño](complexnet-api/docs/diseno.md),
secciones 18 y 19.
