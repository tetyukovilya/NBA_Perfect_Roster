"""Загрузка Players.csv и фильтрация строк."""
from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from .config import DATA_PATH, DEFAULT_POSITION, POS_MAP
from .models import Player

_FLOAT_COLUMNS = (
    "mp", "per", "ts_percent", "x3p_ar", "f_tr", "orb_percent", "drb_percent",
    "trb_percent", "ast_percent", "stl_percent", "blk_percent", "tov_percent",
    "usg_percent", "ows", "dws", "ws", "ws_48", "obpm", "dbpm", "bpm", "vorp",
)


def normalize_position(pos: str | None) -> str:
    """Свести гибридную/неизвестную позицию к одной из пяти стандартных."""
    return POS_MAP.get((pos or "").strip().upper(), DEFAULT_POSITION)


def _to_float(raw: str | None) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _to_int(raw: str | None) -> int | None:
    value = _to_float(raw)
    return None if value is None else int(value)


def parse_row(row: dict[str, str]) -> Player | None:
    """Строка CSV -> Player; None, если строка непригодна (нет имени/id/сезона)."""
    name = (row.get("player") or "").strip()
    player_id = (row.get("player_id") or "").strip()
    season = _to_int(row.get("season"))
    if not name or not player_id or season is None:
        return None
    raw_pos = (row.get("pos") or "").strip()
    return Player(
        player_id=player_id,
        name=name,
        season=season,
        lg=(row.get("lg") or "").strip(),
        team=(row.get("team") or "").strip(),
        pos=normalize_position(raw_pos),
        original_pos=raw_pos,
        age=_to_int(row.get("age")),
        g=_to_int(row.get("g")) or 0,
        **{col: _to_float(row.get(col)) for col in _FLOAT_COLUMNS},
    )


def load_players(path: Path | str = DATA_PATH) -> list[Player]:
    """Прочитать все строки CSV (включая и суммарные, и покомандные)."""
    with open(path, newline="", encoding="utf-8") as f:
        return [p for p in map(parse_row, csv.DictReader(f)) if p is not None]


def season_rows(players: Iterable[Player]) -> list[Player]:
    """По одной строке на игрока за сезон.

    Для игроков, сменивших клуб, в данных есть суммарная строка (2TM/3TM)
    и строки по каждому клубу. Для сезонных рейтингов берём суммарную,
    иначе обмен «размазывает» сезон и лучший игрок может не попасть в топ.
    """
    players = list(players)
    aggregated = {(p.player_id, p.season, p.lg) for p in players if p.is_aggregate}
    return [
        p for p in players
        if p.is_aggregate or (p.player_id, p.season, p.lg) not in aggregated
    ]


def team_rows(players: Iterable[Player]) -> list[Player]:
    """Только покомандные строки (без 2TM/3TM) — для подсчёта совместных минут."""
    return [p for p in players if not p.is_aggregate]


def filter_players(
    players: Iterable[Player],
    *,
    min_minutes: float = 0.0,
    season_from: int | None = None,
    season_to: int | None = None,
    leagues: Iterable[str] | None = None,
) -> list[Player]:
    """Отфильтровать строки по минутам, диапазону сезонов и лигам."""
    league_set = set(leagues) if leagues is not None else None
    result = []
    for p in players:
        if min_minutes > 0 and (p.mp or 0.0) < min_minutes:
            continue
        if season_from is not None and p.season < season_from:
            continue
        if season_to is not None and p.season > season_to:
            continue
        if league_set is not None and p.lg not in league_set:
            continue
        result.append(p)
    return result
