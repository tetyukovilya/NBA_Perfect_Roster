"""Профиль игрока для симуляции.

Переводит сезонную rate-статистику (TS%, TOV%, FTr, 3PAr, ORB%, DRB%, USG%,
STL%, DBPM) в вероятности исходов владения. Пропуски в старых сезонах
заполняются средними по сезону, а DBPM до 1974 г. оценивается по DWS/48.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .config import SimulationConfig
from .models import Player

# Доля FTA, которая «съедает» владение (стандарт Basketball-Reference).
FTA_POSSESSION_FACTOR = 0.44

# Показатели, пропуски в которых заполняются средним по сезону/лиге.
IMPUTED_STATS = (
    "ts_percent", "f_tr", "x3p_ar", "orb_percent", "drb_percent", "trb_percent",
    "ast_percent", "stl_percent", "blk_percent", "tov_percent", "usg_percent",
)

# Если по сезону данных нет совсем: x3p_ar = 0 (до 1980 г. в NBA не было
# трёхочковой линии), для остальных — среднее по всей истории.
_FALLBACK_OVERRIDES = {"x3p_ar": 0.0}

# Масштабы для вектора стиля (приводим показатели к ~0..1).
_STYLE_SCALES = (("x3p_ar", 1.0), ("ast_percent", 50.0), ("trb_percent", 25.0),
                 ("blk_percent", 6.0), ("stl_percent", 3.5))


def _weight(p: Player) -> float:
    """Вес строки при усреднении: минуты (до 1952 г. минут нет — оцениваем по играм)."""
    if p.mp:
        return p.mp
    return p.g * 20.0


def least_squares(xs: list[list[float]], ys: list[float]) -> list[float]:
    """МНК через нормальные уравнения (без numpy). Последний коэффициент — свободный член."""
    rows = [x + [1.0] for x in xs]
    k = len(rows[0]) if rows else 1
    if len(rows) < k:
        return [0.0] * (k - 1) + [sum(ys) / len(ys) if ys else 0.0]
    # Матрица [X^T X | X^T y]
    a = [[sum(r[i] * r[j] for r in rows) for j in range(k)] for i in range(k)]
    for i in range(k):
        a[i].append(sum(r[i] * y for r, y in zip(rows, ys)))
    # Гаусс с выбором главного элемента
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(a[r][col]))
        a[col], a[pivot] = a[pivot], a[col]
        if abs(a[col][col]) < 1e-12:
            continue
        for r in range(k):
            if r != col:
                f = a[r][col] / a[col][col]
                a[r] = [v - f * w for v, w in zip(a[r], a[col])]
    return [a[i][k] / a[i][i] if abs(a[i][i]) > 1e-12 else 0.0 for i in range(k)]


class _LinearImputer:
    """Оценка пропущенного показателя линейной регрессией по другим показателям.

    Нужна для сезонов до 1974 г.: DBPM и USG% тогда не считались,
    но DWS, PER и TS% есть. (Корреляция на современных данных:
    DBPM ~ DWS/48: r≈0.78; USG% ~ PER + TS%: r≈0.73.)
    """

    def __init__(self, target: str, features, players: list[Player], min_minutes: float = 500):
        self.target = target
        self.features = features
        xs, ys = [], []
        for p in players:
            y = getattr(p, target)
            x = features(p)
            if y is not None and x is not None and (p.mp or 0) >= min_minutes:
                xs.append(x)
                ys.append(y)
        self.coef = least_squares(xs, ys)

    def predict(self, p: Player) -> float | None:
        x = self.features(p)
        if x is None:
            return None
        return sum(c * v for c, v in zip(self.coef, x + [1.0]))


def _dws_per_48(p: Player) -> list[float] | None:
    if p.dws is None or not p.mp:
        return None
    return [p.dws * 48.0 / p.mp]


def _per_and_ts(p: Player) -> list[float] | None:
    if p.per is None or p.ts_percent is None:
        return None
    return [p.per, p.ts_percent]


class LeagueContext:
    """Средние по лиге за сезон и правила заполнения пропусков.

    Строится по *всем* сезонным строкам датасета (до фильтрации), чтобы
    средние не зависели от того, какие игроки отобраны в пятёрки.
    """

    def __init__(self, players: Iterable[Player]):
        players = [p for p in players if not p.is_aggregate]
        sums: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
        global_sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for p in players:
            w = _weight(p)
            if w <= 0:
                continue
            for stat in IMPUTED_STATS:
                value = getattr(p, stat)
                if value is None:
                    continue
                acc = sums[(stat, p.season, p.lg)]
                acc[0] += w * value
                acc[1] += w
                g_acc = global_sums[stat]
                g_acc[0] += w * value
                g_acc[1] += w
        self._season_avg = {k: s / w for k, (s, w) in sums.items() if w > 0}
        self._global_avg = {k: s / w for k, (s, w) in global_sums.items() if w > 0}

        # Регрессионная оценка для показателей, которых нет в старых сезонах.
        self._imputers = {
            "dbpm": _LinearImputer("dbpm", _dws_per_48, players),
            "usg_percent": _LinearImputer("usg_percent", _per_and_ts, players),
        }

    def season_avg(self, stat: str, season: int, lg: str) -> float | None:
        return self._season_avg.get((stat, season, lg))

    def global_avg(self, stat: str) -> float:
        if stat in _FALLBACK_OVERRIDES:
            return _FALLBACK_OVERRIDES[stat]
        return self._global_avg.get(stat, 0.0)

    def stat(self, p: Player, stat: str) -> float:
        """Значение с заполнением пропуска: регрессия -> среднее за сезон -> среднее за историю."""
        value = getattr(p, stat)
        if value is not None:
            return value
        imputer = self._imputers.get(stat)
        if imputer is not None:
            estimate = imputer.predict(p)
            if estimate is not None:
                return estimate
        season_value = self.season_avg(stat, p.season, p.lg)
        return season_value if season_value is not None else self.global_avg(stat)

    def era_adjusted_ts(self, p: Player) -> float:
        """TS% относительно среднего по сезону, перенесённый на исторический уровень."""
        ts = self.stat(p, "ts_percent")
        season = self.season_avg("ts_percent", p.season, p.lg)
        if season is None:
            return ts
        return ts - season + self.global_avg("ts_percent")

    def dbpm(self, p: Player) -> float:
        if p.dbpm is not None:
            return p.dbpm
        estimate = self._imputers["dbpm"].predict(p)
        return 0.0 if estimate is None else estimate


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    """Параметры игрока, которые напрямую использует симулятор."""

    player_id: str
    name: str
    usage: float          # USG% в долях: насколько часто владение заканчивается на нём
    tov_rate: float       # P(потеря) на розыгрыш
    ft_trip_rate: float   # P(розыгрыш закончился штрафными | не потеря)
    three_rate: float     # доля трёхочковых среди бросков с игры
    p2: float             # P(попадание 2-очкового)
    p3: float             # P(попадание 3-очкового)
    orb: float            # ORB% в долях
    drb: float            # DRB% в долях
    stl: float            # STL% (в процентах)
    dbpm: float           # очков на 100 владений, которые игрок «отнимает» в защите
    style: tuple[float, ...]


def build_profile(p: Player, ctx: LeagueContext, cfg: SimulationConfig) -> PlayerProfile:
    """Player (+ средние лиги) -> PlayerProfile."""
    ts = ctx.era_adjusted_ts(p) if cfg.era_adjust else ctx.stat(p, "ts_percent")
    f_tr = ctx.stat(p, "f_tr")
    three_rate = min(max(ctx.stat(p, "x3p_ar"), 0.0), 1.0)

    # Из TS% вычитаем вклад штрафных и получаем eFG%:
    #   PTS = 2*TS*(FGA + 0.44*FTA),  eFG = (PTS - FT%*FTA) / (2*FGA)
    efg = ts * (1 + FTA_POSSESSION_FACTOR * f_tr) - cfg.league_ft_pct * f_tr / 2
    # eFG = (1-x)*p2 + 1.5*x*p3,  p3 = r*p2
    denom = (1 - three_rate) + 1.5 * three_rate * cfg.three_to_two_ratio
    p2 = min(max(efg / denom, 0.05), cfg.max_make_prob)
    p3 = min(p2 * cfg.three_to_two_ratio, cfg.max_make_prob)

    ft_plays = FTA_POSSESSION_FACTOR * f_tr
    style = tuple(min(max(ctx.stat(p, stat) / scale, 0.0), 1.0) for stat, scale in _STYLE_SCALES)

    return PlayerProfile(
        player_id=p.player_id,
        name=p.name,
        usage=max(ctx.stat(p, "usg_percent"), 1.0) / 100.0,
        tov_rate=min(max(ctx.stat(p, "tov_percent"), 0.0), 40.0) / 100.0,
        ft_trip_rate=ft_plays / (1 + ft_plays),
        three_rate=three_rate,
        p2=p2,
        p3=p3,
        orb=ctx.stat(p, "orb_percent") / 100.0,
        drb=ctx.stat(p, "drb_percent") / 100.0,
        stl=ctx.stat(p, "stl_percent"),
        dbpm=ctx.dbpm(p),
        style=style,
    )
