"""
Pruebas de las operaciones de la mensajeria (applications/operaciones.py).

    python3 -m pytest tests/test_operaciones.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "applications")

from operaciones import (ExpresionInvalida, calcular, es_primo, estresar,
                         quemar)


# ------------------------------------------------------------ calcular

@pytest.mark.parametrize("expresion, esperado", [
    ("10 + 20", 30),
    ("(10 + 20) * 2^3", 240),
    ("2 ** 10", 1024),
    ("7 // 2 + 7 % 2", 4),
    ("-3 + +5", 2),
    ("sqrt(16) + abs(-2)", 6.0),
    ("max(1, 5, 3) - min(4, 2)", 3),
    ("factorial(5)", 120),
    ("round(pi, 2)", 3.14),
])
def test_calcula_expresiones(expresion, esperado):
    assert calcular(expresion) == esperado


def test_funciones_con_decimales():
    assert calcular("sin(pi / 2)") == pytest.approx(1.0)
    assert calcular("log(e)") == pytest.approx(1.0)


@pytest.mark.parametrize("expresion", [
    "__import__('os').system('echo hola')",
    "open('archivo.txt')",
    "(1).__class__",
    "x + 1",
    "[1, 2, 3]",
    "'texto' * 3",
    "lambda: 1",
    "2 ** 100000",
    "(10 ** 1000) ** 1000",
    "9 ** 9999 * 9 ** 9999",
    "factorial(100000)",
    "",
    "1 +",
    "1" * 300,
])
def test_rechaza_lo_que_no_es_matematica(expresion):
    with pytest.raises(ExpresionInvalida):
        calcular(expresion)


def test_los_errores_de_aritmetica_salen_como_tales():
    with pytest.raises(ZeroDivisionError):
        calcular("1 / 0")
    with pytest.raises(ValueError):
        calcular("sqrt(-1)")


# ------------------------------------------------------------ estresar

def test_es_primo():
    primos = [n for n in range(30) if es_primo(n)]
    assert primos == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]


def test_quemar_trabaja_el_tiempo_pedido():
    r = quemar(1.0, mb=5, desde=1_000)
    assert 1.0 <= r["segundos"] < 1.5
    assert r["revisados"] > 1000
    assert r["primos"] > 0 and es_primo(r["mayor"])
    assert r["mb"] == 5


def test_estresar_corre_en_otro_proceso():
    r = estresar({"segundos": 1, "desde": 100})
    assert r["pid"] != os.getpid()
    assert r["revisados"] > 0


def test_estresar_respeta_los_limites():
    r = estresar({"segundos": 0, "mb": -5})
    assert r["segundos"] >= 1.0
    assert r["mb"] == 0
