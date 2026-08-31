"""Тесты ядра калькулятора."""
import math

import pytest

from calculator.engine import CalcError, Calculator


@pytest.fixture()
def calc() -> Calculator:
    return Calculator(angle_mode="deg")


def value(calc: Calculator, expression: str):
    return calc.evaluate(expression).value


def text(calc: Calculator, expression: str) -> str:
    return calc.evaluate(expression).text


class TestArithmetic:
    @pytest.mark.parametrize(("expression", "expected"), [
        ("2+2", 4),
        ("2+2*2", 6),
        ("(2+2)*2", 8),
        ("10-4-3", 3),
        ("10/4", 2.5),
        ("7//2", 3),
        ("7%3", 1),
        ("-3", -3),
        ("--3", 3),
        ("-2^2", -4),
        ("(-2)^2", 4),
        ("2^3^2", 512),
        ("2**10", 1024),
        ("1_000+1", 1001),
        (".5+.5", 1.0),
        ("1e3", 1000.0),
    ])
    def test_basic(self, calc, expression, expected):
        assert value(calc, expression) == expected

    def test_int_stays_exact(self, calc):
        assert value(calc, "2^100") == 2 ** 100

    def test_division_by_zero(self, calc):
        with pytest.raises(CalcError, match="деление на ноль"):
            calc.evaluate("1/0")


class TestSyntaxSugar:
    @pytest.mark.parametrize(("expression", "expected"), [
        ("2pi", 2 * math.pi),
        ("3(4+5)", 27),
        ("(1+1)(2+2)", 8),
        ("2×3", 6),
        ("10÷4", 2.5),
        ("√9", 3),
        ("√9+1", 4),
        ("5²", 25),
        ("sqrt 16", 4),
        ("2 + 3!", 8),
        ("5!", 120),
        ("0xff", 255),
        ("0b1010", 10),
        ("0o17", 15),
    ])
    def test_sugar(self, calc, expression, expected):
        assert value(calc, expression) == pytest.approx(expected)

    def test_implicit_multiplication_with_variable(self, calc):
        calc.evaluate("x = 4")
        assert value(calc, "2x") == 8


class TestPercent:
    @pytest.mark.parametrize(("expression", "expected"), [
        ("10%", 0.1),
        ("200+10%", 220),
        ("200-10%", 180),
        ("100*10%", 10),
        ("100/10%", 1000),
        ("10%3", 1),          # тут % — остаток от деления
        ("10 % 3", 1),
        ("50+10%+10", 65),
    ])
    def test_percent(self, calc, expression, expected):
        assert value(calc, expression) == pytest.approx(expected)


class TestFunctions:
    def test_trig_degrees_exact(self, calc):
        assert value(calc, "sin(180)") == 0
        assert value(calc, "cos(90)") == 0
        assert value(calc, "sin(30)") == pytest.approx(0.5)

    def test_trig_radians(self, calc):
        calc.toggle_angle_mode()
        assert calc.angle_mode == "rad"
        assert value(calc, "sin(pi/2)") == pytest.approx(1)

    def test_inverse_trig_follows_mode(self, calc):
        assert value(calc, "asin(1)") == pytest.approx(90)
        calc.toggle_angle_mode()
        assert value(calc, "asin(1)") == pytest.approx(math.pi / 2)

    def test_tan_90_is_an_error(self, calc):
        with pytest.raises(CalcError, match="тангенс"):
            calc.evaluate("tan(90)")

    @pytest.mark.parametrize(("expression", "expected"), [
        ("log(8, 2)", 3),
        ("ln(e)", 1),
        ("log10(1000)", 3),
        ("cbrt(-27)", -3),
        ("root(32, 5)", 2),
        ("gcd(12, 18)", 6),
        ("lcm(4, 6)", 12),
        ("comb(5, 2)", 10),
        ("hypot(3, 4)", 5),
        ("max(1, 7, 3)", 7),
        ("avg(1, 2, 3, 4)", 2.5),
        ("median(1, 3, 10)", 3),
        ("round(2.567, 2)", 2.57),
        ("fact(0)", 1),
        ("abs(-5)", 5),
        ("sign(-9)", -1),
    ])
    def test_library(self, calc, expression, expected):
        assert value(calc, expression) == pytest.approx(expected)

    def test_gamma_for_non_integer_factorial(self, calc):
        assert value(calc, "fact(0.5)") == pytest.approx(math.sqrt(math.pi) / 2)

    def test_huge_factorial_is_rejected(self, calc):
        with pytest.raises(CalcError, match="факториал"):
            calc.evaluate("fact(50000)")

    def test_even_root_of_negative(self, calc):
        with pytest.raises(CalcError, match="корень"):
            calc.evaluate("(-8)^0.5")


class TestBitwise:
    @pytest.mark.parametrize(("expression", "expected"), [
        ("6 & 3", 2),
        ("6 | 3", 7),
        ("1 << 10", 1024),
        ("1024 >> 3", 128),
        ("0xf0 | 0x0f", 255),
    ])
    def test_bitwise(self, calc, expression, expected):
        assert value(calc, expression) == expected

    def test_bitwise_needs_integers(self, calc):
        with pytest.raises(CalcError, match="целые"):
            calc.evaluate("1.5 & 3")


class TestStateAndVariables:
    def test_assignment_and_use(self, calc):
        result = calc.evaluate("radius = 3")
        assert result.assigned == "radius"
        assert value(calc, "pi*radius^2") == pytest.approx(math.pi * 9)

    def test_ans(self, calc):
        calc.evaluate("2+2")
        assert value(calc, "ans*10") == 40

    def test_preview_does_not_touch_state(self, calc):
        calc.evaluate("2+2")
        calc.evaluate("x = 99", commit=False)
        assert "x" not in calc.variables
        assert calc.variables["ans"] == 4
        assert len(calc.history) == 1

    def test_history_grows(self, calc):
        calc.evaluate("1+1")
        calc.evaluate("2+2")
        assert [item.text for item in calc.history] == ["2", "4"]

    def test_reset(self, calc):
        calc.evaluate("x = 1")
        calc.reset()
        assert calc.variables == {"ans": 0}
        assert calc.history == []

    def test_cannot_shadow_a_function(self, calc):
        with pytest.raises(CalcError, match="занято"):
            calc.evaluate("sin = 1")


class TestErrors:
    @pytest.mark.parametrize("expression", [
        "", "  ", "2+", "(2+2", "2+2)", "2 $ 2", "foo(1)", "unknown_name", "*5",
    ])
    def test_bad_input(self, calc, expression):
        with pytest.raises(CalcError):
            calc.evaluate(expression)

    def test_error_message_is_readable(self, calc):
        with pytest.raises(CalcError) as info:
            calc.evaluate("2 $ 2")
        assert "$" in info.value.message


class TestFormatting:
    @pytest.mark.parametrize(("expression", "expected"), [
        ("1/3", "0.333333333333"),
        ("0.1+0.2", "0.3"),
        ("6/3", "2"),
        ("2^100", "1267650600228229401496703205376"),
        ("1/0.0000000001", "10000000000"),
        ("1e-20", "1e-20"),
        ("-0.0", "0"),
    ])
    def test_format(self, calc, expression, expected):
        assert text(calc, expression) == expected

    def test_grouping(self, calc):
        assert calc.format(1234567, group=True) == "1 234 567"

    def test_bases(self, calc):
        assert calc.format_bases(255) == "HEX FF   OCT 377   BIN 11111111"
        assert calc.format_bases(1.5) is None
