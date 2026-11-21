<p align="center">
  <img src="complexnet-api/LOGO.jpg" alt="ComplexNet API" width="360">
</p>

# ComplexNet API
### Framework para Computación Descentralizada sobre Redes Ad hoc
**Proyecto Integrador — Sistemas Complejos (Corte 3)**  
**Universidad Sergio Arboleda** — Escuela de Ciencias Exactas e Ingeniería  
*Programa de Ciencias de la Computación e Inteligencia Artificial*  
**Autores:** Felipe Morales Robelto y Juan David Sánchez Vargas  
**Docente:** Joaquín F. Sánchez Cifuentes  
**Año:** 2026  

---

## 1. ¿Qué problema resuelve?

Cuando ocurre un desastre natural (un terremoto, una inundación o un colapso estructural), la infraestructura de telecomunicaciones convencional (antenas celulares, fibra óptica, internet y energía eléctrica) colapsa, aislando a las brigadas de emergencia en el momento más crítico.

**ComplexNet API** permite que un conjunto de computadores móviles y heterogéneos (computadores portátiles, Raspberry Pi y microcontroladores ESP32 como extensiones sensoriales) formen una red inalámbrica descentralizada sin depender de ningún servidor central:

- **Se encuentran solos:** Descubrimiento automático entre pares mediante protocolos reactivos y latidos periódicos.
- **Se comunican sin internet:** Mensajería directa punto a punto, difusión general y grupos multicast temáticos (p. ej. `"rescate"`).
- **Se reparten el trabajo:** Planificación descentralizada multi-criterio donde cada tarea la procesa el nodo con mejores condiciones de cómputo y señal.
- **Toleran fallos:** Si un nodo se desconecta o colapsa en medio de un cálculo, los vecinos lo detectan y reasignan la tarea automáticamente sin pérdida de datos.
- **Clasifican emergencias con Inteligencia Artificial:** Diagnóstico en tiempo real mediante un Árbol de Decisión CART nativo y explicable.

```
       [ ESP32 Sensor Edge ]
                 │ (USB / Telemetría Serial)
                 ▼
          ┌─────────────┐
          │   Nodo 1    │ (Nodo de Campo / Baliza)
          └──────┬──────┘
                 │
       (Malla Ad hoc Wi-Fi IBSS / B.A.T.M.A.N. Advanced)
                 │
        ┌────────┴────────┐
        ▼                 ▼
 ┌─────────────┐   ┌─────────────┐
 │   Nodo 2    │   │   Nodo 3    │
 │ Evaluador IA│   │   Monitor   │
 └─────────────┘   └─────────────┘
```

---

## 2. Modelo Conceptual y Matemático de Sistemas Complejos

El sistema modela la red como un **sistema complejo autoorganizado, robusto y adaptativo**:

1. **Grafo Dinámico de Red:**
   $$G(t) = (V(t), E(t))$$
   Donde $V(t)$ representa los nodos disponibles en el instante $t$, y $E(t)$ los enlaces activos entre ellos, adaptándose dinámicamente ante movilidad, fallos de batería o interferencias.

2. **Vector de Estado de los Nodos:**
   Cada nodo $v_i$ publica periódicamente su vector de recursos normalizado $[0, 1]$:
   $$S_i(t) = [C_i(t), M_i(t), B_i(t), R_i(t), A_i(t)]$$
   * **$C_i$**: Capacidad de CPU disponible ($1.0 - \text{carga}$).
   * **$M_i$**: Memoria RAM disponible ($\text{RAM}_{\text{libre}} / \text{RAM}_{\text{total}}$).
   * **$B_i$**: Calidad del enlace de red (métrica $TQ / 255$ provista por B.A.T.M.A.N. Advanced).
   * **$R_i$**: Nivel de reputación y confiabilidad histórica de tareas exitosas.
   * **$A_i$**: Disponibilidad del nodo ($A_i < 0.2$ filtra nodos sobrecargados).

3. **Planificador Distribuido (Función de Aptitud):**
   Para cada tarea $T_j$, el nodo solicitante selecciona al mejor ejecutor maximizando:
   $$F(i, j) = w_1 C_i + w_2 M_i + w_3 B_i + w_4 R_i - w_5 L_i$$
   $$i^* = \arg\max_{i \in V} F(i, j)$$
   Donde $L_i$ representa la carga actual de tareas asignadas al nodo $i$.

---

## 3. Las Tres Aplicaciones Descentralizadas (Fase 3)

