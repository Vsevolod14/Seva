"""Запуск калькулятора.

    python main.py            окно (если Tkinter недоступен — консоль)
    python main.py --cli      консольный REPL
    python main.py "2+2*2"    посчитать и выйти
"""
from __future__ import annotations

import sys

from calculator.cli import evaluate_once, repl


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args and args[0] == "--cli":
        return repl()
    if args:
        return evaluate_once(" ".join(args))
    try:
        from calculator.gui import run
    except ImportError:
        print("Tkinter не найден — запускаю консольный режим.\n"
              "Linux: sudo apt install python3-tk\n")
        return repl()
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
