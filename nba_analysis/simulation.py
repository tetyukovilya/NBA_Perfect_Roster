"""Монте-Карло симуляция матчей между пятёрками.

Модель одного владения (все вероятности — из PlayerProfile):

1. Игрок, на котором заканчивается розыгрыш, выбирается пропорционально USG%.
2. Потеря: P = TOV% игрока × (STL% обороны / средний STL% лиги).
3. Поход на линию штрафных (по FTr) или бросок с игры: 3-очковый с
   вероятностью 3PAr, точность из TS% (через eFG%), умноженная на бонус химии
   и на фактор обороны (сумма DBPM пятёрки соперника).
4. Промах -> подбор: P(в нападении) = ΣORB% / (ΣORB% + ΣDRB%).
   Подбор в нападении продолжает то же владение.

В каждой игре у каждой команды ровно ``possessions_per_game`` владений,
при ничьей играются овертаймы.
"""
from __future__ import annotations

import bisect
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import accumulate, combinations

from .chemistry import ChemistryModel
from .config import SimulationConfig
from .models import Lineup
from .profiles import FTA_POSSESSION_FACTOR, LeagueContext, PlayerProfile, build_profile

# В среднем за «поход на линию» бросается 1/0.44 ≈ 2.27 штрафных.
EXTRA_FT_PROB = 1 / FTA_POSSESSION_FACTOR - 2
OVERTIME_POSSESSIONS = 10
MAX_OVERTIMES = 5


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass(frozen=True, slots=True)
class TeamState:
    """Предрасчитанные параметры пятёрки, чтобы не считать их в каждом владении."""

    name: str
    profiles: tuple[PlayerProfile, ...]
    cum_usage: tuple[float, ...]   # накопленные веса USG% для выбора игрока
    make_mult: tuple[float, ...]   # бонус химии к точности для каждого игрока
    orb: float                     # Σ ORB%
    drb: float                     # Σ DRB%
    # Как эта пятёрка влияет на соперника, когда обороняется:
    defense_factor: float          # множитель к точности бросков соперника
    steal_factor: float            # множитель к потерям соперника


@dataclass(frozen=True, slots=True)
class MatchupResult:
    team_a: str
    team_b: str
    games: int
    wins_a: int
    wins_b: int
    avg_score_a: float
    avg_score_b: float
    mean_diff: float     # средняя разница (A - B) за игру
    std_diff: float

    @property
    def win_pct_a(self) -> float:
        return self.wins_a / self.games if self.games else 0.0

    @property
    def stderr_diff(self) -> float:
        return self.std_diff / math.sqrt(self.games) if self.games else 0.0


