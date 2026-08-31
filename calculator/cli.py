"""Консольный режим: REPL и разовый подсчёт из аргументов."""
from __future__ import annotations

from .engine import CalcError, Calculator

HELP = """Команды:
  help            эта справка
  deg / rad       режим углов (сейчас: {mode})
  vars            список переменных
  hist            история вычислений
  clear           сбросить переменные, память и историю
  exit / quit     выход

Примеры: 2+2*2 · 200+10% · sin(30) · √9+1 · x = 5 · 2x^2 · 0xff & 0x0f · ans/3
"""


def evaluate_once(expression: str, calc: Calculator | None = None) -> int:
    """Считает одно выражение и печатает результат. Возвращает код возврата."""
    calc = calc or Calculator()
    try:
        print(calc.evaluate(expression).text)
    except CalcError as error:
        print(f"ошибка: {error.message}")
        return 1
    return 0


def repl(calc: Calculator | None = None) -> int:
    calc = calc or Calculator()
    print("Калькулятор. help — справка, exit — выход.")
    while True:
        try:
            line = input(f"[{calc.angle_mode}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        command = line.lower()
        if command in ("exit", "quit", "q"):
            return 0
        if command == "help":
            print(HELP.format(mode=calc.angle_mode))
            continue
        if command in ("deg", "rad"):
            calc.angle_mode = command
            print(f"режим углов: {command}")
            continue
        if command == "vars":
            for name, value in sorted(calc.variables.items()):
                print(f"  {name} = {calc.format(value)}")
            continue
        if command == "hist":
            for item in calc.history:
                print(f"  {item.expression} = {item.text}")
            continue
        if command == "clear":
            calc.reset()
            print("сброшено")
            continue
        try:
            result = calc.evaluate(line)
        except CalcError as error:
            print(f"  ошибка: {error.message}")
            continue
        prefix = f"{result.assigned} = " if result.assigned else "= "
        bases = calc.format_bases(result.value)
        print(f"  {prefix}{result.text}" + (f"    ({bases})" if bases else ""))
