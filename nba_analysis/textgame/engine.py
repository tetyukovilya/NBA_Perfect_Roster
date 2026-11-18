"""Движок текстовой игры: тиковая симуляция владения с play-by-play.

Один тик = 2 секунды, владение длится до 12 тиков (24 секунды).
События владения: потеря при ведении/перехват паса, финт с вероятностью
«закусить» защитника, бросок с учётом зоны, дистанции защитника и бонуса
финта, подбор в нападении.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..config import SimulationConfig
from ..models import Lineup
from ..profiles import LeagueContext, build_profile
from .actors import Action, Decision, PlayerAgent
from .court import Court, ShotZone, is_three, range_factor, zone_at

TICK_SECONDS = 2
TICKS_PER_POSSESSION = 12
MAX_OFFENSIVE_REBOUNDS = 3

# Стартовые точки атаки по позициям (x, y) — простая расстановка 1-2-2.
SPOTS = {
    "PG": (11.0, 0.0),
    "SG": (8.5, 5.5),
    "SF": (7.0, -6.0),
    "PF": (5.0, 3.0),
    "C": (2.8, 0.0),
}

# Модификаторы точности.
OPENNESS_SLOPE = 0.09      # штраф за каждую усл. единицу близости защитника
FAKE_BONUS = 1.12          # бонус, если защитник клюнул на финт
MAX_P_MAKE = 0.85


@dataclass(slots=True)
class PossessionResult:
    points: int
    events: list[str] = field(default_factory=list)


def _setup(lineup: Lineup, ctx, rng) -> list[PlayerAgent]:
    agents = []
    for pos, player in lineup.slots():
        x, y = SPOTS.get(pos, (8.0, 0.0))
        profile = build_profile(player, ctx, cfg=_DEFAULT_SIM_CFG)
        agents.append(PlayerAgent(profile, pos, x + rng.uniform(-0.5, 0.5),
                                  y + rng.uniform(-0.5, 0.5), rng))
    return agents


_DEFAULT_SIM_CFG = SimulationConfig()


def _nearest_defender(handler: PlayerAgent, defense: list[PlayerAgent]) -> PlayerAgent:
    return min(defense, key=lambda d: d.dist_to(handler.x, handler.y))


def _openness(handler: PlayerAgent, defender: PlayerAgent, fake_active: bool) -> float:
    """Множитель точности: 1.0 = совсем открыт, ниже — плотный contest."""
    if fake_active:
        return FAKE_BONUS
    dist = defender.dist_to(handler.x, handler.y)
    return max(0.55, 1.12 - OPENNESS_SLOPE * dist)


def simulate_possession(
    offense: list[PlayerAgent],
    defense: list[PlayerAgent],
    court: Court,
    rng: random.Random,
    show_court: bool = False,
) -> PossessionResult:
    """Одно владение команды offense против пятёрки defense."""
    events: list[str] = []
    points = 0
    orebounds = 0
    handler_idx = 0  # начинает PG (первый в списке)

    # Защитники встают на своих игроков (по порядку позиций).
    for d, mark in zip(defense, offense):
        d.x, d.y = mark.x + 1.2, mark.y + 0.8

    for tick in range(1, TICKS_PER_POSSESSION + 1):
        clock = TICKS_PER_POSSESSION - tick + 1
        handler = offense[handler_idx]

        # 1. Защита двигается.
        for d, mark in zip(defense, offense):
            d.defend_update(mark, court)
        on_ball = _nearest_defender(handler, defense)

        if show_court:
            events.append(court.render(
                [(a.name, a.x, a.y, i == handler_idx) for i, a in enumerate(offense)],
                [(d.name, d.x, d.y) for d in defense],
                tick,
            ))

        nearest_dist = on_ball.dist_to(handler.x, handler.y)
        zone = zone_at(handler.x, handler.y)
        forced = clock == 1  # последний тик — бросок любой ценой

        # 2. Решение.
        if forced:
            decision = Decision(Action.SHOOT)
        else:
            others = [a for i, a in enumerate(offense) if i != handler_idx]
            decision = handler.decide_with_ball(zone, nearest_dist, tick, others)

        # 3. Исполнение.
        if decision.action is Action.FAKE:
            bite_p = 0.25 + 0.45 * on_ball.pressure  # агрессивные чаще клюют
            if rng.random() < bite_p:
                handler.fake_open_until = tick + 2
                on_ball.move_towards(handler.x, handler.y, court, multiplier=1.5)
                events.append(
                    f"[{clock:>2}с] {handler.name} — финт броском! "
                    f"{on_ball.name} клюёт и вылетает навстречу."
                )
            else:
                events.append(f"[{clock:>2}с] {handler.name} — финт, {on_ball.name} не реагирует.")
            continue

        if decision.action is Action.DRIVE:
            steal_p = min(on_ball.pressure * on_ball.profile.stl / 30.0, 0.22)
            if rng.random() < steal_p:
                events.append(
                    f"[{clock:>2}с] {handler.name} прорывается... но {on_ball.name} "
                    f"выбивает мяч — ПОТЕРЯ!"
                )
                return PossessionResult(points, events)
            tx, ty = decision.target  # type: ignore[misc]
            handler.move_towards(tx, ty, court, multiplier=1.35)
            events.append(f"[{clock:>2}с] {handler.name} прорывается к кольцу.")
            continue

        if decision.action is Action.MOVE:
            tx, ty = decision.target  # type: ignore[misc]
            handler.move_towards(tx, ty, court)
            events.append(f"[{clock:>2}с] {handler.name} перестраивается без броска.")
            continue

        if decision.action is Action.PASS:
            target = decision.target
            intercept_p = 0.03 + 0.08 * _nearest_defender(target, defense).pressure
            if rng.random() < intercept_p:
                events.append(
                    f"[{clock:>2}с] Передача {handler.name} -> {target.name} перехвачена! ПОТЕРЯ!"
                )
                return PossessionResult(points, events)
            handler_idx = offense.index(target)
            events.append(f"[{clock:>2}с] {handler.name} отдаёт пас на {target.name}.")
            continue

        # SHOOT
        fake_active = handler.fake_open_until >= tick
        openness = _openness(handler, on_ball, fake_active)
        three = is_three(zone)
        base = handler.profile.p3 if three else handler.profile.p2
        p_make = min(base * range_factor(zone) * openness, MAX_P_MAKE)
        mark = "3" if three else "2"
        if rng.random() < p_make:
            pts = 3 if three else 2
            events.append(
                f"[{clock:>2}с] {handler.name} — попадание с {'трёх' if three else 'двух'} "
                f"({zone.value}, p={p_make:.0%})! +{pts}"
            )
            return PossessionResult(pts, events)
        events.append(
            f"[{clock:>2}с] {handler.name} бросает ({mark}, {zone.value}, p={p_make:.0%}) — мимо."
        )

        # Подбор.
        orb = sum(a.profile.orb for a in offense)
        drb = sum(d.profile.drb for d in defense)
        p_oreb = orb / (orb + drb) if (orb + drb) > 0 else 0.25
        if rng.random() < p_oreb and orebounds < MAX_OFFENSIVE_REBOUNDS:
            orebounds += 1
            events.append(f"Подбор в нападении — владение продолжается ({orebounds}-й).")
            continue
        return PossessionResult(points, events)

    return PossessionResult(points, events + ["Звучит сирена владения — 24 секунды."])


def simulate_game(
    lineup_a: Lineup,
    lineup_b: Lineup,
    ctx: LeagueContext,
    possessions: int = 12,
    seed: int | None = None,
    show_court_first: bool = True,
) -> tuple[int, int]:
    """Короткая показательная игра между двумя пятёрками (play-by-play)."""
    rng = random.Random(seed)
    court = Court()
    team_a = _setup(lineup_a, ctx, rng)
    team_b = _setup(lineup_b, ctx, rng)
    score_a = score_b = 0

    for i in range(possessions):
        attacking, defending = (team_a, team_b) if i % 2 == 0 else (team_b, team_a)
        name = lineup_a.name if i % 2 == 0 else lineup_b.name
        print(f"\n===== Владение {i + 1}: мяч у пятёрки {name} =====")
        res = simulate_possession(
            attacking, defending, court, rng,
            show_court=show_court_first and i == 0,
        )
        for e in res.events:
            print(e)
        if i % 2 == 0:
            score_a += res.points
        else:
            score_b += res.points
        print(f"--- счёт: {lineup_a.name} {score_a} : {score_b} {lineup_b.name}")

    print(f"\nИТОГ: {lineup_a.name} {score_a} — {score_b} {lineup_b.name}")
    return score_a, score_b
