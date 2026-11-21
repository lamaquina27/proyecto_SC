"""
Entrenamiento y evaluacion del modelo de Inteligencia Artificial para ComplexNet API.
Aplicacion 3: Clasificador de urgencias en zonas de desastre mediante Arbol de Decision (CART).

Genera un dataset sintetico con parametros ambientales reales de emergencias,
entrena un Arbol de Decision (CART por impureza de Gini), calcula metricas
experimentales (Accuracy, Matriz de Confusion, Precision, Recall) y exporta
el clasificador a applications/arbol_decision.py sin dependencias externas.
"""

import csv
import json
import math
import os
import random
import sys

random.seed(42)

CLASES = [
    "NORMAL_ESTABLE",
    "ALERTA_INCENDIO",
    "ALERTA_INUNDACION_LODO",
    "POSIBLE_ATRAPADO_ESCOMBROS",
    "ALERTA_CALOR_EXTREMO",
]

NOMBRES_FEATURES = ["temp", "hum_aire", "suelo", "luz"]


def generar_dataset(n_muestras=2000):
    datos = []
    por_clase = n_muestras // len(CLASES)

    # 1. NORMAL_ESTABLE: temperatura templada, humedad normal, suelo normal,
    # abarca desde exteriores (1000-5000 lux) hasta interiores/noche (12-300 lux)
    for _ in range(por_clase):
        t = random.gauss(22.0, 3.5)
        ha = random.gauss(55.0, 8.0)
        s = random.gauss(40.0, 10.0)
        # 50% interiores (15 a 400 lux), 50% exteriores iluminados (400 a 4000 lux)
        if random.random() < 0.5:
            l = random.uniform(12.0, 400.0)
        else:
            l = random.uniform(400.0, 3500.0)
        t = max(14.0, min(33.0, t))
        ha = max(35.0, min(75.0, ha))
        s = max(15.0, min(65.0, s))
        datos.append([round(t, 2), round(ha, 2), round(s, 2), round(l, 1), 0])

    # 2. ALERTA_INCENDIO: temp alta (>48C), hum_aire muy baja (<25%), suelo seco, luz alta
    for _ in range(por_clase):
        t = random.gauss(58.0, 7.0)
        ha = random.gauss(16.0, 4.0)
        s = random.gauss(12.0, 5.0)
        l = max(500.0, random.gauss(4500.0, 1500.0))
        t = max(45.0, min(85.0, t))
        ha = max(5.0, min(28.0, ha))
        s = max(0.0, min(25.0, s))
        datos.append([round(t, 2), round(ha, 2), round(s, 2), round(l, 1), 1])

    # 3. ALERTA_INUNDACION_LODO: suelo saturado (>82%), hum_aire alta, temp moderada
    for _ in range(por_clase):
        t = random.gauss(20.0, 4.0)
        ha = random.gauss(88.0, 5.0)
        s = random.gauss(92.0, 4.0)
        l = max(10.0, random.gauss(600.0, 300.0))
        t = max(10.0, min(30.0, t))
        ha = max(75.0, min(100.0, ha))
        s = max(80.0, min(100.0, s))
        datos.append([round(t, 2), round(ha, 2), round(s, 2), round(l, 1), 2])

    # 4. POSIBLE_ATRAPADO_ESCOMBROS: luz casi nula (<5 lux), suelo y temp estables
    for _ in range(por_clase):
        t = random.gauss(19.0, 3.0)
        ha = random.gauss(65.0, 10.0)
        s = random.gauss(50.0, 15.0)
        l = max(0.0, random.gauss(1.2, 0.8))
        t = max(10.0, min(28.0, t))
        ha = max(40.0, min(80.0, ha))
        s = max(20.0, min(75.0, s))
        l = min(4.5, l)
        datos.append([round(t, 2), round(ha, 2), round(s, 2), round(l, 1), 3])

    # 5. ALERTA_CALOR_EXTREMO: temp alta (37 - 44C), hum_aire moderada (no incendio aun)
    for _ in range(por_clase):
        t = random.gauss(40.0, 2.0)
        ha = random.gauss(45.0, 7.0)
        s = random.gauss(30.0, 8.0)
        l = max(200.0, random.gauss(2500.0, 600.0))
        t = max(36.0, min(44.0, t))
        ha = max(32.0, min(65.0, ha))
        s = max(15.0, min(50.0, s))
        datos.append([round(t, 2), round(ha, 2), round(s, 2), round(l, 1), 4])

    random.shuffle(datos)
    return datos


