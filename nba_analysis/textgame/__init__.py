"""Текстовая игра: живая симуляция баскетбольного владения в терминале.

МАКЕТ (прототип). Отличия от Monte-Carlo симуляции (simulation.py):
здесь каждый игрок — агент с позицией на площадке, который каждый тик
выбирает действие (передвижение, финт, пас, бросок), а защитники реально
перемещаются и влияют на бросок через близость (contest).

Схема координат (половина площадки, нападение влево):
    x: 0 (щит) .. 14 (центральная линия)
    y: -7.5 .. 7.5 (ширина)
Кольцо в точке (0, 0). Один тик = 2 секунды владения.
"""
from .court import Court, ShotZone, zone_at
from .actors import PlayerAgent, Action, Decision
from .engine import GameState, PossessionResult, simulate_possession, simulate_game

__all__ = [
    "Court", "ShotZone", "zone_at",
    "PlayerAgent", "Action", "Decision",
    "GameState", "PossessionResult", "simulate_possession", "simulate_game",
]
