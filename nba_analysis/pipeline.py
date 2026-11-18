"""Основной пайплайн: данные -> пятёрки -> симуляция."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .chemistry import ChemistryModel, compute_shared_minutes
from .config import AnalysisConfig
from .data_loader import filter_players, load_players, season_rows, team_rows
from .lineup_builder import best_lineup
from .models import Lineup, Player
from .profiles import LeagueContext
from .simulation import MatchupResult, Simulator, average_point_diff, round_robin

Log = Callable[[str], None]


def _silent(_: str) -> None:
    pass


@dataclass(frozen=True)
class Dataset:
    """Загруженные данные и всё, что из них предрасчитывается один раз."""

    all_rows: list[Player]
    candidates: list[Player]        # сезонные строки после фильтров — кандидаты в пятёрки
    context: LeagueContext
    shared_minutes: dict[tuple[str, str], float]


@dataclass(frozen=True)
class AnalysisResult:
    config: AnalysisConfig
    lineups: list[Lineup]
    matchups: list[MatchupResult]
    avg_diff: dict[str, float]


def load_dataset(cfg: AnalysisConfig, log: Log = _silent) -> Dataset:
    rows = load_players(cfg.data_path)
    log(f"Loaded {len(rows)} rows from {cfg.data_path}")
    seasons = season_rows(rows)
    candidates = filter_players(
        seasons,
        min_minutes=cfg.min_minutes,
        season_from=cfg.season_from,
        season_to=cfg.season_to,
        leagues=cfg.leagues,
    )
    log(f"{len(candidates)} player-seasons pass filters (min {cfg.min_minutes:g} MP)")
    if not candidates:
        raise ValueError("No players left after filtering; relax --min-minutes / season range")
    return Dataset(
        all_rows=rows,
        candidates=candidates,
        context=LeagueContext(rows),
        shared_minutes=compute_shared_minutes(team_rows(rows)),
    )


def build_lineups(cfg: AnalysisConfig, data: Dataset) -> list[Lineup]:
    return [best_lineup(data.candidates, metric, name=name) for name, metric in cfg.lineups]


def run_analysis(cfg: AnalysisConfig | None = None, log: Log = _silent) -> AnalysisResult:
    cfg = cfg or AnalysisConfig()
    data = load_dataset(cfg, log)
    lineups = build_lineups(cfg, data)
    for lineup in lineups:
        log(f"{lineup.name}: " + ", ".join(p.label for p in lineup))

    simulator = Simulator(
        data.context,
        cfg.simulation,
        chemistry=ChemistryModel(data.shared_minutes, cfg.chemistry),
    )
    log(f"Simulating {cfg.simulation.games} games per matchup...")
    matchups = round_robin(
        simulator,
        lineups,
        progress=lambda r: log(
            f"  {r.team_a} vs {r.team_b}: {r.avg_score_a:.1f}-{r.avg_score_b:.1f}, "
            f"{r.team_a} wins {r.win_pct_a:.1%}"
        ),
    )
    return AnalysisResult(cfg, lineups, matchups, average_point_diff(matchups))
