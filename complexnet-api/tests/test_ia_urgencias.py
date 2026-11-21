"""
Pruebas de la Aplicacion 3: Inteligencia Artificial (Arbol de Decision) en ComplexNet API.
Verifica:
    1. Exactitud de clasificacion en casos de emergencia locales.
    2. Ejecucion distribuida de la tarea 'clasificar_urgencia' entre nodos por la API.
    3. Tolerancia a fallos: reasignacion automatica si el nodo evaluador se desconecta.
"""

import threading
import time
import pytest

from src.api import Nodo
from src.discovery import Vecino, ACTIVO
from applications.arbol_decision import clasificar_urgencia

DIFUSION = "127.255.255.255"


def test_arbol_decision_casos_locales():
    # Caso 1: Normal
    r = clasificar_urgencia({"temp": 22.0, "hum_aire": 60.0, "suelo": 40.0, "luz": 1500.0})
    assert r["clase"] == "NORMAL_ESTABLE"
    assert r["confianza"] > 0.9
    assert "Monitoreo" in r["accion_recomendada"]

    # Caso 2: Incendio
    r = clasificar_urgencia({"temp": 65.0, "hum_aire": 12.0, "suelo": 8.0, "luz": 4800.0})
    assert r["clase"] == "ALERTA_INCENDIO"
    assert "EVACUACION" in r["accion_recomendada"].upper()

    # Caso 3: Inundacion / lodo
    r = clasificar_urgencia({"temp": 18.0, "hum_aire": 92.0, "suelo": 95.0, "luz": 300.0})
    assert r["clase"] == "ALERTA_INUNDACION_LODO"
    assert "COTA ALTA" in r["accion_recomendada"].upper()

    # Caso 4: Atrapado bajo escombros
    r = clasificar_urgencia({"temp": 20.0, "hum_aire": 65.0, "suelo": 45.0, "luz": 0.5})
    assert r["clase"] == "POSIBLE_ATRAPADO_ESCOMBROS"
    assert "USAR" in r["accion_recomendada"].upper()

    # Caso 5: Calor extremo
    r = clasificar_urgencia({"temp": 40.5, "hum_aire": 46.0, "suelo": 28.0, "luz": 2400.0})
    assert r["clase"] == "ALERTA_CALOR_EXTREMO"
    assert "HIDRATACION" in r["accion_recomendada"].upper()


def test_ia_distribuida_dos_nodos():
    """Un nodo solicita la clasificacion de IA y otro nodo de la red la ejecuta."""
    n1 = Nodo("nodo-sensor", interfaz="lo", difusion=DIFUSION,
              puerto_udp=5610, puerto_tcp=5611, carpeta_logs=None)
    n2 = Nodo("nodo-evaluador-ia", interfaz="lo", difusion=DIFUSION,
              puerto_udp=5612, puerto_tcp=5613, carpeta_logs=None,
              servicios=["ia_urgencias"])

    n2.registrar_operacion("clasificar_urgencia", clasificar_urgencia)

    try:
        n1.iniciar()
        n2.iniciar()

        # Registrar a n2 como vecino conocido de n1
        v = Vecino(n2.node_id, n2.nombre, "127.0.0.1", n2.puerto,
                   servicios=["clasificar_urgencia", "ia_urgencias"])
        v.status = ACTIVO
        v.estado = {"cpu": 0.9, "memoria": 0.8, "ancho_banda": 1.0, "carga": 0.0, "capacidad": 1}
        n1.descubrimiento.vecinos[n2.node_id] = v

        datos_incendio = {"temp": 60.0, "hum_aire": 15.0, "suelo": 10.0, "luz": 4000.0}
        futuro = n1.enviar_tarea_async("clasificar_urgencia", datos_incendio, timeout=5.0)
        resultado = futuro.result(timeout=5.0)

        assert resultado["clase"] == "ALERTA_INCENDIO"
        assert futuro.tarea.ejecutor == n2.node_id
        assert "EVACUACION" in resultado["accion_recomendada"]
    finally:
        n1.detener()
        n2.detener()


def test_ia_tolerancia_a_fallos_reasignacion():
    """Si el nodo ejecutor de IA se cae a mitad del analisis, otro nodo asume la tarea."""
    n1 = Nodo("nodo-origen", interfaz="lo", difusion=DIFUSION,
              puerto_udp=5620, puerto_tcp=5621, carpeta_logs=None)
    n2 = Nodo("nodo-eval-1", interfaz="lo", difusion=DIFUSION,
              puerto_udp=5622, puerto_tcp=5623, carpeta_logs=None,
              servicios=["ia_urgencias"])
    n3 = Nodo("nodo-eval-2", interfaz="lo", difusion=DIFUSION,
              puerto_udp=5624, puerto_tcp=5625, carpeta_logs=None,
              servicios=["ia_urgencias"])

    # Nodo 2 simula caerse
    soltar = threading.Event()

    def bloqueada(datos):
        soltar.wait(10.0)
        return clasificar_urgencia(datos)

    n2.registrar_operacion("clasificar_urgencia", bloqueada)
    n3.registrar_operacion("clasificar_urgencia", clasificar_urgencia)

    try:
        n1.iniciar()
        n2.iniciar()
        n3.iniciar()

        # Registrar n2 y n3 en n1. Ponemos a n2 con mejor CPU para que el planificador F(i,j) lo elija primero
        v2 = Vecino(n2.node_id, n2.nombre, "127.0.0.1", n2.puerto,
                    servicios=["clasificar_urgencia", "ia_urgencias"])
        v2.status = ACTIVO
        v2.estado = {"cpu": 0.95, "memoria": 0.9, "ancho_banda": 1.0, "carga": 0.0, "capacidad": 1}

        v3 = Vecino(n3.node_id, n3.nombre, "127.0.0.1", n3.puerto,
                    servicios=["clasificar_urgencia", "ia_urgencias"])
        v3.status = ACTIVO
        v3.estado = {"cpu": 0.50, "memoria": 0.5, "ancho_banda": 1.0, "carga": 0.0, "capacidad": 1}

        n1.descubrimiento.vecinos[n2.node_id] = v2
        n1.descubrimiento.vecinos[n3.node_id] = v3

        # Enviar tarea de emergencia con escombros
        datos_escombros = {"temp": 19.0, "hum_aire": 65.0, "suelo": 40.0, "luz": 0.5}
        # Con timeout corto de 2.0 s para detectar que n2 no responde a tiempo
        futuro = n1.enviar_tarea_async("clasificar_urgencia", datos_escombros, timeout=2.0)

        # Esperamos a que la tarea sea enviada a n2
        time.sleep(0.3)
        assert futuro.tarea.ejecutor == n2.node_id

        # Simulamos que n2 se cae o desconecta
        n2.detener(despedirse=False)

        # La recuperacion por tiempo vencido reasigna a n3
        resultado = futuro.result(timeout=8.0)

        assert resultado["clase"] == "POSIBLE_ATRAPADO_ESCOMBROS"
        assert futuro.tarea.ejecutor == n3.node_id
        assert futuro.tarea.intentos >= 2
    finally:
        soltar.set()
        n1.detener()
        n2.detener()
        n3.detener()
