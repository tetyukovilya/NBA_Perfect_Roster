"""Демо текстовой игры: nba-game (или python -m nba_analysis.textgame).

Берёт две лучшие пятёрки из исторического датасета и показывает
показательную игру с play-by-play отчётом в терминале.
"""
from __future__ import annotations

import argparse

from ..config import AnalysisConfig
from ..pipeline import build_lineups, load_dataset
from .engine import simulate_game


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nba-game",
        description="Текстовая игра: живая симуляция владений между двумя пятёрками",
    )
    parser.add_argument("--possessions", type=int, default=12, help="число владений (по очереди)")
    parser.add_argument("--seed", type=int, default=42, help="seed для воспроизводимости")
    parser.add_argument("--no-court", action="store_true", help="не рисовать ASCII-площадку")
    args = parser.parse_args(argv)

    cfg = AnalysisConfig()
    data = load_dataset(cfg)
    lineups = build_lineups(cfg, data)
    lineup_a, lineup_b = lineups[0], lineups[1]

    print(f"Пятёрка «{lineup_a.name}»: " + ", ".join(p.name for p in lineup_a))
    print(f"Пятёрка «{lineup_b.name}»: " + ", ".join(p.name for p in lineup_b))
    simulate_game(
        lineup_a, lineup_b, data.context,
        possessions=args.possessions, seed=args.seed,
        show_court_first=not args.no_court,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
