"""Графическая оболочка текстовой игры (Tkinter, без внешних зависимостей).

Запуск: nba-game-gui (после pip install -e .) или
python -m nba_analysis.textgame.gui.

Слева — площадка с анимацией игроков (каждый тик = кадр), справа —
play-by-play лог с подсветкой событий. Вся математика — та же, что в
консольной версии: движок вызывает on_tick каждый тик и шлёт события
через printer.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from ..config import AnalysisConfig
from ..pipeline import build_lineups, load_dataset
from .engine import TickSnapshot, simulate_game

# Размеры холста и отступы.
COURT_L, COURT_W = 14.0, 15.0
W, H, MARGIN = 560, 620, 44

COLOR_OFF = "#e8852a"     # атака
COLOR_DEF = "#c0392b"     # защита
COLOR_BALL = "#f7d038"    # мяч
COLOR_LINE = "#dddddd"


def _short(name: str) -> str:
    """«Kareem Abdul-Jabbar» -> «Abdul-Jabbar», «Michael Jordan» -> «Jordan»."""
    parts = name.split()
    return parts[-1] if len(parts) > 1 else name


class GameApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("NBA Text Game — GUI (макет)")
        root.resizable(False, False)

        self._build_controls()
        self.canvas = tk.Canvas(root, width=W, height=H, bg="#1a472a",
                                highlightthickness=0)
        self.canvas.grid(row=1, column=0, padx=8, pady=8)
        self.log = ScrolledText(root, width=58, height=38, state="disabled",
                                font=("Consolas", 9))
        self.log.grid(row=1, column=1, padx=8, pady=8, sticky="n")
        self._setup_log_tags()
        self.score_var = tk.StringVar(value="Выбери пятёрки и нажми «Играть»")
        ttk.Label(root, textvariable=self.score_var, font=("Segoe UI", 11, "bold")
                  ).grid(row=2, column=0, columnspan=2, pady=(0, 8))

        self.data = None
        self.lineups: dict[str, object] = {}
        self._draw_court()

    # --- UI-сборка ---------------------------------------------------------
    def _build_controls(self) -> None:
        bar = ttk.Frame(self.root)
        bar.grid(row=0, column=0, columnspan=2, pady=6)
        ttk.Label(bar, text="Команда A:").pack(side="left", padx=(8, 2))
        self.combo_a = ttk.Combobox(bar, width=10, state="readonly")
        self.combo_a.pack(side="left")
        ttk.Label(bar, text="Команда B:").pack(side="left", padx=(8, 2))
        self.combo_b = ttk.Combobox(bar, width=10, state="readonly")
        self.combo_b.pack(side="left")
        ttk.Label(bar, text="Владений:").pack(side="left", padx=(8, 2))
        self.spin_pos = tk.Spinbox(bar, from_=2, to=60, width=4)
        self.spin_pos.delete(0, "end")
        self.spin_pos.insert(0, "12")
        self.spin_pos.pack(side="left")
        ttk.Label(bar, text="Seed:").pack(side="left", padx=(8, 2))
        self.entry_seed = tk.Entry(bar, width=6)
        self.entry_seed.insert(0, "42")
        self.entry_seed.pack(side="left")
        ttk.Label(bar, text="Скорость:").pack(side="left", padx=(8, 2))
        self.speed = tk.Scale(bar, from_=0.0, to=1.0, resolution=0.05,
                              orient="horizontal", length=90)
        self.speed.set(0.25)
        self.speed.pack(side="left")
        self.btn = ttk.Button(bar, text="Играть", command=self.start_game)
        self.btn.pack(side="left", padx=8)

    def _setup_log_tags(self) -> None:
        for tag, color in (("score", "#2ecc71"), ("foul", "#e74c3c"),
                           ("screen", "#5dade2"), ("turnover", "#eb984e"),
                           ("header", "#f4d03f")):
            self.log.tag_configure(tag, foreground=color)

    # --- координаты и отрисовка --------------------------------------------
    def _px(self, x: float, y: float) -> tuple[float, float]:
        s = min((W - 2 * MARGIN) / COURT_L, (H - 2 * MARGIN) / COURT_W)
        return MARGIN + x * s, H / 2 - y * s

    def _draw_court(self) -> None:
        """Статическая разметка: кольцо, краска, дуги, линия центра."""
        c = self.canvas
        x0, y_mid = self._px(0, 0)
        # линия центра (правая граница)
        xc, _ = self._px(COURT_L, 0)
        c.create_line(xc, MARGIN // 2, xc, H - MARGIN // 2, fill=COLOR_LINE)
        # краска: прямоугольник + полукруг
        xp, ytop = self._px(5, 2.5)
        _, ybot = self._px(5, -2.5)
        c.create_rectangle(x0, ytop, xp, ybot, outline=COLOR_LINE)
        s = (xp - x0) / 5.0
        c.create_arc(xp - 2.5 * s, ytop, xp + 2.5 * s, ybot,
                     start=-90, extent=180, outline=COLOR_LINE, style="arc")
        # restricted (r=2.5)
        c.create_arc(x0 - 2.5 * s, y_mid - 2.5 * s, x0 + 2.5 * s, y_mid + 2.5 * s,
                     start=-90, extent=180, outline=COLOR_LINE, style="arc")
        # средний (r=8, пунктир)
        c.create_arc(x0 - 8 * s, y_mid - 8 * s, x0 + 8 * s, y_mid + 8 * s,
                     start=-90, extent=180, outline=COLOR_LINE, style="arc",
                     dash=(4, 4))
        # трёхочковая: дуга r=9 + угловые линии
        c.create_arc(x0 - 9 * s, y_mid - 9 * s, x0 + 9 * s, y_mid + 9 * s,
                     start=-55, extent=110, outline="#f5b041", style="arc", width=2)
        xc1, yc = self._px(6.5, 6.3)
        _, ycn = self._px(6.5, -6.3)
        xa, _ = self._px(9, 0)
        c.create_line(xc1, yc, xa, yc, fill="#f5b041", width=2)
        c.create_line(xc1, ycn, xa, ycn, fill="#f5b041", width=2)
        # кольцо
        c.create_oval(x0 - 5, y_mid - 5, x0 + 5, y_mid + 5,
                      outline="white", width=2)

    def render(self, snap: TickSnapshot) -> None:
        """Один кадр: игроки, мяч, счётчик времени владения."""
        self.canvas.delete("players")
        for d in snap.defense:
            self._draw_player(d.x, d.y, _short(d.name), COLOR_DEF)
        for i, a in enumerate(snap.offense):
            self._draw_player(a.x, a.y, _short(a.name), COLOR_OFF,
                              has_ball=i == snap.handler_idx)
        self.score_var.set(
            f"Владение: {snap.clock} сек осталось | тик {snap.tick}"
        )
        self.canvas.update()

    def _draw_player(self, x: float, y: float, label: str,
                     color: str, has_ball: bool = False) -> None:
        px, py = self._px(x, y)
        r = 11
        self.canvas.create_oval(px - r, py - r, px + r, py + r, fill=color,
                                outline="white", tags="players")
        self.canvas.create_text(px, py - r - 8, text=label, fill="white",
                                font=("Segoe UI", 8), tags="players")
        if has_ball:
            self.canvas.create_oval(px + r - 3, py + r - 10, px + r + 7, py + r,
                                    fill=COLOR_BALL, outline="black",
                                    tags="players")

    # --- лог ----------------------------------------------------------------
    def printer(self, line: str) -> None:
        """Приём событий от движка: в лог с подсветкой + пауза между владениями."""
        self.log.config(state="normal")
        tag = self._tag_for(line)
        if tag == "header":
            line = "\n" + line
        self.log.insert("end", line + "\n", tag or ())
        self.log.see("end")
        self.log.config(state="disabled")
        self.root.update()
        if line.startswith("====="):
            time.sleep(max(self.speed.get(), 0.05))

    @staticmethod
    def _tag_for(line: str) -> str | None:
        low = line.lower()
        if line.startswith("=====") or line.startswith("--- счёт") or line.startswith("ИТОГ"):
            return "header"
        if "фол" in low:
            return "foul"
        if "попадание" in low or "+" in line and "очко" in low:
            return "score"
        if "заслон" in low or "подмена" in low:
            return "screen"
        if "потеря" in low or "перехвач" in low:
            return "turnover"
        return None

    # --- запуск ---------------------------------------------------------------
    def start_game(self) -> None:
        if self.data is None:
            self.btn.config(state="disabled")
            self.score_var.set("Загружаю данные (пара секунд)...")
            self.root.update()
            cfg = AnalysisConfig()
            self.data = load_dataset(cfg)
            self.lineups = {lu.name: lu for lu in build_lineups(cfg, self.data)}
            names = list(self.lineups)
            self.combo_a.config(values=names)
            self.combo_b.config(values=names)
            self.combo_a.set(names[0])
            self.combo_b.set(names[1] if len(names) > 1 else names[0])
            self.btn.config(state="normal")

        self.btn.config(state="disabled")
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        try:
            possessions = max(2, int(self.spin_pos.get()))
            seed = int(self.entry_seed.get() or 0)
        except ValueError:
            possessions, seed = 12, 42

        def on_tick(snap: TickSnapshot) -> None:
            self.render(snap)
            time.sleep(self.speed.get())

        lu_a = self.lineups[self.combo_a.get()]
        lu_b = self.lineups[self.combo_b.get()]
        self.score_var.set(f"Игра: {lu_a.name} vs {lu_b.name}")
        simulate_game(
            lu_a, lu_b, self.data.context,
            possessions=possessions, seed=seed,
            show_court_first=False,
            printer=self.printer,
            on_tick=on_tick,
        )
        self.score_var.set(f"Готово: {lu_a.name} vs {lu_b.name} (seed={seed})")
        self.btn.config(state="normal")


def main() -> int:
    root = tk.Tk()
    GameApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
