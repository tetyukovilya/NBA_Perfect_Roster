"""Командная строка: ``nba-analysis`` или ``python -m nba_analysis``."""
from __future__ import annotations

import argparse
import time
from dataclasses import replace

from . import __version__
from .config import AnalysisConfig, SimulationConfig
from .pipeline import build_lineups, load_dataset, run_analysis
from .reporter import generate_report, save_report

QUICK_GAMES = 100


def build_parser() -> argparse.ArgumentParser:
    defaults = AnalysisConfig()
    sim = SimulationConfig()
    parser = argparse.ArgumentParser(
        prog="nba-analysis",
        description="NBA historical lineup analysis and simulation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-g", "--games", type=int, default=sim.games, help="games per matchup")
    parser.add_argument("-q", "--quick", action="store_true", help=f"only {QUICK_GAMES} games per matchup")
    parser.add_argument("-c", "--chem-weight", type=float, default=sim.chemistry_weight,
                        help="influence of chemistry on shot accuracy")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible results")
    parser.add_argument("--no-era-adjust", action="store_true", help="use raw TS%% instead of era-relative")
    parser.add_argument("--min-minutes", type=float, default=defaults.min_minutes,
                        help="minimum minutes played in a season")
    parser.add_argument("--from", dest="season_from", type=int, default=None, help="first season")
    parser.add_argument("--to", dest="season_to", type=int, default=None, help="last season")
    parser.add_argument("--leagues", nargs="+", default=list(defaults.leagues), help="leagues to include")
    parser.add_argument("-o", "--output", default=str(defaults.output_path), help="markdown report path")
    parser.add_argument("-l", "--list-lineups", action="store_true", help="only print lineups, skip simulation")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def config_from_args(args: argparse.Namespace) -> AnalysisConfig:
    base = AnalysisConfig()
    sim = replace(
        base.simulation,
        games=QUICK_GAMES if args.quick else args.games,
        chemistry_weight=args.chem_weight,
        era_adjust=not args.no_era_adjust,
        seed=args.seed,
    )
    return replace(
        base,
        output_path=args.output,
        min_minutes=args.min_minutes,
        season_from=args.season_from,
        season_to=args.season_to,
        leagues=tuple(args.leagues),
        simulation=sim,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config_from_args(args)

    if args.list_lineups:
        data = load_dataset(cfg)
        for lineup in build_lineups(cfg, data):
            print(f"\n=== {lineup.name} ({lineup.metric.upper()}) ===")
            for pos, p in lineup.slots():
                print(f"  {pos:<2}  {p.label:<40} {lineup.metric.upper()}: {getattr(p, lineup.metric):.2f}")
        return 0

    started = time.perf_counter()
    result = run_analysis(cfg, log=print)
    for name, diff in sorted(result.avg_diff.items(), key=lambda kv: -kv[1]):
        print(f"{name:<10} {diff:+.2f} avg point diff")
    save_report(generate_report(result), cfg.output_path)
    print(f"Report written to {cfg.output_path} ({time.perf_counter() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
