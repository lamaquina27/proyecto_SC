"""
Operaciones que la mensajeria ofrece a la red como tareas distribuidas.

    calcular   una expresion matematica ("(3 + 4) * 2^10", "sqrt(2) * pi")
    estresar   busca primos durante unos segundos, ocupando un nucleo entero
               y, si se pide, reservando memoria; sirve para ver en el
               monitor cuanto le cuesta a cada nodo

La expresion de calcular se interpreta con ast, nunca con eval: solo se
aceptan numeros, + - * / // % ** (o ^), parentesis y las funciones de
FUNCIONES. Asi un nodo no puede mandarle codigo a otro.

estresar corre en un proceso aparte. Dentro de un mismo proceso de Python
dos hilos no usan dos nucleos a la vez (GIL), y lo que se quiere mostrar es
el costo real de la tarea en el equipo que la ejecuta.
"""

import ast
import math
import operator
import os
import signal
import time
from concurrent.futures import ProcessPoolExecutor

MAX_EXPRESION = 200
MAX_EXPONENTE = 10_000
MAX_DIGITOS = 1_000
MAX_BITS = 3_400
MAX_SEGUNDOS = 120
MAX_MB = 1024
PAGINA = 4096

OPERADORES = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
UNARIOS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCIONES = {
    "sqrt": math.sqrt, "raiz": math.sqrt, "abs": abs, "round": round,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp,
    "factorial": math.factorial, "floor": math.floor, "ceil": math.ceil,
    "max": max, "min": min,
}
CONSTANTES = {"pi": math.pi, "e": math.e}


class ExpresionInvalida(ValueError):
    pass


def _valor(nodo):
    if isinstance(nodo, ast.Constant) and type(nodo.value) in (int, float):
        return nodo.value
    if isinstance(nodo, ast.Name) and nodo.id in CONSTANTES:
        return CONSTANTES[nodo.id]
    if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in UNARIOS:
        return UNARIOS[type(nodo.op)](_valor(nodo.operand))
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in OPERADORES:
        izquierda, derecha = _valor(nodo.left), _valor(nodo.right)
        if isinstance(nodo.op, ast.Pow) and (
                abs(derecha) > MAX_EXPONENTE
                or (isinstance(izquierda, int) and isinstance(derecha, int)
                    and izquierda.bit_length() * derecha > MAX_BITS)):
            raise ExpresionInvalida("la potencia es demasiado grande")
        resultado = OPERADORES[type(nodo.op)](izquierda, derecha)
        if isinstance(resultado, int) and resultado.bit_length() > MAX_BITS:
            raise ExpresionInvalida("el resultado tiene demasiados digitos")
        return resultado
    if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
            and nodo.func.id in FUNCIONES and not nodo.keywords):
        argumentos = [_valor(a) for a in nodo.args]
        if nodo.func.id == "factorial" and argumentos and argumentos[0] > 450:
            raise ExpresionInvalida("factorial demasiado grande")
        return FUNCIONES[nodo.func.id](*argumentos)
    raise ExpresionInvalida(f"no se permite {ast.dump(nodo)[:40]}")


def calcular(expresion):
    texto = str(expresion).strip().replace("^", "**")
    if not texto or len(texto) > MAX_EXPRESION:
        raise ExpresionInvalida(
            f"la expresion debe tener entre 1 y {MAX_EXPRESION} caracteres")
    try:
        arbol = ast.parse(texto, mode="eval")
    except SyntaxError:
        raise ExpresionInvalida(f"no entiendo la expresion: {expresion}")
    resultado = _valor(arbol.body)
    if isinstance(resultado, int) and len(str(abs(resultado))) > MAX_DIGITOS:
        raise ExpresionInvalida("el resultado tiene demasiados digitos")
    return resultado


def es_primo(n):
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    divisor = 3
    while divisor * divisor <= n:
        if n % divisor == 0:
            return False
        divisor += 2
    return True


def quemar(segundos, mb=0, desde=10_000_000):
    reservada = bytearray(mb * 1024 * 1024)
    for i in range(0, len(reservada), PAGINA):
        reservada[i] = 1
    inicio = time.monotonic()
    fin = inicio + segundos
    n = desde | 1
    revisados = primos = 0
    mayor = None
    while time.monotonic() < fin:
        for _ in range(200):
            if es_primo(n):
                primos += 1
                mayor = n
            n += 2
            revisados += 1
    return {"revisados": revisados, "primos": primos, "mayor": mayor,
            "mb": mb, "segundos": round(time.monotonic() - inicio, 2),
            "pid": os.getpid()}


def _ignorar_ctrl_c():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


_procesos = None


def _pool():
    global _procesos
    if _procesos is None:
        _procesos = ProcessPoolExecutor(max_workers=os.cpu_count() or 2,
                                        initializer=_ignorar_ctrl_c)
    return _procesos


def estresar(datos):
    datos = datos or {}
    segundos = min(MAX_SEGUNDOS, max(1.0, float(datos.get("segundos", 5))))
    mb = min(MAX_MB, max(0, int(datos.get("mb", 0))))
    desde = max(3, int(datos.get("desde", 10_000_000)))
    try:
        return _pool().submit(quemar, segundos, mb, desde).result()
    except (OSError, RuntimeError):
        return quemar(segundos, mb, desde)