| Aplicación | Qué hace | Estado |
|---|---|:---:|
| **1. Monitoreo Ambiental y Alertas** | Lectura física con ESP32 (DHT11, sensor de suelo capacitivo, GY-302 BH1750) y difusión automática de alarmas por multicast `"rescate"`. | ✅ Lista |
| **2. Cómputo Colaborativo y Balanceo** | Reparto de tareas matemáticas seguras (`calc` por AST) y estrés computacional en paralelo (`estres`). | ✅ Lista |
| **3. Inteligencia Artificial (CART)** | Diagnóstico perimetral en tiempo real (incendio, inundación, atrapado en escombros, calor extremo, normal). | ✅ Lista |
| **Panel de Supervisión (Monitor)** | Visualización en vivo en terminal del estado de la red, métricas de hardware y alertas de rescate. | ✅ Listo |

### Detalle de la Aplicación de Inteligencia Artificial (CART)

* **Fundamento Matemático (Impureza de Gini):**
  El clasificador particiona recursivamente el vector de características sensoriales `(temperatura, humedad_aire, suelo, luz)` optimizando la reducción de impureza en cada división:
  $$I_G(S) = 1 - \sum_{k=1}^{C} p_k^2$$
  $$\Delta I_G(S, f, \theta) = I_G(S) - \left( \frac{|S_L|}{|S|} I_G(S_L) + \frac{|S_R|}{|S|} I_G(S_R) \right)$$

* **¿Por qué un Árbol de Decisión CART frente a Redes Neuronales o SVM?**

| Criterio de Selección | Árbol de Decisión CART (Elegido) | Redes Neuronales (MLP) | Support Vector Machines (SVM) |
|---|:---:|:---:|:---:|
| **Explicabilidad (XAI)** | **Total:** Reglas lógicas transparentes y auditables | Nula ("Caja negra") | Baja (Depende de transformaciones) |
| **Entorno Efímero en RAM (`toram`)** | **0 dependencias pesadas:** Python puro nativo | Requiere PyTorch / TF (~500 MB) | Requiere Scikit-Learn (~150 MB) |
| **Tiempo de Inferencia** | **< 0.2 ms** (Ultrarrápido) | 15 - 50 ms | 5 - 15 ms |
| **Tolerancia a Sensores Parciales** | Alta (Particiones ortogonales) | Media | Sensible a escala y normalización |

> **Justificación en Rescate:** En una misión de rescate humano, las decisiones deben ser auditables. Un brigadista o perito puede inspeccionar la regla exacta que activó `POSIBLE_ATRAPADO_ESCOMBROS` (luz $\le 2.75$ lux y suelo seco) en lugar de depender de pesos opacos de una red neuronal.

* **Métricas Obtenidas en Validación:**
  * **Exactitud Global (Accuracy):** **97.5%** (390 aciertos sobre 400 muestras de prueba).
  * **F1-Scores por Categoría:** Normal (0.931), Incendio (1.000), Inundación (0.987), Escombros (0.964), Calor (0.993).

---

## 4. Documentación Completa del Proyecto

| Documento | Audiencia | Contenido |
|---|---|---|
| [Manual del Desarrollador](complexnet-api/docs/manual_desarrollador.md) | Desarrolladores de aplicaciones | Guía paso a paso para crear nuevos servicios sobre `Nodo`. |
| [Manual Técnico de la API](complexnet-api/docs/api/manual.md) | Diseñadores de sistemas | Protocolo de mensajes, formato JSON, enmarcado TCP y opciones. |
| [Decisiones de Diseño](complexnet-api/docs/diseno.md) | Evaluadores y arquitectos | Registro de 29 decisiones arquitectónicas justificadas. |
| [Matriz de Entregables — Corte 3](complexnet-api/docs/entregables_corte3.md) | Docente y evaluadores | Verificación de cumplimiento de los 10 requisitos oficiales. |
| [Informe Experimental — Corte 3](complexnet-api/docs/informe_experimental_corte3.md) | Comunidad académica | Análisis formal de los 5 puntos exigidos en la Sección 7.3. |
| [Informe Experimental — Mediciones Base](complexnet-api/docs/informe_experimental.md) | Análisis de red | Resultados numéricos de latencia, fallos y escalabilidad. |
| [Métricas del Árbol de Decisión](complexnet-api/docs/metricas_arbol_decision.txt) | Machine Learning | Reporte cuantitativo detallado y matriz de confusión del modelo. |
| [Cómo Probarlo](COMO_PROBARLO.md) | Brigadistas y sustentación | Guía paso a paso de pruebas, telemetría y guion del video. |
| [Preparar la USB](PREPARAR_USB.md) | Montaje de laboratorio | Guía para crear el instalador Ubuntu con `toram` sin internet. |

---

## 5. Organización del Repositorio