class Simulator:
    def __init__(
        self,
        ctx: LeagueContext,
        cfg: SimulationConfig | None = None,
        chemistry: ChemistryModel | None = None,
        rng: random.Random | None = None,
    ):
        self.ctx = ctx
        self.cfg = cfg or SimulationConfig()
        self.chemistry = chemistry
        self.rng = rng or random.Random(self.cfg.seed)
        self._league_stl = ctx.global_avg("stl_percent") or 1.0

    # --- подготовка -------------------------------------------------------
    def team_state(self, lineup: Lineup) -> TeamState:
        cfg = self.cfg
        profiles = tuple(build_profile(p, self.ctx, cfg) for p in lineup.players)
        if self.chemistry is not None and cfg.chemistry_weight:
            make_mult = tuple(
                1.0 + cfg.chemistry_weight * self.chemistry.handler_bonus(h, profiles)
                for h in profiles
            )
        else:
            make_mult = (1.0,) * len(profiles)

        dbpm_sum = sum(p.dbpm for p in profiles)
        mean_stl = sum(p.stl for p in profiles) / len(profiles)
        return TeamState(
            name=lineup.name,
            profiles=profiles,
            cum_usage=tuple(accumulate(p.usage for p in profiles)),
            make_mult=make_mult,
            orb=sum(p.orb for p in profiles),
            drb=sum(p.drb for p in profiles),
            defense_factor=_clamp(
                1 - cfg.defense_scale * dbpm_sum / (100 * cfg.league_points_per_possession),
                0.6, 1.4,
            ),
            steal_factor=_clamp(mean_stl / self._league_stl, 0.5, 2.0),
        )

    # --- игра -------------------------------------------------------------
    def possession(self, off: TeamState, dfn: TeamState) -> int:
        """Одно владение (включая подборы в нападении); возвращает очки."""
        rng = self.rng
        cfg = self.cfg
        p_oreb = off.orb / (off.orb + dfn.drb) if (off.orb + dfn.drb) > 0 else 0.25
        points = 0
        for _ in range(cfg.max_offensive_rebounds + 1):
            i = bisect.bisect_right(off.cum_usage, rng.random() * off.cum_usage[-1])
            i = min(i, len(off.profiles) - 1)
            h = off.profiles[i]

            if rng.random() < h.tov_rate * dfn.steal_factor:
                return points

            if rng.random() < h.ft_trip_rate:
                attempts = 3 if rng.random() < EXTRA_FT_PROB else 2
                made = False
                for _ in range(attempts):
                    made = rng.random() < cfg.league_ft_pct
                    points += made
                if made:
                    return points
            else:
                is_three = rng.random() < h.three_rate
                p_make = (h.p3 if is_three else h.p2) * off.make_mult[i] * dfn.defense_factor
                if rng.random() < min(p_make, cfg.max_make_prob):
                    return points + (3 if is_three else 2)

            if rng.random() >= p_oreb:  # подбор в защите
                return points
        return points

    def _play_possessions(self, a: TeamState, b: TeamState, n: int) -> tuple[int, int]:
        score_a = score_b = 0
        for _ in range(n):
            score_a += self.possession(a, b)
            score_b += self.possession(b, a)
        return score_a, score_b

    def play_game(self, a: TeamState, b: TeamState) -> tuple[int, int]:
        score_a, score_b = self._play_possessions(a, b, self.cfg.possessions_per_game)
        for _ in range(MAX_OVERTIMES):
            if score_a != score_b:
                break
            ot_a, ot_b = self._play_possessions(a, b, OVERTIME_POSSESSIONS // 2)
            score_a += ot_a
            score_b += ot_b
        return score_a, score_b

    def play_series(self, lineup_a: Lineup, lineup_b: Lineup, games: int | None = None) -> MatchupResult:
        games = self.cfg.games if games is None else games
        a, b = self.team_state(lineup_a), self.team_state(lineup_b)
        wins_a = wins_b = 0
        sum_a = sum_b = 0
        sum_d = sum_d2 = 0.0
        for _ in range(games):
            sa, sb = self.play_game(a, b)
            sum_a += sa
            sum_b += sb
            d = sa - sb
            sum_d += d
            sum_d2 += d * d
            if d > 0:
                wins_a += 1
            elif d < 0:
                wins_b += 1
        n = max(games, 1)
        mean = sum_d / n
        var = max(sum_d2 / n - mean * mean, 0.0)
        return MatchupResult(
            team_a=lineup_a.name, team_b=lineup_b.name, games=games,
            wins_a=wins_a, wins_b=wins_b,
            avg_score_a=sum_a / n, avg_score_b=sum_b / n,
            mean_diff=mean, std_diff=math.sqrt(var),
        )


def round_robin(
    simulator: Simulator,
    lineups: Sequence[Lineup],
    games: int | None = None,
    progress: Callable[[MatchupResult], None] | None = None,
) -> list[MatchupResult]:
    """Каждая пара пятёрок играет одну серию."""
    results = []
    for a, b in combinations(lineups, 2):
        result = simulator.play_series(a, b, games)
        results.append(result)
        if progress:
            progress(result)
    return results


def average_point_diff(results: Sequence[MatchupResult]) -> dict[str, float]:
    """Средняя разница очков каждой пятёрки против всех остальных."""
    totals: dict[str, list[float]] = {}
    for r in results:
        totals.setdefault(r.team_a, []).append(r.mean_diff)
        totals.setdefault(r.team_b, []).append(-r.mean_diff)
    return {name: sum(v) / len(v) for name, v in totals.items()}
