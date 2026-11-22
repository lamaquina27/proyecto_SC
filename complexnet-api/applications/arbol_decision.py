"""
Modelo de Inteligencia Artificial para ComplexNet API (Fase 3).
Clasificador de Urgencias en Zonas de Desastre mediante Arbol de Decision (CART).

Variables de entrada:
    temp: Temperatura ambiental (C)
    hum_aire: Humedad relativa del aire (%)
    suelo: Nivel de humedad en terreno (%)
    luz: Intensidad luminica (lux)

Cero dependencias externas: corre de forma nativa en cualquier nodo con toram.
"""

CLASES = [
    "NORMAL_ESTABLE",
    "ALERTA_INCENDIO",
    "ALERTA_INUNDACION_LODO",
    "POSIBLE_ATRAPADO_ESCOMBROS",
    "ALERTA_CALOR_EXTREMO"
]

ACCIONES_RECOMENDADAS = {
    "NORMAL_ESTABLE": "Monitoreo perimetral rutinario. Sin riesgo inminente.",
    "ALERTA_INCENDIO": "EVACUACION INMEDIATA. Despacho urgente de brigada contra incendios y cortafuegos.",
    "ALERTA_INUNDACION_LODO": "ALERTA TEMPRANA. Evacuar a cota alta por riesgo de desbordamiento o deslizamiento.",
    "POSIBLE_ATRAPADO_ESCOMBROS": "RESCATE USAR PRIORITARIO. Despachar equipo de busqueda canina y remocion de escombros.",
    "ALERTA_CALOR_EXTREMO": "PRECAUCION BRIGADA. Hidratacion y rotacion de personal por estres termico severo."
}


def _evaluar_arbol(temp, hum_aire, suelo, luz):
    if hum_aire <= 24.38:
        return {
            'clase': 'ALERTA_INCENDIO',
            'codigo': 1,
            'confianza': 1.0,
            'distribucion': {'ALERTA_INCENDIO': 1.0}
        }
    else:
        if suelo <= 84.82:
            if luz <= 2.75:
                return {
                    'clase': 'POSIBLE_ATRAPADO_ESCOMBROS',
                    'codigo': 3,
                    'confianza': 1.0,
                    'distribucion': {'POSIBLE_ATRAPADO_ESCOMBROS': 1.0}
                }
            else:
                if temp <= 36.33:
                    return {
                        'clase': 'NORMAL_ESTABLE',
                        'codigo': 0,
                        'confianza': 0.913,
                        'distribucion': {'NORMAL_ESTABLE': 0.913, 'ALERTA_CALOR_EXTREMO': 0.04, 'POSIBLE_ATRAPADO_ESCOMBROS': 0.017, 'ALERTA_INUNDACION_LODO': 0.029}
                    }
                else:
                    return {
                        'clase': 'ALERTA_CALOR_EXTREMO',
                        'codigo': 4,
                        'confianza': 0.978,
                        'distribucion': {'ALERTA_CALOR_EXTREMO': 0.978, 'ALERTA_INCENDIO': 0.022}
                    }
        else:
            return {
                'clase': 'ALERTA_INUNDACION_LODO',
                'codigo': 2,
                'confianza': 1.0,
                'distribucion': {'ALERTA_INUNDACION_LODO': 1.0}
            }



# Constantes de calibracion provisional del sensor capacitivo de suelo (ADC 12 bits)
VALOR_ADC_SECO = 3900.0    # Lectura del sensor en aire / seco total (0%)
VALOR_ADC_MOJADO = 1400.0  # Lectura del sensor sumergido / mojado (100%)


def calibrar_suelo_adc(valor, adc_seco=VALOR_ADC_SECO, adc_mojado=VALOR_ADC_MOJADO):
    """
    Convierte lectura ADC (0-4095) del sensor capacitivo a porcentaje (0-100%).
    Escala inversa: mayor valor ADC = menor humedad (seco).
    Acota estrictamente el porcentaje resultante entre 0.0 y 100.0%.
    """
    if valor is None:
        return 40.0
    val = float(valor)
    if val <= 100.0:
        return round(max(0.0, min(100.0, val)), 1)
    pct = 100.0 * (adc_seco - val) / (adc_seco - adc_mojado)
    return round(max(0.0, min(100.0, pct)), 1)


def clasificar_urgencia(datos):
    """
    Operacion distribuida registrada en ComplexNet API.
    Acepta un diccionario con las lecturas o una lista [temp, hum_aire, suelo, luz].
    """
    if isinstance(datos, dict):
        temp = float(datos["temp"] if datos.get("temp") is not None else 22.0)
        hum_aire = float(datos["hum_aire"] if datos.get("hum_aire") is not None else 50.0)
        suelo_val = datos.get("suelo")
        suelo = calibrar_suelo_adc(suelo_val)
        luz = float(datos["luz"] if datos.get("luz") is not None else 1000.0)
    elif isinstance(datos, (list, tuple)):
        temp, hum_aire, suelo_raw, luz = [float(x) for x in datos[:4]]
        suelo = calibrar_suelo_adc(suelo_raw)
    else:
        raise ValueError(f"formato de datos invalido: {datos}")

    resultado = _evaluar_arbol(temp, hum_aire, suelo, luz)
    clase = resultado["clase"]
    resultado["accion_recomendada"] = ACCIONES_RECOMENDADAS.get(clase, "Verificar situacion.")
    resultado["parametros"] = {
        "temp": temp,
        "hum_aire": hum_aire,
        "suelo": round(suelo, 1),
        "luz": round(luz, 1)
    }
    return resultado


if __name__ == "__main__":
    pruebas = [
        {"temp": 22.0, "hum_aire": 60.0, "suelo": 40.0, "luz": 1500.0},  # Normal
        {"temp": 62.0, "hum_aire": 14.0, "suelo": 10.0, "luz": 5000.0},  # Incendio
        {"temp": 18.0, "hum_aire": 92.0, "suelo": 95.0, "luz": 300.0},   # Inundacion
        {"temp": 19.5, "hum_aire": 65.0, "suelo": 45.0, "luz": 0.8},     # Escombros
        {"temp": 41.0, "hum_aire": 48.0, "suelo": 28.0, "luz": 2200.0},  # Calor
    ]
    for p in pruebas:
        r = clasificar_urgencia(p)
        print(f"Entrada: {p} -> Urgencia: {r['clase']} (Confianza: {r['confianza']*100:.0f}%)")
