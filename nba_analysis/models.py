"""Модели данных: строка статистики игрока за сезон и пятёрка."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .config import LINEUP_METRICS, STANDARD_POSITIONS

# Basketball-Reference помечает суммарную строку игрока, сменившего клубы,
# как "2TM"/"3TM"/... (в старых выгрузках — "TOT").
_AGGREGATE_TEAM_RE = re.compile(r"^(TOT|\d+TM)$")


def is_aggregate_team(team: str) -> bool:
    """True для суммарной строки по нескольким клубам (TOT, 2TM, 3TM...)."""
    return bool(_AGGREGATE_TEAM_RE.match(team))


@dataclass(slots=True)
class Player:
    """Одна строка Players.csv: игрок, сезон, команда.

    Названия статистических полей совпадают с колонками CSV.
    ``None`` означает, что показатель в источнике отсутствует
    (например, USG% и DBPM до 1974 года не считались).
    """

    player_id: str
    name: str
    season: int
    lg: str
    team: str
    pos: str            # нормализованная позиция (PG/SG/SF/PF/C)
    original_pos: str   # позиция как в источнике
    age: int | None = None
    g: int = 0
    mp: float | None = None
    per: float | None = None
    ts_percent: float | None = None
    x3p_ar: float | None = None
    f_tr: float | None = None
    orb_percent: float | None = None
    drb_percent: float | None = None
    trb_percent: float | None = None
    ast_percent: float | None = None
    stl_percent: float | None = None
    blk_percent: float | None = None
    tov_percent: float | None = None
    usg_percent: float | None = None
    ows: float | None = None
    dws: float | None = None
    ws: float | None = None
    ws_48: float | None = None
    obpm: float | None = None
    dbpm: float | None = None
    bpm: float | None = None
    vorp: float | None = None

    @property
    def is_aggregate(self) -> bool:
        return is_aggregate_team(self.team)

    @property
    def label(self) -> str:
        """Человекочитаемая подпись: «Michael Jordan (1988 CHI)»."""
        return f"{self.name} ({self.season} {self.team})"

    def get_metric(self, metric: str) -> float:
        """Значение метрики для ранжирования; отсутствующее значение = -inf.

        Неизвестная метрика — ошибка, а не молчаливый 0.0.
        """
        if metric not in LINEUP_METRICS:
            raise ValueError(f"Unknown metric {metric!r}; expected one of {LINEUP_METRICS}")
        value = getattr(self, metric)
        return -math.inf if value is None else value


@dataclass(frozen=True, slots=True)
class Lineup:
    """Пятёрка игроков; ``players[i]`` играет на позиции ``positions[i]``."""

    name: str
    metric: str
    players: tuple[Player, ...]
    positions: tuple[str, ...] = STANDARD_POSITIONS

    def __post_init__(self) -> None:
        if len(self.players) != 5:
            raise ValueError(f"Lineup must have exactly 5 players, got {len(self.players)}")
        if len(self.positions) != len(self.players):
            raise ValueError("positions and players must have the same length")
        ids = [p.player_id for p in self.players]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Lineup {self.name!r} contains the same player twice: {ids}")

    def __iter__(self):
        return iter(self.players)

    def slots(self) -> list[tuple[str, Player]]:
        """Пары (назначенная позиция, игрок)."""
        return list(zip(self.positions, self.players))
