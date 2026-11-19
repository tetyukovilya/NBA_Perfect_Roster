"""Графическая оболочка текстовой игры (Tkinter, без внешних зависимостей).

Запуск: nba-game-gui (после pip install -e .) или
python -m nba_analysis.textgame.gui.

Устройство: движок бежит в фоновом потоке и шлёт события в очередь —
снимки площадки каждый тик (on_tick) и строки play-by-play (printer).
GUI-поток разбирает очередь через root.after: снимок анимируется
(интерполяция позиций между тиками), строки уходят в лог с подсветкой.
Между тиками движок ждёт разрешения — темп задаёт ползунок скорости.

Составы: можно играть готовыми пятёрками (по WS/OWS/DWS) или открыть
«Составы...» и выбрать любых игроков из датасета на каждую позицию.
"""
from __future__ import annotations

import queue
import random
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from ..config import AnalysisConfig, STANDARD_POSITIONS
from ..models import Lineup, Player
from ..pipeline import build_lineups, load_dataset
from .engine import TickSnapshot, simulate_game

# Размеры холста и отступы.
COURT_L, COURT_W = 14.0, 15.0
W, H, MARGIN = 560, 620, 44

COLOR_OFF = "#f39c12"     # атака (оранжевый)
COLOR_DEF = "#2471a3"     # защита (синий)
COLOR_BALL = "#f7d038"    # мяч
COLOR_LINE = "#dddddd"

FRAME_MS = 30              # шаг интерполяции, мс
TOP_PER_POS = 60           # сколько игроков на позицию показывать в выборе


def _short(name: str) -> str:
    """«Kareem Abdul-Jabbar» -> «Abdul-Jabbar», «Michael Jordan» -> «Jordan»."""
    parts = name.split()
    return parts[-1] if len(parts) > 1 else name


def _display(p: Player) -> str:
    return f"{p.name} ({p.season} {p.team})"