```
proyecto_SC/
├── README.md                      # Documentación maestra del repositorio
├── COMO_PROBARLO.md               # Guía paso a paso de verificación y demostración
├── PREPARAR_USB.md                # Manual para montar Ubuntu Live con toram
├── preparar_usb.ps1               # Script PowerShell para sincronizar la memoria USB
├── arrancar_nodo.sh               # Script de inicio del nodo en Linux / toram
├── setup_adhoc.sh                 # Configuración de interfaces Wi-Fi y batman-adv
│
└── complexnet-api/
    ├── README.md                  # Manual técnico de la biblioteca en Python
    ├── requirements.txt           # Dependencias básicas del entorno
    ├── applications/              # Capa 5: Aplicaciones descentralizadas
    │   ├── mensajeria.py          # Consola interactiva de brigada
    │   ├── monitor.py             # Monitor perimetral en tiempo real
    │   ├── operaciones.py         # Cómputo distribuido y estrés de CPU
    │   ├── arbol_decision.py      # Motor de IA: Clasificador de urgencias CART
    │   └── sensor_emergencia.py   # Lector USB de ESP32 + simulador de respaldo
    ├── scripts/                   # Entrenamiento del modelo de Machine Learning
    │   ├── dataset_emergencias.csv# Dataset con 2,000 muestras de entrenamiento
    │   └── entrenar_arbol.py      # Algoritmo CART nativo (Gini, matriz de confusión)
    ├── src/                       # Capas 2, 3 y 4: Núcleo de la API
    │   ├── api/                   # Fachada Nodo e Identidad persistente
    │   ├── communication/         # Sockets UDP/TCP, compresión y enmarcado
    │   ├── discovery/             # Vecinos, anuncios y detector de fallos
    │   ├── monitoring/            # Registro distribuido JSONL y Lamport
    │   ├── resources/             # Gestor del vector [C, M, B, R, A]
    │   ├── scheduler/             # Planificador distribuido F(i,j)
    │   └── tasks/                 # Gestor de tareas y recuperación por caídas
    ├── tests/                     # Suite de pruebas automatizadas (128+ tests)
    │   └── test_ia_urgencias.py   # Pruebas de la IA distribuida y tolerancia a fallos
    ├── experimentos/              # Mediciones de desempeño en red y gráficas
    └── docs/                      # Manuales, decisiones e informes de entrega
```

---

## 6. Guía Rápida de Uso

### Opción A: Pruebas Locales (Windows o Linux en un solo equipo)

1. **Instalar dependencias:**
   ```bash
   cd complexnet-api
   pip install -r requirements.txt pyserial
   ```

2. **Terminal 1 — Monitor de la Red:**
   ```bash
   python applications/monitor.py --local
   ```

3. **Terminal 2 — Nodo Sensor (conecta tu ESP32 o usa el simulador):**
   ```bash
   python applications/mensajeria.py --local --nombre nodo-sensor
   ```

4. **Terminal 3 — Nodo Brigada (Evaluador de IA):**
   ```bash
   python applications/mensajeria.py --local --nombre nodo-brigada
   ```

**Comandos útiles dentro de `mensajeria.py`:**
* `sensor`: Muestra las lecturas físicas de la ESP32 o telemetría simulada.
* `evaluar`: Envía la telemetría a la red para clasificación con IA en el mejor nodo.
* `simular incendio` (o `escombros`, `inundacion`, `calor`, `normal`): Inyecta escenarios de prueba.
* `vigilancia 3`: Monitoreo perimetral automático que proyecta alarmas críticas en el monitor.
* `calc (10 + 20) * 2`: Cálculo distribuido asignado por $F(i,j)$.
* `estres 15 4`: Reparte 4 tareas de estrés computacional entre los nodos.

---

### Opción B: Despliegue en el Laboratorio (Red Ad hoc con USB `toram`)

Se utiliza una sola memoria USB booteable con Ubuntu 24.04:

1. **Sincronizar la USB en Windows:**
   ```powershell
   cd C:\Users\moral\Downloads\proyecto_SC
   powershell -ExecutionPolicy Bypass -File .\preparar_usb.ps1 -Unidad E:
   ```

2. **Arrancar en cada computador:**
   * Inicia el PC desde la USB, presiona `e` en el menú GRUB y añade `toram`.
   * En el PC 1 (con la ESP32 conectada por USB):
     ```bash
     sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 1
     ```
   * En el PC 2:
     ```bash
     sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 2
     ```
   * En el PC 3:
     ```bash
     sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 3
     ```
   El script copia todo a la RAM (`/opt/complexnet`), desmonta la USB para llevarla al siguiente equipo, configura `bat0` y abre la aplicación.

---

## 7. Pruebas Automatizadas

```bash
cd complexnet-api

# Ejecutar pruebas de la Inteligencia Artificial y tolerancia a fallos
python -m pytest tests/test_ia_urgencias.py -v

# Ejecutar suite completa
python -m pytest tests/ -v
```

---

## 8. Licencia
Desarrollado con fines académicos en el marco de la asignatura Sistemas Complejos de la Universidad Sergio Arboleda.
