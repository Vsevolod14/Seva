"""Оконный калькулятор на Tkinter (без внешних зависимостей)."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from .engine import CalcError, Calculator

BG = "#171a21"
PANEL = "#1f232c"
DISPLAY = "#12151b"
FG = "#e9edf5"
MUTED = "#7f8899"
RED = "#ff6b6b"
ACCENT = "#ff9f43"
NUM_BG = "#262b36"
NUM_ACTIVE = "#323847"
FUN_BG = "#1e222b"
FUN_ACTIVE = "#2a3040"
OP_BG = "#3a4152"
OP_ACTIVE = "#485063"

# Клавиатура: (подпись, стиль, действие). Действие с "@" — команда из
# _make_command, остальное вставляется в строку ввода как есть.
KEYPAD: list[list[tuple[str, str, str]]] = [
    [("2nd", "fun", "@second"), ("DEG", "fun", "@angle"), ("MC", "fun", "@mc"),
     ("MR", "fun", "@mr"), ("M+", "fun", "@m+"), ("M−", "fun", "@m-")],
    [("x²", "fun", "^2"), ("xʸ", "fun", "^"), ("(", "fun", "("),
     (")", "fun", ")"), ("C", "fun", "@clear"), ("⌫", "fun", "@back")],
    [("√", "fun", "sqrt()"), ("ln", "fun", "ln()"), ("7", "num", "7"),
     ("8", "num", "8"), ("9", "num", "9"), ("÷", "op", "/")],
    [("n!", "fun", "!"), ("log", "fun", "log()"), ("4", "num", "4"),
     ("5", "num", "5"), ("6", "num", "6"), ("×", "op", "*")],
    [("sin", "fun", "sin()"), ("cos", "fun", "cos()"), ("1", "num", "1"),
     ("2", "num", "2"), ("3", "num", "3"), ("−", "op", "-")],
    [("tan", "fun", "tan()"), ("π", "fun", "pi"), ("ans", "num", "ans"),
     ("0", "num", "0"), (".", "num", "."), ("+", "op", "+")],
    [("1/x", "fun", "@inv"), ("e", "fun", "e"), ("%", "fun", "%"),
     ("±", "fun", "@sign"), ("=", "eq", "@equals")],
]

# Что показывают те же кнопки в режиме 2nd.
SECOND: dict[str, tuple[str, str]] = {
    "x²": ("x³", "^3"),
    "xʸ": ("ʸ√x", "root()"),
    "√": ("∛", "cbrt()"),
    "ln": ("eˣ", "exp()"),
    "log": ("10ˣ", "10^"),
    "n!": ("nCr", "comb()"),
    "sin": ("asin", "asin()"),
    "cos": ("acos", "acos()"),
    "tan": ("atan", "atan()"),
    "π": ("τ", "tau"),
    "1/x": ("|x|", "abs()"),
    "e": ("φ", "phi"),
}

STYLES = {
    "num": (NUM_BG, NUM_ACTIVE, FG),
    "fun": (FUN_BG, FUN_ACTIVE, MUTED),
    "op": (OP_BG, OP_ACTIVE, FG),
    "eq": (ACCENT, "#ffb166", "#20242c"),
}


def _pick_family(root: tk.Misc, *candidates: str) -> str:
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont").cget("family")


class CalculatorApp(tk.Tk):
    """Главное окно."""

    def __init__(self, calc: Calculator | None = None) -> None:
        super().__init__()
        self.calc = calc or Calculator()
        self.second = False
        self.just_evaluated = False
        self.history_visible = True
        self.history_index: int | None = None
        self.buttons: dict[str, tk.Button] = {}

        self.title("Калькулятор")
        self.configure(bg=BG)
        self.minsize(640, 620)
        self.geometry("860x680")

        ui = _pick_family(self, "Segoe UI", "SF Pro Text", "Helvetica Neue",
                          "Noto Sans", "DejaVu Sans", "Arial")
        mono = _pick_family(self, "JetBrains Mono", "Cascadia Mono", "Menlo",
                            "Consolas", "DejaVu Sans Mono", "Courier New")
        self.f_input = tkfont.Font(family=mono, size=18)
        self.f_result = tkfont.Font(family=ui, size=34, weight="bold")
        self.f_small = tkfont.Font(family=mono, size=10)
        self.f_key = tkfont.Font(family=ui, size=14)
        self.f_key_small = tkfont.Font(family=ui, size=12)
        self.f_hist = tkfont.Font(family=mono, size=11)

        self.expr_var = tk.StringVar()
        self.result_var = tk.StringVar(value="0")
        self.info_var = tk.StringVar(value="")
        self.memory_var = tk.StringVar(value="")

        left = tk.Frame(self, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        self._build_display(left)
        self._build_keypad(left)
        self._build_history()
        self._bind_keys()

        self.expr_var.trace_add("write", self._on_expression_change)
        self.entry.focus_set()

    # -- разметка ----------------------------------------------------------

    def _build_display(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=DISPLAY)
        wrap.pack(fill="x", padx=12, pady=(12, 8))

        top = tk.Frame(wrap, bg=DISPLAY)
        top.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(top, textvariable=self.memory_var, bg=DISPLAY, fg=ACCENT,
                 font=self.f_small).pack(side="left")
        tk.Label(top, text="Ctrl+H — история · Enter — посчитать", bg=DISPLAY,
                 fg=MUTED, font=self.f_small).pack(side="right")

        self.entry = tk.Entry(
            wrap, textvariable=self.expr_var, font=self.f_input, bg=DISPLAY,
            fg=FG, insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=0, justify="right",
        )
        self.entry.pack(fill="x", padx=14, pady=(6, 0), ipady=4)

        self.result_label = tk.Label(
            wrap, textvariable=self.result_var, bg=DISPLAY, fg=FG,
            font=self.f_result, anchor="e",
        )
        self.result_label.pack(fill="x", padx=14)
        self.result_label.bind("<Double-Button-1>", lambda _event: self.copy_result())

        tk.Label(wrap, textvariable=self.info_var, bg=DISPLAY, fg=MUTED,
                 font=self.f_small, anchor="e").pack(fill="x", padx=14, pady=(0, 12))

    def _build_keypad(self, parent: tk.Frame) -> None:
        pad = tk.Frame(parent, bg=BG)
        pad.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        for column in range(6):
            pad.columnconfigure(column, weight=1, uniform="key")
        for row in range(len(KEYPAD)):
            pad.rowconfigure(row, weight=1, uniform="key")

        for row, keys in enumerate(KEYPAD):
            for column, (label, style, action) in enumerate(keys):
                bg, active, fg = STYLES[style]
                span = 2 if label == "=" else 1
                font = self.f_key if style in ("num", "op", "eq") else self.f_key_small
                button = tk.Button(
                    pad, text=label, command=self._make_command(action), bg=bg,
                    fg=fg, activebackground=active, activeforeground=FG,
                    font=font, relief="flat", bd=0, highlightthickness=0,
                    cursor="hand2", takefocus=False,
                )
                button.grid(row=row, column=column, columnspan=span,
                            sticky="nsew", padx=3, pady=3)
                self.buttons[label] = button

    def _build_history(self) -> None:
        self.history_frame = tk.Frame(self, bg=PANEL, width=250)
        self.history_frame.pack(side="right", fill="y")
        self.history_frame.pack_propagate(False)

        head = tk.Frame(self.history_frame, bg=PANEL)
        head.pack(fill="x", padx=12, pady=(14, 6))
        tk.Label(head, text="История", bg=PANEL, fg=FG,
                 font=self.f_key_small).pack(side="left")
        tk.Button(head, text="очистить", command=self.clear_history, bg=PANEL,
                  fg=MUTED, activebackground=PANEL, activeforeground=ACCENT,
                  font=self.f_small, relief="flat", bd=0, highlightthickness=0,
                  cursor="hand2", takefocus=False).pack(side="right")

        self.history_list = tk.Listbox(
            self.history_frame, bg=PANEL, fg=FG, font=self.f_hist,
            selectbackground=OP_BG, selectforeground=FG, relief="flat", bd=0,
            highlightthickness=0, activestyle="none", takefocus=False,
        )
        self.history_list.pack(fill="both", expand=True, padx=8)
        self.history_list.bind("<Double-Button-1>", lambda _e: self.use_history("result"))

        buttons = tk.Frame(self.history_frame, bg=PANEL)
        buttons.pack(fill="x", padx=8, pady=10)
        for text, mode in (("результат", "result"), ("выражение", "expression")):
            tk.Button(buttons, text=text, command=lambda m=mode: self.use_history(m),
                      bg=FUN_BG, fg=MUTED, activebackground=FUN_ACTIVE,
                      activeforeground=FG, font=self.f_small, relief="flat",
                      bd=0, highlightthickness=0, cursor="hand2",
                      takefocus=False).pack(
                side="left", expand=True, fill="x", padx=2, ipady=4)

    # -- команды кнопок ----------------------------------------------------

    def _make_command(self, action: str):
        if not action.startswith("@"):
            return lambda: self.insert(action)
        handlers = {
            "@second": self.toggle_second,
            "@angle": self.toggle_angle,
            "@clear": self.clear,
            "@back": self.backspace,
            "@equals": self.equals,
            "@sign": self.toggle_sign,
            "@inv": self.reciprocal,
            "@mc": self.memory_clear,
            "@mr": self.memory_recall,
            "@m+": lambda: self.memory_add(1),
            "@m-": lambda: self.memory_add(-1),
        }
        return handlers[action]

    def insert(self, text: str) -> None:
        """Вставляет текст в позицию курсора; ``()`` оставляет курсор внутри."""
        if self.just_evaluated:
            # после «=» цифра начинает новый ввод, а оператор продолжает старый
            if text[:1].isdigit() or text[:1].isalpha() or text in ("(", "."):
                self.expr_var.set("")
            self.just_evaluated = False
        position = self.entry.index("insert")
        self.entry.insert(position, text)
        if text.endswith("()"):
            self.entry.icursor(position + len(text) - 1)
        self.entry.focus_set()

    def clear(self) -> None:
        self.expr_var.set("")
        self.result_var.set("0")
        self.info_var.set("")
        self.result_label.configure(fg=FG)
        self.just_evaluated = False
        self.entry.focus_set()

    def backspace(self) -> None:
        position = self.entry.index("insert")
        if position:
            self.entry.delete(position - 1)
        self.entry.focus_set()

    def toggle_second(self) -> None:
        self.second = not self.second
        for label, (alt_label, alt_action) in SECOND.items():
            button = self.buttons[label]
            shown, action = ((alt_label, alt_action) if self.second
                             else (label, self._default_action(label)))
            button.configure(text=shown, command=self._make_command(action),
                             fg=ACCENT if self.second else MUTED)
        self.buttons["2nd"].configure(
            bg=ACCENT if self.second else FUN_BG,
            fg="#20242c" if self.second else MUTED)

    @staticmethod
    def _default_action(label: str) -> str:
        for row in KEYPAD:
            for key_label, _style, action in row:
                if key_label == label:
                    return action
        raise KeyError(label)

    def toggle_angle(self) -> None:
        mode = self.calc.toggle_angle_mode()
        self.buttons["DEG"].configure(text=mode.upper())
        self._preview()

    def toggle_sign(self) -> None:
        text = self.expr_var.get().strip()
        if not text:
            self.expr_var.set("-")
        elif text.startswith("-(") and text.endswith(")"):
            self.expr_var.set(text[2:-1])
        elif text.startswith("-"):
            self.expr_var.set(text[1:])
        else:
            self.expr_var.set(f"-({text})")
        self.entry.icursor("end")
        self.entry.focus_set()

    def reciprocal(self) -> None:
        text = self.expr_var.get().strip()
        if text:
            self.expr_var.set(f"1/({text})")
            self.entry.icursor("end")
        self.entry.focus_set()

    # -- память ------------------------------------------------------------

    def _current_value(self):
        try:
            return self.calc.evaluate(self.expr_var.get(), commit=False).value
        except CalcError:
            return None

    def memory_clear(self) -> None:
        self.calc.memory = 0
        self._update_memory()

    def memory_recall(self) -> None:
        self.insert(self.calc.format(self.calc.memory))

    def memory_add(self, sign: int) -> None:
        value = self._current_value()
        if value is None:
            return
        self.calc.memory += sign * value
        self._update_memory()

    def _update_memory(self) -> None:
        self.memory_var.set("" if self.calc.memory == 0
                            else f"M = {self.calc.format(self.calc.memory)}")

    # -- вычисление --------------------------------------------------------

    def _on_expression_change(self, *_args) -> None:
        self.just_evaluated = False
        self._preview()

    def _preview(self) -> None:
        text = self.expr_var.get().strip()
        if not text:
            self.result_var.set("0")
            self.info_var.set("")
            self.result_label.configure(fg=FG)
            return
        try:
            result = self.calc.evaluate(text, commit=False)
        except CalcError:
            self.result_label.configure(fg=MUTED)  # ввод ещё не дописан
            return
        self.result_label.configure(fg=FG)
        self.result_var.set(result.text)
        self.info_var.set(self.calc.format_bases(result.value) or "")

    def equals(self) -> None:
        text = self.expr_var.get().strip()
        if not text:
            return
        try:
            result = self.calc.evaluate(text)
        except CalcError as error:
            self.result_var.set("ошибка")
            self.result_label.configure(fg=RED)
            self.info_var.set(error.message)
            return
        self.result_label.configure(fg=FG)
        self.result_var.set(result.text)
        self.info_var.set(self.calc.format_bases(result.value) or "")
        prefix = f"{result.assigned} = " if result.assigned else ""
        self.history_list.insert("end", f"{result.expression} = {prefix}{result.text}")
        self.history_list.see("end")
        self.history_index = None
        self.expr_var.set(result.text)
        self.entry.icursor("end")
        self.just_evaluated = True

    def copy_result(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.result_var.get())
        self.info_var.set("результат скопирован")

    # -- история -----------------------------------------------------------

    def use_history(self, mode: str) -> None:
        selection = self.history_list.curselection()
        if not selection:
            return
        item = self.calc.history[selection[0]]
        self.insert(item.expression if mode == "expression" else item.text)

    def clear_history(self) -> None:
        self.calc.history.clear()
        self.history_list.delete(0, "end")

    def toggle_history(self) -> None:
        self.history_visible = not self.history_visible
        if self.history_visible:
            self.history_frame.pack(side="right", fill="y")
        else:
            self.history_frame.pack_forget()

    def step_history(self, delta: int) -> None:
        """Стрелки ↑/↓ подставляют предыдущие выражения."""
        history = self.calc.history
        if not history:
            return
        if self.history_index is None:
            self.history_index = len(history)
        self.history_index = max(0, min(len(history) - 1, self.history_index + delta))
        self.expr_var.set(history[self.history_index].expression)
        self.entry.icursor("end")

    # -- клавиатура --------------------------------------------------------

    def _bind_keys(self) -> None:
        self.bind("<Return>", lambda _e: self.equals())
        self.bind("<KP_Enter>", lambda _e: self.equals())
        self.bind("<Escape>", lambda _e: self.clear())
        self.bind("<Up>", lambda _e: self.step_history(-1))
        self.bind("<Down>", lambda _e: self.step_history(1))
        self.bind("<Control-h>", lambda _e: self.toggle_history())
        self.bind("<Control-H>", lambda _e: self.toggle_history())
        self.bind("<Control-Shift-C>", lambda _e: self.copy_result())
        self.bind("<F9>", lambda _e: self.toggle_sign())


def run() -> None:
    """Точка входа оконного режима."""
    CalculatorApp().mainloop()
