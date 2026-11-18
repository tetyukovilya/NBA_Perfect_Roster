"""Построение пятёрок: по одному игроку на позицию, без повторов."""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from .config import STANDARD_POSITIONS
from .models import Lineup, Player


def best_lineup(
    players: Iterable[Player],
    metric: str,
    name: str | None = None,
    positions: Sequence[str] = STANDARD_POSITIONS,
) -> Lineup:
    """Лучшая пятёрка по метрике.

    Жадно идём по сезонам в порядке убывания метрики: сезон занимает слот
    своей позиции, если слот свободен и игрок ещё не выбран (каждый игрок
    попадает в пятёрку один раз — лучшим подходящим сезоном). Незаполненные
    слоты добираются лучшими оставшимися игроками любой позиции.
    """
    ranked = sorted(
        (p for p in players if p.get_metric(metric) != -math.inf),
        key=lambda p: p.get_metric(metric),
        reverse=True,
    )
    slots: dict[str, Player] = {}
    used: set[str] = set()

    for p in ranked:
        if len(slots) == len(positions):
            break
        if p.pos in positions and p.pos not in slots and p.player_id not in used:
            slots[p.pos] = p
            used.add(p.player_id)

    for pos in positions:
        if pos in slots:
            continue
        candidate = next((p for p in ranked if p.player_id not in used), None)
        if candidate is None:
            raise ValueError(f"Not enough players to build a {len(positions)}-man lineup")
        slots[pos] = candidate
        used.add(candidate.player_id)

    return Lineup(
        name=name or metric.upper(),
        metric=metric,
        players=tuple(slots[pos] for pos in positions),
        positions=tuple(positions),
    )
