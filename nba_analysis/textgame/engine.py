"""Движок текстовой игры: тиковая симуляция владения с play-by-play.

Один тик = 2 секунды, владение длится до 12 тиков (24 секунды).

Механики владения:
- обыгрыш защитника: финт броском, кроссовер, заслон (с возможной подменой);
- потери: выбить мяч при ведении/обводке, перехват паса;
- фолы: личные (считаются по игрокам) и командные (за половину); фол вне
  броска до лимита — ввод из-за боковой, с 4-го командного — 2 штрафных;
  фол на броске — всегда 2/3 штрафных (3 при трёхочковой), попадание + фол
  — очки с броска плюс 1 штрафной (and-one);
- бросок: p2/p3 × коэффициент зоны × открытость (дистанция защитника,
  бонус после обыгрыша);
- промах → подбор по ORB/(ORB+DRB).

Подмена (switch): после удачного заслона защита с вероятностью 0.5 меняет
опекунов — защитник заслоняющего берёт владельца мяча. Схема опеки хранится
в matchup: matchup[i] — индекс защитника, который опекает offense[i].
"""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from ..config import SimulationConfig
from ..models import Lineup
from ..profiles import LeagueContext, build_profile
from .actors import Action, Decision, PlayerAgent
from .court import Court, is_three, range_factor, zone_at

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
BEAT_BONUS = 1.12          # бонус, если защитник обыгран (финт/заслон/кроссовер)
MAX_P_MAKE = 0.85

# Фолы и штрафные.
LEAGUE_FT_PCT = 0.75       # индивидуального FT% в датасете нет
REACH_IN_FOUL = 0.08       # базовая P(фола) при прорыве
SHOOTING_FOUL = 0.10       # базовая P(фола) при броске в плотном contest
FOUL_PRESSURE_K = 0.12     # добавка к фолу за агрессивность защитника
SHOOTING_FOUL_DIST = 1.8   # contest ближе этого — возможен фол на броске
TEAM_FOUL_LIMIT = 4        # с 4-го командного фола в половине — штрафные
PERSONAL_FOUL_LIMIT = 6    # 6 личных — выбывание (в макете только лог)


@dataclass(slots=True)
class PossessionResult:
    points: int
    events: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GameState:
    """Состояние игры: командные фолы текущей половины."""

    team_fouls: dict[str, int] = field(default_factory=dict)

    def add_foul(self, team: str) -> int:
        """Засчитать командный фол; вернуть новое число фолов в половине."""
        self.team_fouls[team] = self.team_fouls.get(team, 0) + 1
        return self.team_fouls[team]

    def reset_half(self) -> None:
        self.team_fouls.clear()


@dataclass(slots=True)
class TickSnapshot:
    """Снимок площадки в начале тика — для GUI-отрисовки.

    Списки агентов передаются по ссылке и мутируются дальше;
    снапшот валиден только до следующего тика.
    """

    tick: int
    clock: int                       # осталось секунд владения
    offense: list[PlayerAgent]
    defense: list[PlayerAgent]
    handler_idx: int


OnTick = Callable[[TickSnapshot], None]


_DEFAULT_SIM_CFG = SimulationConfig()


def _setup(lineup: Lineup, ctx, rng) -> list[PlayerAgent]:
    agents = []
    for pos, player in lineup.slots():
        x, y = SPOTS.get(pos, (8.0, 0.0))
        profile = build_profile(player, ctx, cfg=_DEFAULT_SIM_CFG)
        agents.append(PlayerAgent(profile, pos, x + rng.uniform(-0.5, 0.5),
                                  y + rng.uniform(-0.5, 0.5), rng))
    return agents


def _nearest_defender(handler: PlayerAgent, defense: list[PlayerAgent]) -> PlayerAgent:
    return min(defense, key=lambda d: d.dist_to(handler.x, handler.y))


def _openness(handler: PlayerAgent, defender: PlayerAgent, beat_active: bool) -> float:
    """Множитель точности: 1.0 = совсем открыт, ниже — плотный contest."""
    if beat_active:
        return BEAT_BONUS
    dist = defender.dist_to(handler.x, handler.y)
    return max(0.55, 1.12 - OPENNESS_SLOPE * dist)


def _free_throws(shooter: PlayerAgent, n: int, events: list[str], rng: random.Random) -> int:
    """n штрафных с лиговым процентом; очки начисляются, события — в лог."""
    made = 0
    for _ in range(n):
        made += rng.random() < LEAGUE_FT_PCT
    events.append(f"Штрафные: {shooter.name} реализует {made} из {n}.")
    return made


