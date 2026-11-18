"""Парная «химия» игроков: схожесть стиля, сыгранность и конфликт за мяч."""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence

from .config import ChemistryConfig
from .models import Player
from .profiles import PlayerProfile

# Средний USG% игрока на площадке — 20% (5 игроков делят 100% владений).
AVERAGE_USAGE = 0.20


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def compute_shared_minutes(team_rows: Iterable[Player]) -> dict[tuple[str, str], float]:
    """Оценка совместных минут для каждой пары игроков (по player_id).

    Для одноклубников в сезоне берём min(MP_i, MP_j) — верхнюю оценку
    (точных данных по пятёркам в датасете нет). Суммарные строки (2TM)
    сюда не должны попадать, иначе все обменянные за сезон игроки
    окажутся «одноклубниками».
    """
    groups: dict[tuple, list[Player]] = defaultdict(list)
    for p in team_rows:
        if p.is_aggregate or not p.mp:
            continue
        groups[(p.season, p.lg, p.team)].append(p)

    shared: dict[tuple[str, str], float] = defaultdict(float)
    for group in groups.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.player_id != b.player_id:
                    shared[pair_key(a.player_id, b.player_id)] += min(a.mp, b.mp)
    return dict(shared)


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


class ChemistryModel:
    """Считает химию пар и бонус для игрока с мячом. Кэш — на экземпляре."""

    def __init__(self, shared_minutes: dict[tuple[str, str], float], cfg: ChemistryConfig | None = None):
        self.shared_minutes = shared_minutes
        self.cfg = cfg or ChemistryConfig()
        self._log_saturation = math.log1p(self.cfg.familiarity_saturation_minutes)
        self._cache: dict[tuple[str, str], float] = {}

    def familiarity(self, a_id: str, b_id: str) -> float:
        """0..1: насколько игроки сыграны (лог-шкала совместных минут)."""
        minutes = self.shared_minutes.get(pair_key(a_id, b_id), 0.0)
        return min(1.0, math.log1p(minutes) / self._log_saturation)

    def pair(self, a: PlayerProfile, b: PlayerProfile) -> float:
        key = pair_key(a.player_id, b.player_id)
        if key in self._cache:
            return self._cache[key]
        cfg = self.cfg
        usage_overlap = max(0.0, a.usage + b.usage - 2 * AVERAGE_USAGE)
        value = (
            cfg.w_similarity * cosine_similarity(a.style, b.style)
            + cfg.w_familiarity * self.familiarity(a.player_id, b.player_id)
            - cfg.w_usage_overlap * usage_overlap
        )
        value = min(cfg.chem_max, max(cfg.chem_min, value))
        self._cache[key] = value
        return value

    def handler_bonus(self, handler: PlayerProfile, lineup: Sequence[PlayerProfile]) -> float:
        """Средняя химия игрока с мячом с четырьмя партнёрами."""
        mates = [p for p in lineup if p.player_id != handler.player_id]
        if not mates:
            return 0.0
        return sum(self.pair(handler, m) for m in mates) / len(mates)
