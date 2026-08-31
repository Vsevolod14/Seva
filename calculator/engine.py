"""Ядро калькулятора: нормализация, токенайзер, парсер и вычислитель.

Никакого ``eval()``: выражение разбирается рекурсивным спуском, поэтому
через строку ввода нельзя выполнить произвольный код.
"""
from __future__ import annotations

import math
import random
import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable


class CalcError(Exception):
    """Ошибка разбора или вычисления выражения (сообщение для пользователя)."""

    def __init__(self, message: str, pos: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.pos = pos


class Percent:
    """Число с постфиксным ``%``: само по себе ``10%`` равно 0.1."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def as_number(self) -> Any:
        return self.value / 100

    def __repr__(self) -> str:  # pragma: no cover - отладочное
        return f"Percent({self.value!r})"


def _num(value: Any) -> Any:
    """Разворачивает Percent в обычное число."""
    return value.as_number() if isinstance(value, Percent) else value


# --------------------------------------------------------------------------
# Нормализация и токенайзер
# --------------------------------------------------------------------------

_REPLACEMENTS = {
    "×": "*", "·": "*", "∙": "*", "✕": "*",
    "÷": "/", "∕": "/",
    "−": "-", "–": "-", "—": "-",
    "π": "pi", "τ": "tau", "φ": "phi",
    "√": "sqrt ", "∛": "cbrt ",
    "²": "^2", "³": "^3", "⁴": "^4",
    "∞": "inf",
    " ": " ", " ": " ",
    "‘": "", "’": "",
}

_TOKEN_RE = re.compile(
    r"(?P<number>0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+"
    r"|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?)"
    r"|(?P<name>[A-Za-z_Ѐ-ӿ][\wЀ-ӿ]*)"
    r"|(?P<op>\*\*|//|<<|>>|[-+*/%^!&|(),=])"
)

Token = tuple[str, Any, int]


def normalize(text: str) -> str:
    """Приводит «человеческую» запись (×, ÷, π, √, ²) к машинной."""
    for src, dst in _REPLACEMENTS.items():
        if src in text:
            text = text.replace(src, dst)
    return text


def _parse_number(raw: str) -> int | float:
    text = raw.replace("_", "")
    low = text.lower()
    if low.startswith(("0x", "0b", "0o")):
        return int(text, 0)
    if "." in text or "e" in low:
        return float(text)
    return int(text)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    length = len(text)
    while pos < length:
        if text[pos].isspace():
            pos += 1
            continue
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise CalcError(f"непонятный символ {text[pos]!r}", pos)
        kind = match.lastgroup or "op"
        value = match.group()
        if kind == "number":
            tokens.append(("num", _parse_number(value), pos))
        elif kind == "name":
            tokens.append(("name", value, pos))
        else:
            tokens.append(("op", value, pos))
        pos = match.end()
    tokens.append(("end", None, length))
    return tokens


def _starts_operand(token: Token) -> bool:
    """Может ли токен начинать операнд (для неявного умножения ``2pi``)."""
    return token[0] in ("num", "name") or (token[0] == "op" and token[1] == "(")


# --------------------------------------------------------------------------
# Результат вычисления
# --------------------------------------------------------------------------

@dataclass
class Result:
    value: Any
    text: str
    expression: str
    assigned: str | None = None


# --------------------------------------------------------------------------
# Калькулятор
# --------------------------------------------------------------------------

class Calculator:
    """Состояние калькулятора: режим углов, переменные, память, история."""

    ANGLE_MODES = ("deg", "rad")
    MAX_FACTORIAL = 10_000
    MAX_POWER = 100_000

    def __init__(self, angle_mode: str = "deg", precision: int = 12) -> None:
        if angle_mode not in self.ANGLE_MODES:
            raise ValueError(f"unknown angle mode: {angle_mode}")
        self.angle_mode = angle_mode
        self.precision = precision
        self.memory: Any = 0
        self.history: list[Result] = []
        self.constants: dict[str, Any] = {
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "phi": (1 + 5 ** 0.5) / 2,
            "inf": math.inf,
            "nan": math.nan,
        }
        self.variables: dict[str, Any] = {"ans": 0}
        self.functions: dict[str, Callable[..., Any]] = self._build_functions()

    # -- состояние ---------------------------------------------------------

    def reset(self) -> None:
        """Сбрасывает переменные, память и историю (режим углов сохраняется)."""
        self.variables = {"ans": 0}
        self.memory = 0
        self.history.clear()

    def toggle_angle_mode(self) -> str:
        self.angle_mode = "rad" if self.angle_mode == "deg" else "deg"
        return self.angle_mode

    # -- углы --------------------------------------------------------------

    def _to_rad(self, x: Any) -> float:
        return math.radians(x) if self.angle_mode == "deg" else float(x)

    def _from_rad(self, x: float) -> float:
        return math.degrees(x) if self.angle_mode == "deg" else x

    def _sin(self, x: Any) -> float:
        if self.angle_mode == "deg":
            rest = x % 360
            if rest % 90 == 0:  # точные значения вместо 1.2e-16
                return (0.0, 1.0, 0.0, -1.0)[int(rest // 90) % 4]
        return math.sin(self._to_rad(x))

    def _cos(self, x: Any) -> float:
        if self.angle_mode == "deg":
            rest = x % 360
            if rest % 90 == 0:
                return (1.0, 0.0, -1.0, 0.0)[int(rest // 90) % 4]
        return math.cos(self._to_rad(x))

    def _tan(self, x: Any) -> float:
        if self.angle_mode == "deg":
            rest = x % 180
            if rest == 90:
                raise CalcError("тангенс не определён при 90°")
            if rest == 0:
                return 0.0
        return math.tan(self._to_rad(x))

    # -- функции -----------------------------------------------------------

    def _build_functions(self) -> dict[str, Callable[..., Any]]:
        def log(x: Any, base: Any = None) -> float:
            return math.log(x) if base is None else math.log(x, base)

        def cbrt(x: Any) -> float:
            return math.copysign(abs(x) ** (1 / 3), x)

        def root(x: Any, n: Any) -> float:
            if x < 0:
                if n % 2 == 0:
                    raise CalcError("корень чётной степени из отрицательного числа")
                return -((-x) ** (1 / n))
            return x ** (1 / n)

        def factorial(x: Any) -> Any:
            if isinstance(x, float) and not x.is_integer():
                if x <= -1:
                    raise CalcError("факториал не определён для этого числа")
                return math.gamma(x + 1)
            n = int(x)
            if n < 0:
                raise CalcError("факториал отрицательного числа")
            if n > self.MAX_FACTORIAL:
                raise CalcError(f"факториал больше {self.MAX_FACTORIAL}! не считаю")
            return math.factorial(n)

        def as_ints(name: str, args: tuple[Any, ...]) -> list[int]:
            out = []
            for arg in args:
                if isinstance(arg, float) and not arg.is_integer():
                    raise CalcError(f"{name}: нужны целые числа")
                out.append(int(arg))
            return out

        def rand(*args: Any) -> float:
            if not args:
                return random.random()
            if len(args) == 2:
                return random.uniform(args[0], args[1])
            raise CalcError("rand() или rand(a, b)")

        return {
            "sin": self._sin, "cos": self._cos, "tan": self._tan,
            "asin": lambda x: self._from_rad(math.asin(x)),
            "acos": lambda x: self._from_rad(math.acos(x)),
            "atan": lambda x: self._from_rad(math.atan(x)),
            "atan2": lambda y, x: self._from_rad(math.atan2(y, x)),
            "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
            "asinh": math.asinh, "acosh": math.acosh, "atanh": math.atanh,
            "sqrt": math.sqrt, "cbrt": cbrt, "root": root,
            "exp": math.exp, "ln": math.log, "log": log,
            "log2": math.log2, "log10": math.log10, "log1p": math.log1p,
            "abs": abs, "sign": lambda x: (x > 0) - (x < 0),
            "round": lambda x, n=0: round(x, int(n)),
            "floor": lambda x: math.floor(x), "ceil": lambda x: math.ceil(x),
            "trunc": lambda x: math.trunc(x), "frac": lambda x: x - math.trunc(x),
            "fact": factorial, "factorial": factorial,
            "gcd": lambda *a: math.gcd(*as_ints("gcd", a)),
            "lcm": lambda *a: math.lcm(*as_ints("lcm", a)),
            "comb": lambda n, k: math.comb(*as_ints("comb", (n, k))),
            "perm": lambda n, k: math.perm(*as_ints("perm", (n, k))),
            "hypot": lambda *a: math.hypot(*a),
            "deg": math.degrees, "degrees": math.degrees,
            "rad": math.radians, "radians": math.radians,
            "mod": lambda a, b: a % b, "pow": lambda a, b: a ** b,
            "min": lambda *a: min(a), "max": lambda *a: max(a),
            "sum": lambda *a: sum(a),
            "avg": lambda *a: statistics.fmean(a), "mean": lambda *a: statistics.fmean(a),
            "median": lambda *a: statistics.median(a),
            "rand": rand, "random": rand,
            "randint": lambda a, b: random.randint(int(a), int(b)),
        }

    # -- вычисление --------------------------------------------------------

    def evaluate(self, text: str, commit: bool = True) -> Result:
        """Вычисляет выражение.

        ``commit=False`` — режим предпросмотра: переменные, ``ans`` и история
        не меняются (используется для подсказки прямо во время набора).
        """
        expression = text.strip()
        if not expression:
            raise CalcError("пустое выражение")
        tokens = tokenize(normalize(expression))
        scope = self.variables if commit else dict(self.variables)
        name, value = _Parser(self, tokens, scope).parse_statement()
        value = self._check_value(_num(value))
        result = Result(value=value, text=self.format(value),
                        expression=expression, assigned=name)
        if commit:
            if name is not None:
                scope[name] = value
            scope["ans"] = value
            self.history.append(result)
        return result

    def _check_value(self, value: Any) -> Any:
        if isinstance(value, complex):
            raise CalcError("результат — комплексное число")
        if isinstance(value, bool):
            return int(value)
        if not isinstance(value, (int, float)):
            raise CalcError("непонятный результат")
        return value

    # -- форматирование ----------------------------------------------------

    def format(self, value: Any, group: bool = False) -> str:
        """Человекочитаемая запись числа."""
        value = _num(value)
        if isinstance(value, float):
            if math.isnan(value):
                return "не число"
            if math.isinf(value):
                return "∞" if value > 0 else "-∞"
            if value == int(value) and abs(value) < 1e16:
                value = int(value)
        if isinstance(value, int):
            return f"{value:,}".replace(",", " ") if group else str(value)
        text = f"{value:.{self.precision}g}"
        if "e" in text:  # 1e-05 -> 1e-5, 1.5e+20 -> 1.5e20
            mantissa, exponent = text.split("e")
            text = f"{mantissa}e{int(exponent)}"
        return "0" if text in ("-0", "0") else text

    def format_bases(self, value: Any) -> str | None:
        """Строка с HEX/BIN/OCT для целого результата разумного размера."""
        value = _num(value)
        if isinstance(value, float) and value.is_integer() and abs(value) < 1e16:
            value = int(value)
        if not isinstance(value, int) or abs(value) >= 2 ** 64:
            return None
        sign = "-" if value < 0 else ""
        v = abs(value)
        return f"HEX {sign}{v:X}   OCT {sign}{v:o}   BIN {sign}{v:b}"


# --------------------------------------------------------------------------
# Парсер (рекурсивный спуск)
# --------------------------------------------------------------------------

class _Parser:
    """Разбирает и одновременно вычисляет выражение.

    Приоритеты, от низшего к высшему::

        |  ->  &  ->  << >>  ->  + -  ->  * / // %  ->  унарный +/-
           ->  ^ (правоассоциативный)  ->  постфиксные ! и %  ->  атом
    """

    def __init__(self, calc: Calculator, tokens: list[Token], scope: dict[str, Any]) -> None:
        self.calc = calc
        self.tokens = tokens
        self.scope = scope
        self.i = 0

    # -- служебное ---------------------------------------------------------

    def peek(self, offset: int = 0) -> Token:
        index = min(self.i + offset, len(self.tokens) - 1)
        return self.tokens[index]

    def next(self) -> Token:
        token = self.tokens[self.i]
        if token[0] != "end":
            self.i += 1
        return token

    def accept(self, *ops: str) -> str | None:
        kind, value, _ = self.peek()
        if kind == "op" and value in ops:
            self.i += 1
            return value
        return None

    def expect(self, op: str) -> None:
        if self.accept(op) is None:
            kind, value, pos = self.peek()
            found = "конец выражения" if kind == "end" else repr(value)
            raise CalcError(f"ожидалось {op!r}, а тут {found}", pos)

    # -- разбор ------------------------------------------------------------

    def parse_statement(self) -> tuple[str | None, Any]:
        name = None
        first, second = self.peek(), self.peek(1)
        if first[0] == "name" and second[0] == "op" and second[1] == "=":
            name = first[1]
            if name in self.calc.functions or name in self.calc.constants:
                raise CalcError(f"имя {name!r} занято", first[2])
            self.i += 2
        value = self.parse_expr()
        kind, token_value, pos = self.peek()
        if kind != "end":
            raise CalcError(f"лишнее в конце: {token_value!r}", pos)
        return name, value

    def parse_expr(self) -> Any:
        left = self.parse_bitand()
        while self.accept("|") is not None:
            left = self._bitwise("|", left, self.parse_bitand())
        return left

    def parse_bitand(self) -> Any:
        left = self.parse_shift()
        while self.accept("&") is not None:
            left = self._bitwise("&", left, self.parse_shift())
        return left

    def parse_shift(self) -> Any:
        left = self.parse_additive()
        while (op := self.accept("<<", ">>")) is not None:
            left = self._bitwise(op, left, self.parse_additive())
        return left

    def parse_additive(self) -> Any:
        left = self.parse_multiplicative()
        while (op := self.accept("+", "-")) is not None:
            right = self.parse_multiplicative()
            if isinstance(right, Percent):
                # 200 + 10%  ->  200 + 200*0.1 = 220 (как в обычных калькуляторах)
                base = _num(left)
                delta = base * right.value / 100
                left = base + delta if op == "+" else base - delta
            else:
                left = _num(left) + right if op == "+" else _num(left) - right
        return left

    def parse_multiplicative(self) -> Any:
        left = self.parse_unary()
        while True:
            op = self.accept("*", "/", "//", "%")
            if op is None:
                # неявное умножение: 2pi, 3(4+5), 2x
                if _starts_operand(self.peek()):
                    left = _num(left) * _num(self.parse_unary())
                    continue
                return left
            right = _num(self.parse_unary())
            left = _num(left)
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    raise CalcError("деление на ноль")
                left = left / right
            elif op == "//":
                if right == 0:
                    raise CalcError("деление на ноль")
                left = left // right
            else:
                if right == 0:
                    raise CalcError("остаток от деления на ноль")
                left = left % right

    def parse_unary(self) -> Any:
        op = self.accept("+", "-")
        if op is None:
            return self.parse_power()
        value = _num(self.parse_unary())
        return -value if op == "-" else value

    def parse_power(self) -> Any:
        base = self.parse_postfix()
        if self.accept("^", "**") is None:
            return base
        exponent = _num(self.parse_unary())  # правая ассоциативность: 2^3^2 = 512
        return self._power(_num(base), exponent)

    def parse_postfix(self) -> Any:
        value = self.parse_atom()
        while True:
            kind, token_value, _ = self.peek()
            if kind != "op":
                return value
            if token_value == "!":
                self.i += 1
                value = self.calc.functions["fact"](_num(value))
            elif token_value == "%" and not _starts_operand(self.peek(1)):
                self.i += 1  # постфиксный процент, а не остаток от деления
                value = Percent(_num(value))
            else:
                return value

    def parse_atom(self) -> Any:
        kind, value, pos = self.next()
        if kind == "num":
            return value
        if kind == "op" and value == "(":
            inner = self.parse_expr()
            self.expect(")")
            return inner
        if kind == "name":
            return self.parse_name(value, pos)
        if kind == "end":
            raise CalcError("выражение оборвалось", pos)
        raise CalcError(f"здесь не ждали {value!r}", pos)

    def parse_name(self, name: str, pos: int) -> Any:
        if name in self.calc.functions:
            func = self.calc.functions[name]
            if self.accept("(") is not None:
                args = []
                kind, value, _ = self.peek()
                if not (kind == "op" and value == ")"):
                    args.append(_num(self.parse_expr()))
                    while self.accept(",") is not None:
                        args.append(_num(self.parse_expr()))
                self.expect(")")
            else:
                # запись без скобок: sqrt 9, sin 30
                args = [_num(self.parse_unary())]
            return self._call(name, func, args, pos)
        if name in self.scope:
            return self.scope[name]
        if name in self.calc.constants:
            return self.calc.constants[name]
        raise CalcError(f"неизвестное имя: {name}", pos)

    # -- операции ----------------------------------------------------------

    def _call(self, name: str, func: Callable[..., Any], args: list[Any], pos: int) -> Any:
        try:
            return func(*args)
        except CalcError:
            raise
        except TypeError as exc:
            raise CalcError(f"{name}: не те аргументы", pos) from exc
        except ValueError as exc:
            raise CalcError(f"{name}: недопустимый аргумент", pos) from exc
        except ZeroDivisionError as exc:
            raise CalcError("деление на ноль", pos) from exc
        except OverflowError as exc:
            raise CalcError("слишком большое число", pos) from exc

    def _power(self, base: Any, exponent: Any) -> Any:
        if isinstance(base, int) and isinstance(exponent, int) and exponent > 0:
            if abs(base) > 1 and exponent > self.calc.MAX_POWER:
                raise CalcError("слишком большая степень")
        try:
            value = base ** exponent
        except ZeroDivisionError as exc:
            raise CalcError("деление на ноль") from exc
        except OverflowError as exc:
            raise CalcError("слишком большое число") from exc
        if isinstance(value, complex):
            raise CalcError("корень чётной степени из отрицательного числа")
        return value

    def _bitwise(self, op: str, left: Any, right: Any) -> int:
        values = []
        for item in (_num(left), _num(right)):
            if isinstance(item, float):
                if not item.is_integer():
                    raise CalcError(f"{op}: нужны целые числа")
                item = int(item)
            values.append(item)
        a, b = values
        if op in ("<<", ">>"):
            if b < 0:
                raise CalcError("отрицательный сдвиг")
            if b > 4096:
                raise CalcError("слишком большой сдвиг")
            return a << b if op == "<<" else a >> b
        return a & b if op == "&" else a | b
