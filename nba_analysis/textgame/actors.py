"""Игроки-агенты: каждый принимает решения на основе своего профиля.

Решение принимается каждый тик (2 секунды):
    SHOOT     — бросок из текущей позиции
    FAKE      — финт броском (pump fake); если защитник клюёт,
                следующий бросок идёт с бонусом и без contest
    CROSSOVER — обводка с ведением; успех — защитник остаётся стоять,
                неудача — риск потерять мяч
    SCREEN    — партнёр ставит заслон на защитника владельца мяча;
                успех — защитник врезается в заслон (стоит 2 тика),
                дальше возможна подмена (switch)
    DRIVE     — прорыв к кольцу с ведением (риск потери/фола)
    MOVE      — смещение в свободную зону
    PASS      — пас партнёру (риск перехвата)

Пассивные свойства агента берутся из PlayerProfile (profiles.py), чтобы
текстовая игра давала те же вероятности, что и Monte-Carlo симуляция.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from ..profiles import PlayerProfile

# Скорость движения за тик (усл. ед./2 сек) по позициям: защитники быстрее.
SPEED_BY_POS = {"PG": 2.2, "SG": 2.1, "SF": 2.0, "PF": 1.8, "C": 1.6}
# Насколько защитник «отпускает» подальнего/менее опасного игрока.
SAG_BY_POS = {"PG": 1.0, "SG": 1.4, "SF": 1.6, "PF": 1.8, "C": 2.0}
# Склонность идти в обводку по позициям (защитники чаще).
CROSSOVER_P = {"PG": 0.25, "SG": 0.20, "SF": 0.12, "PF": 0.06, "C": 0.03}


class Action(Enum):
    SHOOT = "shoot"
    FAKE = "fake"
    CROSSOVER = "crossover"
    SCREEN = "screen"
    DRIVE = "drive"
    MOVE = "move"
    PASS = "pass"


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    # Для MOVE/DRIVE: целевая точка (x, y); для PASS: сам агент-адресат.
    target: tuple[float, float] | "PlayerAgent" | None = None


class PlayerAgent:
    """Игрок с позицией на площадке и «характером» из его статистики."""

    def __init__(
        self,
        profile: PlayerProfile,
        pos: str,
        x: float,
        y: float,
        rng: random.Random,
    ):
        self.profile = profile
        self.pos = pos
        self.x = x
        self.y = y
        self.rng = rng
        self.speed = SPEED_BY_POS.get(pos, 2.0)
        # Агрессивность защиты: чем выше STL%, тем ближе лезет защитник
        # (и тем чаще фолит/кушает на финты).
        self.pressure = min(profile.stl / 2.5, 1.0)
        # Игрок «открыт» (защитник обведён/врезался в заслон) до этого тика.
        self.open_until = -1
        # Число тиков, которые защитник стоит на месте (заслон/обводка).
        self.frozen = 0
        # Личные фолы за игру.
        self.personal_fouls = 0
        # Домашняя точка расстановки — сюда игрок встаёт в новом владении.
        self.home = (x, y)

    @property
    def name(self) -> str:
        return self.profile.name

    def dist_to(self, x: float, y: float) -> float:
        return ((self.x - x) ** 2 + (self.y - y) ** 2) ** 0.5

    def move_towards(self, tx: float, ty: float, court, multiplier: float = 1.0) -> None:
        d = self.dist_to(tx, ty)
        if d < 1e-6:
            return
        step = min(self.speed * multiplier, d)
        nx = self.x + (tx - self.x) / d * step
        ny = self.y + (ty - self.y) / d * step
        self.x, self.y = court.clamp(nx, ny)

    # --- решения с мячом ---------------------------------------------------
    def decide_with_ball(
        self,
        zone,               # ShotZone текущей позиции
        nearest_def_dist: float,
        tick: int,
        teammates: list["PlayerAgent"],
    ) -> Decision:
        rng = self.rng
        p = self.profile
        beat_open = self.open_until >= tick  # защитник уже обыгран
        open_shot = nearest_def_dist >= 2.2 or beat_open

        # После успешного обыгрыша защитник позади — бросаем почти всегда.
        if beat_open and zone.value != "backcourt" and rng.random() < 0.85:
            return Decision(Action.SHOOT)

        # Совсем открытый и в хорошей зоне — бросаем не раздумывая.
        if open_shot and zone.value != "backcourt":
            if zone.value in ("restricted", "paint", "corner_three"):
                return Decision(Action.SHOOT)
            if zone.value in ("midrange", "arc_three") and rng.random() < 0.6 + p.three_rate:
                return Decision(Action.SHOOT)

        has_big = any(t.pos in ("PF", "C") for t in teammates)

        # Мяч к нам плотно прижали: финт / обводка / прорыв / пас.
        if nearest_def_dist < 1.6:
            roll = rng.random()
            if roll < 0.22:
                return Decision(Action.FAKE)
            if roll < 0.22 + CROSSOVER_P.get(self.pos, 0.1):
                return Decision(Action.CROSSOVER)
            if roll < 0.62:
                return Decision(Action.DRIVE, (0.5, 0.0))
            return self._best_pass(teammates)

        # Плотная, но не давящая опека: заслон или обыгрыш.
        if nearest_def_dist < 2.8:
            roll = rng.random()
            if roll < 0.30 and has_big:
                return Decision(Action.SCREEN)
            if roll < 0.30 + CROSSOVER_P.get(self.pos, 0.1):
                return Decision(Action.CROSSOVER)
            if roll < 0.60:
                return Decision(Action.DRIVE, (0.5, 0.0))
            return self._best_pass(teammates)

        # Любитель дальнего и стоит у дуги — пусть бросает чуть чаще.
        if zone.value in ("arc_three", "corner_three") and p.three_rate > 0.35 and rng.random() < 0.4:
            return Decision(Action.SHOOT)

        # Средний автомат: то прорыв, то перестроение, то пас.
        roll = rng.random()
        if roll < 0.35:
            return Decision(Action.DRIVE, (0.5, 0.0))
        if roll < 0.55:
            return self._best_pass(teammates)
        # Смещение вдоль дуги в свободную сторону.
        side = 1.0 if self.y <= 0 else -1.0
        return Decision(Action.MOVE, (max(self.x - 2.0, 3.0), min(self.y + 3.0 * side, 6.5)))

    def _best_pass(self, teammates: list["PlayerAgent"]) -> Decision:
        """Пас самому открытому партнёру (ближайший по полю — макет)."""
        if not teammates:
            return Decision(Action.MOVE, (self.x, self.y))
        best = min(teammates, key=lambda t: abs(t.x - self.x) + abs(t.y - self.y))
        return Decision(Action.PASS, best)

    # --- решения в защите ---------------------------------------------------
    def defend_update(self, mark: "PlayerAgent", court) -> None:
        """Держать дистанцию между своим игроком и кольцом.

        «Замороженный» защитник (врезался в заслон, обведён) тик стоит.
        """
        if self.frozen > 0:
            return
        sag = SAG_BY_POS.get(mark.pos, 1.5) * (1.0 - 0.5 * self.pressure)
        tx = mark.x * (1 + sag * 0.15)
        ty = mark.y * (1 + sag * 0.15)
        self.move_towards(tx, ty, court)