class RosterDialog(tk.Toplevel):
    """Модальный диалог: по 5 комбобоксов (PG..C) на каждую команду."""

    def __init__(self, app: "GameApp", prefill: dict[str, dict[str, Player]]):
        super().__init__(app.root)
        self.title("Составы команд")
        self.resizable(False, False)
        self.result: dict[str, dict[str, Player]] | None = None
        self._index = {pos: {_display(p): p for p in app.players_by_pos[pos]}
                       for pos in STANDARD_POSITIONS}
        self._boxes: dict[tuple[str, str], ttk.Combobox] = {}

        ttk.Label(self, text="Команда A", font=("Segoe UI", 10, "bold")
                  ).grid(row=0, column=1, pady=(10, 2))
        ttk.Label(self, text="Команда B", font=("Segoe UI", 10, "bold")
                  ).grid(row=0, column=2, pady=(10, 2))
        for r, pos in enumerate(STANDARD_POSITIONS, start=1):
            ttk.Label(self, text=pos).grid(row=r, column=0, padx=(12, 4), sticky="e")
            for col_i, col in ((1, "A"), (2, "B")):
                values = list(self._index[pos])
                box = ttk.Combobox(self, values=values, width=34, state="readonly")
                cur = prefill[col].get(pos)
                box.set(_display(cur) if cur is not None else values[0])
                box.grid(row=r, column=col_i, padx=6, pady=2)
                self._boxes[(col, pos)] = box
        btns = ttk.Frame(self)
        btns.grid(row=len(STANDARD_POSITIONS) + 1, column=0, columnspan=3, pady=10)
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=6)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=6)

        self.transient(app.root)
        self.update_idletasks()
        x = app.root.winfo_x() + (app.root.winfo_width() - self.winfo_width()) // 2
        y = app.root.winfo_y() + (app.root.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _ok(self) -> None:
        self.result = {
            col: {pos: self._index[pos][box.get()]
                  for (c, pos), box in self._boxes.items() if c == col}
            for col in ("A", "B")
        }
        self.destroy()


class GameApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("NBA Text Game — GUI")
        root.resizable(False, False)

        self._build_controls()
        self.canvas = tk.Canvas(root, width=W, height=H, bg="#1a472a",
                                highlightthickness=0)
        self.canvas.grid(row=2, column=0, padx=8, pady=8)
        self.log = ScrolledText(root, width=58, height=38, state="disabled",
                                font=("Consolas", 9))
        self.log.grid(row=2, column=1, padx=8, pady=8, sticky="n")
        self._setup_log_tags()
        self.score_var = tk.StringVar(value="Выбери пятёрки и нажми «Играть»")
        ttk.Label(root, textvariable=self.score_var, font=("Segoe UI", 11, "bold")
                  ).grid(row=3, column=0, columnspan=2, pady=(0, 8))

        # Данные и состояние составов.
        self.data = None
        self.lineups: dict[str, Lineup] = {}
        self.players_by_pos: dict[str, list[Player]] = {}
        self.custom: dict[str, dict[str, Player] | None] = {"A": None, "B": None}
        # Анимация.
        self._prev_pos: dict[int, tuple[float, float]] = {}
        self._running = False
        self._pump_running = False

        self._draw_court()
        # Данные грузим сразу после отрисовки окна, чтобы комбобоксы
        # пятёрок и «Составы...» работали с первого клика.
        self.root.after(100, self._ensure_data)

    # --- UI-сборка ---------------------------------------------------------
    def _build_controls(self) -> None:
        bar = ttk.Frame(self.root)
        bar.grid(row=0, column=0, columnspan=2, pady=6)
        ttk.Label(bar, text="Пятёрка A:").pack(side="left", padx=(8, 2))
        self.combo_a = ttk.Combobox(bar, width=10, state="readonly")
        self.combo_a.pack(side="left")
        ttk.Label(bar, text="Пятёрка B:").pack(side="left", padx=(8, 2))
        self.combo_b = ttk.Combobox(bar, width=10, state="readonly")
        self.combo_b.pack(side="left")
        ttk.Label(bar, text="Владений:").pack(side="left", padx=(8, 2))
        self.spin_pos = tk.Spinbox(bar, from_=2, to=60, width=4)
        self.spin_pos.delete(0, "end")
        self.spin_pos.insert(0, "12")
        self.spin_pos.pack(side="left")
        ttk.Label(bar, text="Seed (пусто — случайный):").pack(side="left", padx=(8, 2))
        self.entry_seed = tk.Entry(bar, width=8)
        self.entry_seed.pack(side="left")
        ttk.Label(bar, text="Скорость:").pack(side="left", padx=(8, 2))
        self.speed = tk.Scale(bar, from_=0.0, to=1.0, resolution=0.05,
                              orient="horizontal", length=90)
        self.speed.set(0.25)
        self.speed.pack(side="left")

        bar2 = ttk.Frame(self.root)
        bar2.grid(row=1, column=0, columnspan=2)
        ttk.Button(bar2, text="Составы...", command=self.open_roster_dialog
                  ).pack(side="left", padx=8)
        self.btn = ttk.Button(bar2, text="Играть", command=self.start_game)
        self.btn.pack(side="left", padx=8)
        self.roster_hint = tk.StringVar(value="играют готовые пятёрки")
        ttk.Label(bar2, textvariable=self.roster_hint,
                  foreground="#666").pack(side="left", padx=8)

    def _setup_log_tags(self) -> None:
        for tag, color in (("score", "#2ecc71"), ("foul", "#e74c3c"),
                           ("screen", "#5dade2"), ("turnover", "#eb984e"),
                           ("header", "#f4d03f")):
            self.log.tag_configure(tag, foreground=color)

    # --- данные -------------------------------------------------------------
    def _ensure_data(self) -> None:
        if self.data is not None:
            return
        self.score_var.set("Загружаю данные (пара секунд)...")
        self.root.update()
        cfg = AnalysisConfig()
        self.data = load_dataset(cfg)
        self.lineups = {lu.name: lu for lu in build_lineups(cfg, self.data)}
        # Кандидаты на выбор: топ по WS на каждой позиции (после фильтров).
        by_pos: dict[str, list[Player]] = {pos: [] for pos in STANDARD_POSITIONS}
        for p in self.data.candidates:
            if p.pos in by_pos:
                by_pos[p.pos].append(p)
        for pos in by_pos:
            by_pos[pos].sort(key=lambda p: -(p.ws or 0.0))
            by_pos[pos] = by_pos[pos][:TOP_PER_POS]
        self.players_by_pos = by_pos
        names = list(self.lineups)
        self.combo_a.config(values=names)
        self.combo_b.config(values=names)
        self.combo_a.set(names[0])
        self.combo_b.set(names[1] if len(names) > 1 else names[0])

    def _effective_lineup(self, col: str) -> Lineup:
        custom = self.custom[col]
        if custom:
            players = tuple(custom[pos] for pos in STANDARD_POSITIONS)
            return Lineup(name=f"Custom {col}", metric="ws", players=players)
        combo = self.combo_a if col == "A" else self.combo_b
        return self.lineups[combo.get()]

    def open_roster_dialog(self) -> None:
        self._ensure_data()
        prefill: dict[str, dict[str, Player]] = {"A": {}, "B": {}}
        for col in ("A", "B"):
            for pos, player in self._effective_lineup(col).slots():
                prefill[col][pos] = player
        dialog = RosterDialog(self, prefill)
        self.root.wait_window(dialog)
        if dialog.result:
            self.custom = dialog.result
            a = ", ".join(_short(dialog.result["A"][p].name) for p in STANDARD_POSITIONS)
            b = ", ".join(_short(dialog.result["B"][p].name) for p in STANDARD_POSITIONS)
            self.roster_hint.set(f"свои составы — A: {a} | B: {b}")

    # --- координаты и отрисовка --------------------------------------------
    def _px(self, x: float, y: float) -> tuple[float, float]:
        s = min((W - 2 * MARGIN) / COURT_L, (H - 2 * MARGIN) / COURT_W)
        return MARGIN + x * s, H / 2 - y * s

    def _draw_court(self) -> None:
        """Статическая разметка: кольцо, краска, дуги, линия центра."""
        c = self.canvas
        x0, y_mid = self._px(0, 0)
        xc, _ = self._px(COURT_L, 0)
        c.create_line(xc, MARGIN // 2, xc, H - MARGIN // 2, fill=COLOR_LINE)
        xp, ytop = self._px(5, 2.5)
        _, ybot = self._px(5, -2.5)
        c.create_rectangle(x0, ytop, xp, ybot, outline=COLOR_LINE)
        s = (xp - x0) / 5.0
        c.create_arc(xp - 2.5 * s, ytop, xp + 2.5 * s, ybot,
                     start=-90, extent=180, outline=COLOR_LINE, style="arc")
        c.create_arc(x0 - 2.5 * s, y_mid - 2.5 * s, x0 + 2.5 * s, y_mid + 2.5 * s,
                     start=-90, extent=180, outline=COLOR_LINE, style="arc")
        c.create_arc(x0 - 8 * s, y_mid - 8 * s, x0 + 8 * s, y_mid + 8 * s,
                     start=-90, extent=180, outline=COLOR_LINE, style="arc",
                     dash=(4, 4))
        c.create_arc(x0 - 9 * s, y_mid - 9 * s, x0 + 9 * s, y_mid + 9 * s,
                     start=-55, extent=110, outline="#f5b041", style="arc", width=2)
        xc1, yc = self._px(6.5, 6.3)
        _, ycn = self._px(6.5, -6.3)
        xa, _ = self._px(9, 0)
        c.create_line(xc1, yc, xa, yc, fill="#f5b041", width=2)
        c.create_line(xc1, ycn, xa, ycn, fill="#f5b041", width=2)
        c.create_oval(x0 - 5, y_mid - 5, x0 + 5, y_mid + 5,
                      outline="white", width=2)

    def _draw_frame(self, offense: list, defense: list, handler_idx: int,
                    interp: dict[int, tuple[float, float]] | None = None) -> None:
        """Кадр: игроки с номерами и фамилиями + заметный мяч."""
        self.canvas.delete("players")

        def pos(agent):
            if interp is None:
                return agent.x, agent.y
            return interp.get(id(agent), (agent.x, agent.y))

        for d in defense:
            px, py = self._px(*pos(d))
            ring = "#95a5a6" if d.frozen > 0 else "white"
            self.canvas.create_oval(px - 13, py - 13, px + 13, py + 13,
                                    fill=COLOR_DEF, outline=ring, width=2,
                                    tags="players")
            if d.frozen > 0:  # «врезался в заслон / обведён» — крестик
                self.canvas.create_text(px, py, text="×", fill="white",
                                        font=("Segoe UI", 12, "bold"), tags="players")
        for i, a in enumerate(offense):
            px, py = self._px(*pos(a))
            has_ball = i == handler_idx
            outline = COLOR_BALL if has_ball else "white"
            self.canvas.create_oval(px - 13, py - 13, px + 13, py + 13,
                                    fill=COLOR_OFF, outline=outline, width=2,
                                    tags="players")
            self.canvas.create_text(px, py, text=str(i + 1), fill="white",
                                    font=("Segoe UI", 9, "bold"), tags="players")
            self.canvas.create_text(px, py - 22, text=_short(a.name), fill="white",
                                    font=("Segoe UI", 8), tags="players")
            if has_ball:
                bx, by = px + 18, py + 11
                self.canvas.create_oval(bx - 8, by - 8, bx + 8, by + 8,
                                        fill=COLOR_BALL, outline="black",
                                        width=1, tags="players")
                self.canvas.create_oval(bx - 4, by - 5, bx - 1, by - 2,
                                        fill="white", outline="", tags="players")

    # --- поток движка и очередь --------------------------------------------
    def _engine_line(self, line: str) -> None:
        self._queue.put(("line", line))

    def _engine_tick(self, snap: TickSnapshot) -> None:
        self._queue.put(("tick", snap))
        self._tick_gate.wait()
        self._tick_gate.clear()

    def _pump(self) -> None:
        """Разбор очереди: строки — в лог, тик — в анимацию."""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "line":
                    self._append_log(payload)
                elif kind == "tick":
                    self._animate_to(payload)
                elif kind == "done":
                    self.score_var.set(payload)
                    self._running = False
                    self.btn.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(FRAME_MS, self._pump)

    def _animate_to(self, snap: TickSnapshot) -> None:
        """Плавная интерполяция позиций от предыдущего тика к новому."""
        duration = self.speed.get()
        agents = snap.offense + snap.defense
        start = {id(a): self._prev_pos.get(id(a), (a.x, a.y)) for a in agents}
        target = {id(a): (a.x, a.y) for a in agents}

        if duration <= 0:
            self._draw_frame(snap.offense, snap.defense, snap.handler_idx, target)
            self._prev_pos = target
            self._tick_gate.set()
            return

        keys = list(start.keys() | target.keys())
        frames = max(2, int(duration * 1000 / FRAME_MS))
        state = {"n": 0}

        def step() -> None:
            try:
                n = state["n"] = state["n"] + 1
                t = min(1.0, n / frames)
                interp = {}
                for k in keys:
                    sx, sy = start.get(k, target.get(k, (0, 0)))
                    tx, ty = target.get(k, (sx, sy))
                    interp[k] = (sx + (tx - sx) * t, sy + (ty - sy) * t)
                self._draw_frame(snap.offense, snap.defense, snap.handler_idx, interp)
                self.score_var.set(f"Владение: {snap.clock} сек | тик {snap.tick}")
                if n < frames:
                    self.root.after(FRAME_MS, step)
                    return
                self._prev_pos = target
            except Exception as exc:
                # движок не должен ждать вечно, даже если кадр упал с ошибкой
                self._append_log(f"ОШИБКА ОТРИСОВКИ: {exc!r}")
                self._prev_pos = target
            self._tick_gate.set()

        self.root.after(FRAME_MS, step)

    # --- лог ----------------------------------------------------------------
    def _append_log(self, line: str) -> None:
        self.log.config(state="normal")
        tag = self._tag_for(line)
        if tag == "header":
            line = "\n" + line
        self.log.insert("end", line + "\n", tag or ())
        self.log.see("end")
        self.log.config(state="disabled")

    @staticmethod
    def _tag_for(line: str) -> str | None:
        low = line.lower()
        if line.startswith("=====") or line.startswith("--- счёт") or line.startswith("ИТОГ"):
            return "header"
        if "фол" in low:
            return "foul"
        if "попадание" in low or ("+" in line and "очко" in low):
            return "score"
        if "заслон" in low or "подмена" in low:
            return "screen"
        if "потеря" in low or "перехвач" in low:
            return "turnover"
        return None

    # --- запуск ---------------------------------------------------------------
    def start_game(self) -> None:
        if self._running:
            return  # игра уже идёт — повторный запуск игнорируем
        self._ensure_data()
        try:
            possessions = max(2, int(self.spin_pos.get()))
        except ValueError:
            possessions = 12
        # Пустое поле seed = каждый запуск случайный; явный seed = повторяемость.
        seed_text = self.entry_seed.get().strip()
        seed = int(seed_text) if seed_text else random.randrange(1, 10 ** 9)

        lu_a = self._effective_lineup("A")
        lu_b = self._effective_lineup("B")

        self.btn.config(state="disabled")
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self._prev_pos = {}
        self._queue: queue.Queue = queue.Queue()
        self._tick_gate = threading.Event()
        self._running = True
        self.score_var.set(f"Игра: {lu_a.name} vs {lu_b.name}")

        def run() -> None:
            try:
                score_a, score_b = simulate_game(
                    lu_a, lu_b, self.data.context,
                    possessions=possessions, seed=seed,
                    show_court_first=False,
                    printer=self._engine_line,
                    on_tick=self._engine_tick,
                )
                self._queue.put(("done", f"Готово: {lu_a.name} {score_a} — {score_b} {lu_b.name} (seed={seed})"))
            except Exception as exc:  # ошибку — в лог, а не в молчание
                self._queue.put(("line", f"ОШИБКА ДВИЖКА: {exc!r}"))
                self._queue.put(("done", "Ошибка"))

        threading.Thread(target=run, daemon=True).start()
        if not self._pump_running:
            self._pump_running = True
            self.root.after(FRAME_MS, self._pump)


def main() -> int:
    root = tk.Tk()
    GameApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
