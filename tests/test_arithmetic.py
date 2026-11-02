import pytest

from skills.arithmetic import exact
from skills.arithmetic.parser import extract_expression, is_pure_arithmetic


@pytest.mark.parametrize("expr,expected", [
    ("12*7", "84"), ("1000-387", "613"), ("2^10", "1024"), ("17 % 5", "2"), ("-7 % 3", "2"),
    ("sqrt(144)", "12"), ("(1+2)*(3+4)", "21"), ("1/4", "0.25 (= 1/4)"), ("5 > 3", "True"),
])
def test_exact_values(expr, expected):
    assert exact.format_value(exact.evaluate(expr)) == expected


@pytest.mark.parametrize("bad", ["1/0", "5 % 0", "0 ** -1", "2 ** 100000000", "__import__('os')", "sqrt(2)", "sqrt(-4)",
                                 "open('x')", "1 +", "2 ** 0.5"])
def test_rejects_bad_or_unsafe(bad):
    with pytest.raises(ArithmeticError):
        exact.evaluate(bad)


def test_exact_has_no_float_error():
    assert exact.evaluate("0.1 + 0.2") == exact.evaluate("0.3")


def test_independent_verifier_agrees_and_catches_wrong():
    from fractions import Fraction
    v = exact.evaluate("123456789 * 987654321")
    assert exact.verify("123456789 * 987654321", v)[0] is True
    assert exact.verify("123456789 * 987654321", v + 1)[0] is False
    assert exact.verify("2 ** 10", exact.evaluate("2 ** 10"))[0] is None   # honest: no independent check


def test_parser_words_and_purity():
    assert extract_expression("what is 12 times 7?") == "12  *  7"
    assert is_pure_arithmetic("What is 12*7?")
    assert is_pure_arithmetic("calculate 5 plus 3")
    assert not is_pure_arithmetic("I have 3 apples and bought 4 more, explain how many apples I own")
    assert extract_expression("hello there") is None