class NodoArbol:
    def __init__(self, feature=None, umbral=None, izquierda=None, derecha=None, valor=None, prob=None):
        self.feature = feature
        self.umbral = umbral
        self.izquierda = izquierda
        self.derecha = derecha
        self.valor = valor
        self.prob = prob or {}

    @property
    def es_hoja(self):
        return self.valor is not None


def gini(etiquetas):
    if not etiquetas:
        return 0.0
    total = len(etiquetas)
    conteos = {}
    for y in etiquetas:
        conteos[y] = conteos.get(y, 0) + 1
    impureza = 1.0
    for c in conteos.values():
        p = c / total
        impureza -= p * p
    return impureza


def mejor_particion(filas):
    mejor_gini = 1.0
    mejor_feat = None
    mejor_umbral = None
    n = len(filas)
    etiquetas_actuales = [f[-1] for f in filas]
    gini_base = gini(etiquetas_actuales)

    if gini_base == 0:
        return None, None

    for feat_idx in range(len(NOMBRES_FEATURES)):
        valores = sorted(list(set(f[feat_idx] for f in filas)))
        if len(valores) <= 1:
            continue
        umbrales = [(valores[i] + valores[i + 1]) / 2.0 for i in range(len(valores) - 1)]
        # Para eficiencia, muestreamos a lo sumo 25 umbrales equiespaciados
        if len(umbrales) > 25:
            paso = len(umbrales) // 25
            umbrales = umbrales[::paso]

        for u in umbrales:
            izq = [f[-1] for f in filas if f[feat_idx] <= u]
            der = [f[-1] for f in filas if f[feat_idx] > u]
            if not izq or not der:
                continue
            g = (len(izq) / n) * gini(izq) + (len(der) / n) * gini(der)
            if g < mejor_gini:
                mejor_gini = g
                mejor_feat = feat_idx
                mejor_umbral = u

    return mejor_feat, mejor_umbral


def construir_arbol(filas, prof=0, max_prof=4, min_muestras=10):
    etiquetas = [f[-1] for f in filas]
    conteos = {}
    for y in etiquetas:
        conteos[y] = conteos.get(y, 0) + 1
    clase_predilecta = max(conteos.items(), key=lambda kv: kv[1])[0]
    total = len(etiquetas)
    probs = {CLASES[k]: round(v / total, 3) for k, v in conteos.items()}

    # Condiciones de parada
    if prof >= max_prof or len(filas) < min_muestras or len(conteos) == 1:
        return NodoArbol(valor=clase_predilecta, prob=probs)

    feat, umbral = mejor_particion(filas)
    if feat is None:
        return NodoArbol(valor=clase_predilecta, prob=probs)

    izq_filas = [f for f in filas if f[feat] <= umbral]
    der_filas = [f for f in filas if f[feat] > umbral]

    if not izq_filas or not der_filas:
        return NodoArbol(valor=clase_predilecta, prob=probs)

    izq = construir_arbol(izq_filas, prof + 1, max_prof, min_muestras)
    der = construir_arbol(der_filas, prof + 1, max_prof, min_muestras)
    return NodoArbol(feature=feat, umbral=umbral, izquierda=izq, derecha=der, prob=probs)


def predecir(nodo, x):
    if nodo.es_hoja:
        return nodo.valor, nodo.prob
    if x[nodo.feature] <= nodo.umbral:
        return predecir(nodo.izquierda, x)
    return predecir(nodo.derecha, x)