def _register_foul(defender: PlayerAgent, def_team: str, state: GameState,
                   events: list[str]) -> int:
    """Личный + командный фол; вернуть число командных фолов в половине."""
    defender.personal_fouls += 1
    team_n = state.add_foul(def_team)
    note = ""
    if defender.personal_fouls == PERSONAL_FOUL_LIMIT - 1:
        note = " (5 личных — один до выбывания)"
    elif defender.personal_fouls >= PERSONAL_FOUL_LIMIT:
        note = " (6 личных — в реальном матче выбыл бы; в макете остаётся)"
    events.append(
        f"Фол {defender.name} ({defender.personal_fouls} личный{note}, "
        f"командный {team_n})."
    )
    return team_n


def simulate_possession(
    offense: list[PlayerAgent],
    defense: list[PlayerAgent],
    court: Court,
    rng: random.Random,
    state: GameState | None = None,
    off_name: str = "",
    def_name: str = "",
    show_court: bool = False,
    on_tick: OnTick | None = None,
) -> PossessionResult:
    """Одно владение команды offense против пятёрки defense.

    state/off_name/def_name нужны для фолов; без них фолы считаются
    в пустую команду "" (для изолированных тестов). on_tick вызывается
    в начале каждого тика — GUI использует его для анимации.
    """
    state = state or GameState()
    events: list[str] = []
    points = 0
    orebounds = 0
    handler_idx = 0  # начинает PG (первый в списке)
    matchup = list(range(5))  # matchup[i] — кто из defense опекает offense[i]

    # Новое владение — обе команды встают в стартовую расстановку.
    for a in offense:
        a.x, a.y = a.home
        a.open_until = -1
    for d in defense:
        d.frozen = 0
    for a, d in zip(offense, defense):
        d.x, d.y = a.x + 1.2, a.y + 0.8

    for tick in range(1, TICKS_PER_POSSESSION + 1):
        clock = TICKS_PER_POSSESSION - tick + 1
        handler = offense[handler_idx]

        # 1. Защита двигается (замороженные пропускают тик).
        # matchup — перестановка: каждый защитник встречается ровно один раз.
        for off_i, def_i in enumerate(matchup):
            d = defense[def_i]
            if d.frozen > 0:
                d.frozen -= 1
                continue
            d.defend_update(offense[off_i], court)
        on_ball = defense[matchup[handler_idx]]

        if show_court:
            events.append(court.render(
                [(a.name, a.x, a.y, i == handler_idx) for i, a in enumerate(offense)],
                [(d.name, d.x, d.y) for d in defense],
                tick,
            ))
        if on_tick is not None:
            on_tick(TickSnapshot(tick, clock * TICK_SECONDS, offense, defense, handler_idx))

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
                handler.open_until = tick + 2
                on_ball.move_towards(handler.x, handler.y, court, multiplier=1.5)
                events.append(
                    f"[{clock:>2}с] {handler.name} — финт броском! "
                    f"{on_ball.name} клюёт и вылетает навстречу."
                )
            else:
                events.append(f"[{clock:>2}с] {handler.name} — финт, {on_ball.name} не реагирует.")
            continue

        if decision.action is Action.CROSSOVER:
            beat_p = 0.20 + 0.45 * on_ball.pressure
            if rng.random() < beat_p:
                on_ball.frozen = 1
                handler.open_until = tick + 1
                handler.move_towards(0.5, 0.0, court, multiplier=1.5)
                events.append(
                    f"[{clock:>2}с] {handler.name} обводит {on_ball.name} — "
                    f"тот остаётся стоять!"
                )
            elif rng.random() < 0.10 * on_ball.pressure:
                events.append(
                    f"[{clock:>2}с] {handler.name} теряет мяч в обводке — "
                    f"{on_ball.name} выбирает его! ПОТЕРЯ!"
                )
                return PossessionResult(points, events)
            else:
                events.append(f"[{clock:>2}с] {handler.name} неудачно обыгрывает, мяч сохранён.")
            continue

        if decision.action is Action.SCREEN:
            bigs = [(i, a) for i, a in enumerate(offense)
                    if i != handler_idx and a.pos in ("PF", "C")]
            if not bigs:
                events.append(f"[{clock:>2}с] {handler.name} ищет заслон, но больших рядом нет.")
                continue
            scr_idx, screener = min(bigs, key=lambda t: t[1].dist_to(on_ball.x, on_ball.y))
            screener.x, screener.y = court.clamp(on_ball.x + 0.6, on_ball.y + 0.6)
            size_bonus = {"C": 0.20, "PF": 0.12}.get(screener.pos, 0.0)
            screen_p = 0.45 + size_bonus - 0.25 * on_ball.pressure
            if rng.random() < screen_p:
                on_ball.frozen = 2
                handler.open_until = tick + 2
                if rng.random() < 0.5:  # подмена
                    d_on = matchup[handler_idx]
                    matchup[handler_idx], matchup[scr_idx] = matchup[scr_idx], d_on
                    events.append(
                        f"[{clock:>2}с] Заслон {screener.name}! {on_ball.name} врезается. "
                        f"Подмена: теперь {defense[matchup[handler_idx]].name} на {handler.name}."
                    )
                else:
                    events.append(
                        f"[{clock:>2}с] Заслон {screener.name}! {on_ball.name} "
                        f"врезается в него и отстаёт."
                    )
            else:
                events.append(
                    f"[{clock:>2}с] Заслон {screener.name} не удался — "
                    f"{on_ball.name} проходит поверх."
                )
            continue

        if decision.action is Action.DRIVE:
            # Фол в защите при прорыве (достижение руками).
            if rng.random() < REACH_IN_FOUL + FOUL_PRESSURE_K * on_ball.pressure:
                team_n = _register_foul(on_ball, def_name, state, events)
                if team_n < TEAM_FOUL_LIMIT:
                    events.append(
                        f"[{clock:>2}с] {handler.name} прорывается — фол вне броска. "
                        f"Ввод из-за боковой."
                    )
                    return PossessionResult(points, events)
                events.append(f"[{clock:>2}с] {handler.name} прорывается — фол, два штрафных!")
                points += _free_throws(handler, 2, events, rng)
                return PossessionResult(points, events)
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
        beat_active = handler.open_until >= tick
        openness = _openness(handler, on_ball, beat_active)
        three = is_three(zone)
        base = handler.profile.p3 if three else handler.profile.p2
        p_make = min(base * range_factor(zone) * openness, MAX_P_MAKE)
        mark = "3" if three else "2"

        # Фол на броске возможен только при плотном контесте.
        shooting_foul = (not beat_active and nearest_dist < SHOOTING_FOUL_DIST
                         and rng.random() < SHOOTING_FOUL + FOUL_PRESSURE_K * on_ball.pressure)
        if shooting_foul:
            _register_foul(on_ball, def_name, state, events)

        if rng.random() < p_make:
            pts = 3 if three else 2
            events.append(
                f"[{clock:>2}с] {handler.name} — попадание с {'трёх' if three else 'двух'} "
                f"({zone.value}, p={p_make:.0%})! +{pts}"
            )
            points += pts
            if shooting_foul:  # and-one
                events.append(f"Есть фол! {handler.name} получает ещё одно очко с линии.")
                points += _free_throws(handler, 1, events, rng)
            return PossessionResult(points, events)
        events.append(
            f"[{clock:>2}с] {handler.name} бросает ({mark}, {zone.value}, p={p_make:.0%}) — мимо."
        )
        if shooting_foul:
            n_ft = 3 if three else 2
            events.append(f"Фол на броске — {n_ft} штрафных.")
            points += _free_throws(handler, n_ft, events, rng)
            return PossessionResult(points, events)

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
    printer=print,
    on_tick: OnTick | None = None,
) -> tuple[int, int]:
    """Короткая показательная игра между двумя пятёрками (play-by-play).

    Первые possessions//2 владений — первая половина, дальше командные
    фолы обнуляются. В конце — сводка личных фолов. Весь вывод идёт
    через printer (GUI подставляет свой обработчик), а on_tick получает
    снимок площадки каждый тик — для анимации.
    """
    rng = random.Random(seed)
    court = Court()
    team_a = _setup(lineup_a, ctx, rng)
    team_b = _setup(lineup_b, ctx, rng)
    state = GameState()
    score_a = score_b = 0
    half = possessions // 2

    for i in range(possessions):
        if i == half:
            state.reset_half()
            printer("\n===== Конец первой половины: командные фолы обнулены =====")
        attacking, defending = (team_a, team_b) if i % 2 == 0 else (team_b, team_a)
        if i % 2 == 0:
            off_name, def_name = lineup_a.name, lineup_b.name
        else:
            off_name, def_name = lineup_b.name, lineup_a.name
        printer(f"\n===== Владение {i + 1}: мяч у пятёрки {off_name} =====")
        res = simulate_possession(
            attacking, defending, court, rng, state, off_name, def_name,
            show_court=show_court_first and i == 0,
            on_tick=on_tick,
        )
        for e in res.events:
            printer(e)
        if i % 2 == 0:
            score_a += res.points
        else:
            score_b += res.points
        printer(f"--- счёт: {lineup_a.name} {score_a} : {score_b} {lineup_b.name}")

    printer(f"\nИТОГ: {lineup_a.name} {score_a} — {score_b} {lineup_b.name}")
    for lineup, team in ((lineup_a, team_a), (lineup_b, team_b)):
        fouls = ", ".join(f"{a.name} {a.personal_fouls}" for a in team)
        printer(f"Личные фолы «{lineup.name}»: {fouls}")
    return score_a, score_b
