"""Exact arithmetic path (HARN spec 12.4): the reliable fallback AND verifier.

Two independent evaluators:
  * 'fraction' - exact rational arithmetic (primary)
  * 'decimal'  - 60-digit Decimal arithmetic (independent cross-check for + - * / % ** sqrt)
Expressions are parsed with `ast` and walked with a whitelist. `eval` is never used.
"""
from __future__ import annotations

import ast
import math
import operator
from decimal import Decimal, localcontext
from fractions import Fraction
from math import isqrt

MAX_RESULT_BITS = 200_000
# Python refuses str(int) above ~4300 digits (a DoS guard). We never change that global limit; very large
# exact results are reported in scientific notation instead of being printed in full.
MAX_PRINT_DIGITS = 4000


class ArithmeticError_(ArithmeticError):
    pass


def _check_size(v):
    """Reject exact results that would grow without bound (long chains of multiplications)."""
    if isinstance(v, Fraction) and max(v.numerator.bit_length(), v.denominator.bit_length()) > MAX_RESULT_BITS:
        raise ArithmeticError_("result too large")
    return v


def _mul(a, b):
    return _check_size(a * b)


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: _mul}
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
            if b == 0:
                raise ArithmeticError_("modulo by zero")
            if backend == "fraction":
                return a - b * (a // b)                  # floor modulo, sign follows the divisor
            # Decimal `%` truncates (sign follows the dividend); adjust to floor modulo so the
            # independent backend checks the same operation the exact backend computes.
            r = a % b
            if r != 0 and (r < 0) != (b < 0):
                r += b
            return r
        if op is ast.Pow:
            if backend == "fraction":
                if b.denominator != 1:
                    raise ArithmeticError_("only integer exponents are supported")
                e = int(b)
            else:
                if b != b.to_integral_value():
                    raise ArithmeticError_("only integer exponents are supported")
                e = int(b)
            if e == 0:
                return ctor(1)                           # includes 0 ** 0, consistent across backends
            if a == 0 and e < 0:
                raise ArithmeticError_("zero to a negative power")
            scale = max(a.numerator.bit_length(), a.denominator.bit_length()) if backend == "fraction" else 0
            if backend == "fraction" and a not in (0, 1, -1) and abs(e) * scale > MAX_RESULT_BITS:
                raise ArithmeticError_("result too large")
            return _check_size(a ** e) if backend == "fraction" else a ** e
        raise ArithmeticError_("unsupported operator")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1:
        x = _eval(node.args[0], backend)
        if backend == "fraction":
            return _frac_sqrt(x)
        return x.sqrt()                                  # context-precision square root (x >= 0)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
        return _CMP[type(node.ops[0])](_eval(node.left, backend), _eval(node.comparators[0], backend))
    raise ArithmeticError_(f"unsupported syntax: {type(node).__name__}")


def _parse(expr: str) -> ast.Expression:
    try:
        return ast.parse(expr.replace("^", "**").strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:   # ValueError: NUL bytes / oversized literals
        raise ArithmeticError_(f"cannot parse: {expr[:60]!r}") from e


def _format_int(n: int) -> str:
    """str(n), or scientific notation when n has too many digits to print safely."""
    digits = len(str(abs(n))) if abs(n).bit_length() < 13_000 else int(math.log10(abs(n))) + 1
    if digits <= MAX_PRINT_DIGITS:
        return str(n)
    exp = int(math.log10(abs(n)))                       # math.log10 accepts arbitrarily large ints
    mantissa = 10 ** (math.log10(abs(n)) - exp)
    sign = "-" if n < 0 else ""
    return f"{sign}{mantissa:.12f}e+{exp} (about {digits} digits; too large to print in full)"


def format_value(v) -> str:
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return _format_int(v.numerator)
        if max(v.numerator.bit_length(), v.denominator.bit_length()) > 12_000:
            return f"{_format_int(v.numerator)} / {_format_int(v.denominator)}"
        with localcontext() as ctx:                      # never mutate the process-wide decimal context
            ctx.prec = 30
            return f"{Decimal(v.numerator) / Decimal(v.denominator):.15g} (= {v.numerator}/{v.denominator})"
    return str(v)


def evaluate(expr: str) -> Fraction | bool:
    """Exact evaluation. Raises ArithmeticError for invalid / unsafe / non-exact expressions."""
    try:
        return _eval(_parse(expr), "fraction")
    except _Irrational as e:
        raise ArithmeticError_(f"sqrt({e.x}) is irrational; exact path only returns exact values") from None
    except (RecursionError, MemoryError, OverflowError, ValueError) as e:
        raise ArithmeticError_(f"expression too complex or too large: {type(e).__name__}") from e


def verify(expr: str, value) -> tuple[bool | None, str]:
    """Independent cross-check. Returns (True/False, note) or (None, reason) if no independent check exists."""
    if isinstance(value, bool):
        return None, "no independent verifier for comparisons"
    with localcontext() as ctx:
        ctx.prec = 60
        try:
            other = _eval(_parse(expr), "decimal")
            exact = Decimal(value.numerator) / Decimal(value.denominator)
            tol = max(Decimal(10) ** -40, abs(exact) * Decimal(10) ** -40)
            ok = abs(exact - other) <= tol
        except NotImplementedError:
            return None, "no independent verifier for this operation"
        except Exception as e:  # noqa: BLE001 - a failing cross-check must never crash the answer path
            return None, f"decimal check failed: {type(e).__name__}"
    return ok, "decimal(60) cross-check " + ("agrees" if ok else "DISAGREES")