def generar_codigo_python(nodo, indent=4):
    esp = " " * indent
    if nodo.es_hoja:
        nombre_clase = CLASES[nodo.valor]
        prob_max = nodo.prob.get(nombre_clase, 1.0)
        return (
            f"{esp}return {{\n"
            f"{esp}    'clase': '{nombre_clase}',\n"
            f"{esp}    'codigo': {nodo.valor},\n"
            f"{esp}    'confianza': {prob_max},\n"
            f"{esp}    'distribucion': {nodo.prob}\n"
            f"{esp}}}\n"
        )
    feat_nom = NOMBRES_FEATURES[nodo.feature]
    u = round(nodo.umbral, 2)
    codigo = f"{esp}if {feat_nom} <= {u}:\n"
    codigo += generar_codigo_python(nodo.izquierda, indent + 4)
    codigo += f"{esp}else:\n"
    codigo += generar_codigo_python(nodo.derecha, indent + 4)
    return codigo


def evaluar(arbol, test_data):
    y_true = [f[-1] for f in test_data]
    y_pred = []
    for f in test_data:
        pred, _ = predecir(arbol, f[:4])
        y_pred.append(pred)

    n = len(y_true)
    aciertos = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    acc = aciertos / n

    # Matriz de confusion
    k = len(CLASES)
    matriz = [[0] * k for _ in range(k)]
    for yt, yp in zip(y_true, y_pred):
        matriz[yt][yp] += 1

    reporte = []
    reporte.append(f"Precision Global (Accuracy): {acc * 100:.2f}%\n")
    reporte.append("Matriz de Confusion (Filas=Real, Columnas=Prediccion):")
    encabezado = " " * 28 + " ".join(f"[{i}]" for i in range(k))
    reporte.append(encabezado)
    for i in range(k):
        fila_str = f"{CLASES[i][:26]:<26} " + " ".join(f"{matriz[i][j]:4d}" for j in range(k))
        reporte.append(fila_str)

    reporte.append("\nMetricas por Clase:")
    for i in range(k):
        tp = matriz[i][i]
        fp = sum(matriz[r][i] for r in range(k) if r != i)
        fn = sum(matriz[i][c] for c in range(k) if c != i)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        reporte.append(f"  [{i}] {CLASES[i]}:")
        reporte.append(f"      Precision={prec*100:.1f}%, Recall={rec*100:.1f}%, F1-Score={f1:.3f}")

    return acc, "\n".join(reporte)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(base_dir)

    print("=== Generando Dataset Sintetico de Desastres ===")
    datos = generar_dataset(2000)
    csv_path = os.path.join(base_dir, "dataset_emergencias.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(NOMBRES_FEATURES + ["clase_codigo", "clase_nombre"])
        for fila in datos:
            w.writerow(fila + [CLASES[fila[-1]]])
    print(f"Dataset guardado en: {csv_path} ({len(datos)} registros)")

    # Split 80% train, 20% test
    corte = int(len(datos) * 0.8)
    train_data = datos[:corte]
    test_data = datos[corte:]

    print(f"Entrenando Arbol de Decision (CART) con {len(train_data)} muestras...")
    arbol = construir_arbol(train_data, max_prof=4, min_muestras=10)

    print("Evaluando en conjunto de prueba...")
    acc, reporte_texto = evaluar(arbol, test_data)
    print("\n" + reporte_texto)

    # Guardar reporte de metricas para el informe
    docs_dir = os.path.join(repo_dir, "docs")
    reporte_path = os.path.join(docs_dir, "metricas_arbol_decision.txt")
    with open(reporte_path, "w", encoding="utf-8") as f:
        f.write("REPORTE EXPERIMENTAL DE CLASIFICACION - CORTE 3\n")
        f.write("Modelo: Arbol de Decision (CART, Max Profundidad = 4)\n")
        f.write("=" * 60 + "\n\n")
        f.write(reporte_texto)
    print(f"\nReporte guardado en: {reporte_path}")

    # Exportar aplicacion arbol_decision.py
    app_path = os.path.join(repo_dir, "applications", "arbol_decision.py")
    arbol_codigo = generar_codigo_python(arbol, indent=4)

    contenido_app = f'''"""
Modelo de Inteligencia Artificial para ComplexNet API (Fase 3).
Clasificador de Urgencias en Zonas de Desastre mediante Arbol de Decision (CART).

Variables de entrada:
    temp: Temperatura ambiental (C)
    hum_aire: Humedad relativa del aire (%)
    suelo: Nivel de humedad en terreno (%)
    luz: Intensidad luminica (lux)

Cero dependencias externas: corre de forma nativa en cualquier nodo con toram.
"""

CLASES = {json.dumps(CLASES, indent=4)}

ACCIONES_RECOMENDADAS = {{
    "NORMAL_ESTABLE": "Monitoreo perimetral rutinario. Sin riesgo inminente.",
    "ALERTA_INCENDIO": "EVACUACION INMEDIATA. Despacho urgente de brigada contra incendios y cortafuegos.",
    "ALERTA_INUNDACION_LODO": "ALERTA TEMPRANA. Evacuar a cota alta por riesgo de desbordamiento o deslizamiento.",
    "POSIBLE_ATRAPADO_ESCOMBROS": "RESCATE USAR PRIORITARIO. Despachar equipo de busqueda canina y remocion de escombros.",
    "ALERTA_CALOR_EXTREMO": "PRECAUCION BRIGADA. Hidratacion y rotacion de personal por estres termico severo."
}}


def _evaluar_arbol(temp, hum_aire, suelo, luz):
{arbol_codigo}


def clasificar_urgencia(datos):
    """
    Operacion distribuida registrada en ComplexNet API.
    Acepta un diccionario con las lecturas o una lista [temp, hum_aire, suelo, luz].
    """
    if isinstance(datos, dict):
        temp = float(datos["temp"] if datos.get("temp") is not None else 22.0)
        hum_aire = float(datos["hum_aire"] if datos.get("hum_aire") is not None else 50.0)
        suelo_val = datos.get("suelo")
        if suelo_val is None:
            suelo = 40.0
        elif float(suelo_val) > 100.0:
            adc = float(suelo_val)
            suelo = max(0.0, min(100.0, 100.0 * (1.0 - (adc - 1200.0) / 2895.0)))
        else:
            suelo = float(suelo_val)
        luz = float(datos["luz"] if datos.get("luz") is not None else 1000.0)
    elif isinstance(datos, (list, tuple)):
        temp, hum_aire, suelo, luz = [float(x) for x in datos[:4]]
    else:
        raise ValueError(f"formato de datos invalido: {{datos}}")

    resultado = _evaluar_arbol(temp, hum_aire, suelo, luz)
    clase = resultado["clase"]
    resultado["accion_recomendada"] = ACCIONES_RECOMENDADAS.get(clase, "Verificar situacion.")
    resultado["parametros"] = {{
        "temp": temp,
        "hum_aire": hum_aire,
        "suelo": round(suelo, 1),
        "luz": round(luz, 1)
    }}
    return resultado


if __name__ == "__main__":
    pruebas = [
        {{"temp": 22.0, "hum_aire": 60.0, "suelo": 40.0, "luz": 1500.0}},  # Normal
        {{"temp": 62.0, "hum_aire": 14.0, "suelo": 10.0, "luz": 5000.0}},  # Incendio
        {{"temp": 18.0, "hum_aire": 92.0, "suelo": 95.0, "luz": 300.0}},   # Inundacion
        {{"temp": 19.5, "hum_aire": 65.0, "suelo": 45.0, "luz": 0.8}},     # Escombros
        {{"temp": 41.0, "hum_aire": 48.0, "suelo": 28.0, "luz": 2200.0}},  # Calor
    ]
    for p in pruebas:
        r = clasificar_urgencia(p)
        print(f"Entrada: {{p}} -> Urgencia: {{r['clase']}} (Confianza: {{r['confianza']*100:.0f}}%)")
'''

    with open(app_path, "w", encoding="utf-8") as f:
        f.write(contenido_app)
    print(f"Clasificador de IA generado en: {app_path}")


if __name__ == "__main__":
    main()
