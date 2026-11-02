"""Exact arithmetic path (HARN spec 12.4): the reliable fallback AND verifier.

Two independent evaluators:
  * 'fraction' - exact rational arithmetic (primary)
  * 'decimal'  - 60-digit Decimal arithmetic (independent cross-check for + - * /)
Expressions are parsed with `ast` and walked with a whitelist. `eval` is never used.
"""
from __future__ import annotations

import ast
import operator
from decimal import Decimal, getcontext
from fractions import Fraction
from math import isqrt

MAX_RESULT_BITS = 200_000


class ArithmeticError_(ArithmeticError):
    pass


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.Eq: operator.eq, ast.NotEq: operator.ne}


def _frac_sqrt(x: Fraction) -> Fraction:
    if x < 0:
        raise ArithmeticError_("square root of a negative number")
    n, d = x.numerator, x.denominator
    rn, rd = isqrt(n), isqrt(d)
    if rn * rn == n and rd * rd == d:
        return Fraction(rn, rd)
    raise _Irrational(x)


class _Irrational(Exception):
    def __init__(self, x):
        self.x = x


def _eval(node, backend: str):
    ctor = Fraction if backend == "fraction" else Decimal
    if isinstance(node, ast.Expression):
        return _eval(node.body, backend)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return ctor(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, backend)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, backend), _eval(node.right, backend)
        op = type(node.op)
        if op in _BIN:
            return _BIN[op](a, b)
        if op is ast.Div:
            if b == 0:
                raise ArithmeticError_("division by zero")
            return a / b
        if op is ast.Mod:
            if backend != "fraction":
                raise NotImplementedError
            if b == 0:
                raise ArithmeticError_("modulo by zero")
            return a - b * (a // b)
        if op is ast.Pow:
            if backend != "fraction":
                raise NotImplementedError
            if b.denominator != 1:
                raise ArithmeticError_("only integer exponents are supported")
            e = int(b)
            if a == 0 and e < 0:
                raise ArithmeticError_("zero to a negative power")
            if a not in (0, 1, -1) and abs(e) * max(a.numerator.bit_length(), a.denominator.bit_length()) > MAX_RESULT_BITS:
                raise ArithmeticError_("result too large")
            return a ** e
        raise ArithmeticError_("unsupported operator")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1:
        if backend != "fraction":
            raise NotImplementedError
        return _frac_sqrt(_eval(node.args[0], backend))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
        return _CMP[type(node.ops[0])](_eval(node.left, backend), _eval(node.comparators[0], backend))
    raise ArithmeticError_(f"unsupported syntax: {type(node).__name__}")


def _parse(expr: str) -> ast.Expression:
    try:
        return ast.parse(expr.replace("^", "**").strip(), mode="eval")
    except SyntaxError as e:
        raise ArithmeticError_(f"cannot parse: {expr!r}") from e


def format_value(v) -> str:
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return str(v.numerator)
        getcontext().prec = 30
        return f"{Decimal(v.numerator) / Decimal(v.denominator):.15g} (= {v.numerator}/{v.denominator})"
    return str(v)


def evaluate(expr: str) -> Fraction | bool:
    """Exact evaluation. Raises ArithmeticError for invalid / unsafe / non-exact expressions."""
    try:
        return _eval(_parse(expr), "fraction")
    except _Irrational as e:
        raise ArithmeticError_(f"sqrt({e.x}) is irrational; exact path only returns exact values")


def verify(expr: str, value) -> tuple[bool | None, str]:
    """Independent cross-check. Returns (True/False, note) or (None, reason) if no independent check exists."""
    if isinstance(value, bool):
        return None, "no independent verifier for comparisons"
    getcontext().prec = 60
    try:
        other = _eval(_parse(expr), "decimal")
    except NotImplementedError:
        return None, "no independent verifier for % ** sqrt"
    except Exception as e:  # noqa: BLE001
        return None, f"decimal check failed: {e}"
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    tol = max(Decimal(10) ** -40, abs(exact) * Decimal(10) ** -40)
    ok = abs(exact - other) <= tol
    return ok, "decimal(60) cross-check " + ("agrees" if ok else "DISAGREES")
